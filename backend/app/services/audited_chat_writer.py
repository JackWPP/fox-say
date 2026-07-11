"""Audited chat writer for agent-run-owned DeepSeek text completions.

This wrapper mirrors :class:`AuditedDeepSeekTextModel` but is keyed to an
:class:`AgentRun` instead of a :class:`KnowledgeJob`.  It uses the F1
``reserve_agent_run_model_call`` path (``owner_type='agent_run'``,
``budget_scope='interactive'``) so interactive model calls are budgeted and
audited without requiring a knowledge-job lease.

The helper functions for canonical-request fingerprinting, token estimation,
response extraction, and error classification are reused from
:mod:`app.services.audited_text_model` to avoid duplicating that logic.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from app.db.sqlite_store import SqliteStore
from app.schemas.agent_runs import AGENT_RUN_ACTIVE_STATUSES, AgentRun
from app.schemas.model_calls import ModelCallReservationRequest
from app.services.audited_text_model import (
    AuditedModelCallError,
    AuditedTextResult,
    _canonical_request,
    _classify_provider_error,
    _conservative_input_token_upper_bound,
    _elapsed_ms,
    _extract_content,
    _extract_usage,
)


class AuditedChatWriter:
    """Reserve -> call once -> settle an OpenAI-compatible text completion for an agent run.

    Unlike the knowledge-job wrapper, this does not require a lease.  It
    validates that the run is still in a non-terminal status after the
    provider call settles, so a run that was cancelled or marked stale
    during the call is detected rather than silently accepted.
    """

    def __init__(
        self,
        store: SqliteStore,
        *,
        client: Any,
        model: str,
        course_budget_tokens: int,
        provider: str = "deepseek",
    ) -> None:
        if not model.strip() or not provider.strip() or course_budget_tokens <= 0:
            raise ValueError("Model, provider, and course budget must be configured")
        self._store = store
        self._client = client
        self._model = model
        self._provider = provider
        self._course_budget_tokens = course_budget_tokens

    async def complete(
        self,
        run: AgentRun,
        *,
        purpose: str,
        messages: Sequence[Mapping[str, Any]],
        max_output_tokens: int,
        temperature: float | None = None,
        budget_scope: str = "interactive",
    ) -> AuditedTextResult:
        """Make exactly one audited completion for a currently active agent run."""
        if not purpose.strip() or max_output_tokens <= 0:
            raise ValueError("purpose and max_output_tokens are required")
        if budget_scope not in ("interactive", "review", "artifact"):
            raise ValueError(f"Unsupported budget_scope: {budget_scope}")

        canonical_request = _canonical_request(
            model=self._model,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        request = ModelCallReservationRequest(
            call_id=str(uuid.uuid4()),
            course_id=run.course_id,
            owner_type="agent_run",
            run_id=run.run_id,
            budget_scope=budget_scope,
            source_revision=run.source_revision,
            knowledge_revision=run.knowledge_revision,
            call_kind="text",
            purpose=purpose,
            provider=self._provider,
            model=self._model,
            request_fingerprint=hashlib.sha256(canonical_request).hexdigest(),
            input_token_upper_bound=_conservative_input_token_upper_bound(
                canonical_request, message_count=len(messages)
            ),
            max_output_tokens=max_output_tokens,
            course_budget_tokens=self._course_budget_tokens,
        )

        audit = await asyncio.to_thread(self._store.reserve_agent_run_model_call, request)
        if audit.status == "rejected":
            raise AuditedModelCallError(
                audit.error_detail or "Model call was rejected before contacting the provider",
                audit.error_code or "model_call_rejected",
                False,
            )

        started = time.monotonic()
        try:
            response = await asyncio.to_thread(
                self._create_completion,
                messages,
                max_output_tokens,
                temperature,
            )
            content = _extract_content(response)
            usage = _extract_usage(response)
        except Exception as exc:
            error = _classify_provider_error(exc)
            await asyncio.to_thread(
                self._store.fail_model_call,
                run.course_id,
                request.call_id,
                error_code=error.code,
                error_detail=error.detail,
                elapsed_ms=_elapsed_ms(started),
            )
            raise error from exc

        warning_code: str | None = None
        warning_detail: str | None = None
        if usage.usage_source == "unavailable":
            warning_code = "model_usage_unavailable"
            warning_detail = "Provider returned content without token usage; reservation remains charged"
        await asyncio.to_thread(
            self._store.complete_model_call,
            run.course_id,
            request.call_id,
            usage=usage,
            elapsed_ms=_elapsed_ms(started),
            warning_code=warning_code,
            warning_detail=warning_detail,
        )

        # Verify the run is still active after the call settled.  A run that
        # was cancelled or moved to a terminal status during the provider
        # call must not publish its result silently.
        current_run = await asyncio.to_thread(
            self._store.get_agent_run, run.course_id, run.run_id
        )
        if current_run is None or current_run.status not in AGENT_RUN_ACTIVE_STATUSES:
            raise AuditedModelCallError(
                "Model response was audited but the agent run is no longer active",
                "agent_run_no_longer_active",
                True,
            )

        return AuditedTextResult(
            content=content,
            call_id=request.call_id,
            usage_source=usage.usage_source,
        )

    def _create_completion(
        self,
        messages: Sequence[Mapping[str, Any]],
        max_output_tokens: int,
        temperature: float | None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
            "max_tokens": max_output_tokens,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        return self._client.chat.completions.create(**kwargs)
