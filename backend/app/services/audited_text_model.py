"""The only V2 entry point for a course-scoped DeepSeek text request.

No D1a worker invokes this service yet. Keeping it injectable lets tests prove
that a rejected reservation makes zero provider calls, and makes later semantic
extraction use the same persistent audit/lease boundary by construction.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.db.sqlite_store import SqliteStore
from app.schemas.knowledge_jobs import KnowledgeJob
from app.schemas.model_calls import ModelCallReservationRequest, ModelCallUsage


@dataclass(frozen=True)
class AuditedModelCallError(Exception):
    """A visible model error that a knowledge-job handler can classify."""

    detail: str
    code: str
    retryable: bool

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True)
class AuditedTextResult:
    """Text and durable audit identity returned only after provider settlement."""

    content: str
    call_id: str
    usage_source: str


class AuditedDeepSeekTextModel:
    """Reserve → call once → settle an OpenAI-compatible text completion."""

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
        job: KnowledgeJob,
        *,
        lease_owner: str,
        purpose: str,
        messages: Sequence[Mapping[str, Any]],
        max_output_tokens: int,
        temperature: float | None = None,
    ) -> AuditedTextResult:
        """Make exactly one audited completion for a currently leased course job."""
        if (
            job.scope != "course"
            or job.target_source_revision is None
            or job.target_knowledge_revision is None
            or job.attempt < 1
        ):
            raise ValueError("Audited text calls require a claimed course-scoped knowledge job")
        if not lease_owner.strip() or not purpose.strip() or max_output_tokens <= 0:
            raise ValueError("lease_owner, purpose, and max_output_tokens are required")
        canonical_request = _canonical_request(
            model=self._model,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        request = ModelCallReservationRequest(
            call_id=str(uuid.uuid4()),
            course_id=job.course_id,
            job_id=job.job_id,
            lease_owner=lease_owner,
            job_attempt=job.attempt,
            source_revision=job.target_source_revision,
            knowledge_revision=job.target_knowledge_revision,
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
        audit = await asyncio.to_thread(self._store.reserve_model_call, request)
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
                job.course_id,
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
            job.course_id,
            request.call_id,
            usage=usage,
            elapsed_ms=_elapsed_ms(started),
            warning_code=warning_code,
            warning_detail=warning_detail,
        )
        lease_is_current = await asyncio.to_thread(
            self._store.has_current_knowledge_job_lease,
            course_id=job.course_id,
            job_id=job.job_id,
            attempt=job.attempt,
            lease_owner=lease_owner,
            source_revision=job.target_source_revision,
            knowledge_revision=job.target_knowledge_revision,
        )
        if not lease_is_current:
            raise AuditedModelCallError(
                "Model response was audited but the knowledge-job lease was lost before publication",
                "knowledge_job_lease_lost",
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


def build_audited_deepseek_text_model(
    store: SqliteStore,
    *,
    client: Any | None = None,
) -> AuditedDeepSeekTextModel:
    """Build the production wrapper with SDK retries explicitly disabled."""
    resolved_client = client or OpenAI(
        api_key=settings.deepseek_api_key or "placeholder",
        base_url=settings.deepseek_api_base,
        timeout=settings.knowledge_model_timeout_seconds,
        max_retries=0,
    )
    return AuditedDeepSeekTextModel(
        store,
        client=resolved_client,
        model=settings.deepseek_model,
        provider="deepseek",
        course_budget_tokens=settings.knowledge_course_default_token_budget,
    )


def _canonical_request(
    *,
    model: str,
    messages: Sequence[Mapping[str, Any]],
    max_output_tokens: int,
    temperature: float | None,
) -> bytes:
    """Encode standard chat inputs once for both fingerprint and estimate."""
    try:
        return json.dumps(
            {
                "model": model,
                "messages": list(messages),
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Audited text request must be JSON serializable") from exc


def _conservative_input_token_upper_bound(payload: bytes, *, message_count: int) -> int:
    """Use UTF-8 byte length plus fixed chat framing as a safe upper bound.

    This intentionally over-reserves non-ASCII material. D1b must split large
    evidence scopes; later production measurements can replace the estimator
    only with one that remains a true upper bound for the chosen provider.
    """
    return len(payload) + 32 + (8 * message_count)


def _extract_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise ValueError("Provider response has no first text choice") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Provider response has no non-empty text content")
    return content


def _extract_usage(response: Any) -> ModelCallUsage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return ModelCallUsage(usage_source="unavailable")
    input_tokens = _non_negative_int(getattr(usage, "prompt_tokens", None))
    output_tokens = _non_negative_int(getattr(usage, "completion_tokens", None))
    total_tokens = _non_negative_int(getattr(usage, "total_tokens", None))
    reasoning_details = getattr(usage, "completion_tokens_details", None)
    reasoning_tokens = _non_negative_int(
        getattr(reasoning_details, "reasoning_tokens", None)
        if reasoning_details is not None
        else getattr(usage, "reasoning_tokens", None)
    )
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    if total_tokens is None:
        return ModelCallUsage(usage_source="unavailable")
    return ModelCallUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        usage_source="provider",
    )


def _non_negative_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _classify_provider_error(exc: Exception) -> AuditedModelCallError:
    detail = f"{type(exc).__name__}: {str(exc)[:500]}"
    status_code = getattr(exc, "status_code", None)
    if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
        return AuditedModelCallError(detail, "model_timeout", True)
    if status_code == 429:
        return AuditedModelCallError(detail, "model_rate_limited", True)
    if isinstance(status_code, int) and status_code >= 500:
        return AuditedModelCallError(detail, "model_provider_server_error", True)
    if isinstance(status_code, int) and 400 <= status_code < 500:
        return AuditedModelCallError(detail, "model_provider_request_error", False)
    if "connection" in type(exc).__name__.lower():
        return AuditedModelCallError(detail, "model_connection_error", True)
    if isinstance(exc, ValueError):
        return AuditedModelCallError(detail, "invalid_model_response", True)
    return AuditedModelCallError(detail, "model_provider_error", True)
