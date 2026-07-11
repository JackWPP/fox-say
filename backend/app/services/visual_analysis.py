"""Controlled V2-E visual completion for explicitly selected parser assets.

The result table is deliberately not a source-fragment or knowledge fact. A
future projection may turn an accepted result into evidence; until then this
handler only provides audited, revision-pinned visual recovery.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.db.sqlite_store import SqliteStore
from app.schemas.knowledge_jobs import KnowledgeJob
from app.schemas.model_calls import ModelCallReservationRequest
from app.services.audited_text_model import (
    AuditedModelCallError,
    _classify_provider_error,
    _extract_content,
    _extract_usage,
)
from app.services.knowledge_worker import KnowledgeJobExecutionError


_PROMPT = (
    "Recover only the visual information that text parsing could not reliably preserve. "
    "State visible labels, equations, table values, and diagram relationships. "
    "Do not infer facts that are not visible. Return concise Markdown only."
)


class VisualAnalysis:
    """Run one persisted, explicit asset selection through the configured VLM."""

    def __init__(
        self,
        store: SqliteStore,
        *,
        enabled: bool | None = None,
        client: Any | None = None,
    ) -> None:
        self._store = store
        self._enabled = settings.knowledge_visual_analysis_enabled if enabled is None else enabled
        self._client = client

    async def __call__(self, job: KnowledgeJob) -> None:
        if (
            job.job_type != "visual_analysis" or job.scope != "course"
            or job.target_source_revision is None or job.target_knowledge_revision is None
            or job.lease_owner is None
        ):
            raise KnowledgeJobExecutionError(
                "Visual analysis received an invalid claimed course job",
                code="invalid_visual_analysis_job",
                retryable=False,
            )
        if not self._enabled:
            raise KnowledgeJobExecutionError(
                "Visual analysis is disabled; set KNOWLEDGE_VISUAL_ANALYSIS_ENABLED=true to permit VLM calls",
                code="visual_analysis_disabled",
                retryable=False,
            )
        if not settings.resolved_vlm_api_key.strip():
            raise KnowledgeJobExecutionError(
                "VLM_API_KEY is not configured for visual analysis",
                code="visual_model_not_configured",
                retryable=False,
            )
        manifest = self._store.get_compilable_source_manifest(job.course_id)
        if manifest is None or manifest[0] != job.target_source_revision:
            raise KnowledgeJobExecutionError(
                "Course source revision changed before visual analysis",
                code="stale_course_source_revision",
                retryable=False,
            )
        requests = self._store.get_visual_analysis_requests(job.course_id, job.job_id)
        if not requests or len(requests) > settings.knowledge_visual_max_assets_per_job:
            raise KnowledgeJobExecutionError(
                "Visual analysis request has no assets or exceeds its configured asset cap",
                code="invalid_visual_asset_selection",
                retryable=False,
            )
        results: list[dict[str, str]] = []
        for request in requests:
            try:
                data_url, digest = await asyncio.to_thread(_load_asset_data_url, request["storage_path"])
                call_id, content = await self._analyse_one(
                    job, asset_id=request["asset_id"], reason_code=request["reason_code"],
                    data_url=data_url, asset_digest=digest,
                )
            except AuditedModelCallError as exc:
                raise KnowledgeJobExecutionError(exc.detail, code=exc.code, retryable=exc.retryable) from exc
            except ValueError as exc:
                raise KnowledgeJobExecutionError(str(exc), code="visual_asset_unavailable", retryable=False) from exc
            results.append({"asset_id": request["asset_id"], "model_call_id": call_id, "analysis_text": content})
        published = self._store.publish_visual_analysis_results_if_current(
            course_id=job.course_id,
            job_id=job.job_id,
            job_attempt=job.attempt,
            lease_owner=job.lease_owner,
            source_revision=job.target_source_revision,
            knowledge_revision=job.target_knowledge_revision,
            results=results,
        )
        if not published:
            if not self._store.has_current_knowledge_job_lease(
                course_id=job.course_id,
                job_id=job.job_id,
                attempt=job.attempt,
                lease_owner=job.lease_owner,
                source_revision=job.target_source_revision,
                knowledge_revision=job.target_knowledge_revision,
            ):
                raise KnowledgeJobExecutionError(
                    "Visual analysis lost its knowledge-job lease before publication",
                    code="knowledge_job_lease_lost",
                    retryable=True,
                )
            raise KnowledgeJobExecutionError(
                "Course source revision or visual-analysis lease changed before publication",
                code="stale_visual_analysis_revision",
                retryable=False,
            )

    async def _analyse_one(
        self,
        job: KnowledgeJob,
        *,
        asset_id: str,
        reason_code: str,
        data_url: str,
        asset_digest: str,
    ) -> tuple[str, str]:
        assert job.lease_owner is not None
        request_fingerprint = hashlib.sha256(
            json.dumps(
                {"model": settings.vlm_model, "asset_sha256": asset_digest, "reason": reason_code,
                 "max_tokens": settings.vlm_max_tokens, "prompt": _PROMPT},
                sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        reservation = ModelCallReservationRequest(
            call_id=str(uuid.uuid4()),
            course_id=job.course_id,
            job_id=job.job_id,
            lease_owner=job.lease_owner,
            job_attempt=job.attempt,
            source_revision=job.target_source_revision or "",
            knowledge_revision=job.target_knowledge_revision or "",
            call_kind="vision",
            purpose="visual_analysis",
            provider="siliconflow",
            model=settings.vlm_model,
            request_fingerprint=request_fingerprint,
            # The provider's image-token accounting is settled from its response.
            # This configurable pre-reservation is intentionally charged even if
            # the response omits usage, so a missing bill never becomes free.
            input_token_upper_bound=settings.knowledge_visual_input_token_reserve,
            max_output_tokens=settings.vlm_max_tokens,
            course_budget_tokens=settings.knowledge_course_default_token_budget,
        )
        audit = await asyncio.to_thread(self._store.reserve_model_call, reservation)
        if audit.status == "rejected":
            raise AuditedModelCallError(
                audit.error_detail or "Visual model call was rejected before contacting the provider",
                audit.error_code or "model_call_rejected", False,
            )
        started = time.monotonic()
        try:
            response = await asyncio.to_thread(
                self._client_or_create().chat.completions.create,
                model=settings.vlm_model,
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": f"Reason: {reason_code}. {_PROMPT}"},
                ]}],
                max_tokens=settings.vlm_max_tokens,
                temperature=0.0,
                extra_body={"enable_thinking": False},
            )
            content = _extract_content(response)
            usage = _extract_usage(response)
        except Exception as exc:
            error = _classify_provider_error(exc)
            await asyncio.to_thread(
                self._store.fail_model_call, job.course_id, reservation.call_id,
                error_code=error.code, error_detail=error.detail,
                elapsed_ms=max(0, round((time.monotonic() - started) * 1000)),
            )
            raise error from exc
        await asyncio.to_thread(
            self._store.complete_model_call, job.course_id, reservation.call_id,
            usage=usage, elapsed_ms=max(0, round((time.monotonic() - started) * 1000)),
            warning_code="model_usage_unavailable" if usage.usage_source == "unavailable" else None,
            warning_detail="Provider returned visual output without token usage; reservation remains charged"
            if usage.usage_source == "unavailable" else None,
        )
        return reservation.call_id, content

    def _client_or_create(self) -> Any:
        if self._client is None:
            self._client = OpenAI(
                api_key=settings.resolved_vlm_api_key,
                base_url=settings.resolved_vlm_api_base,
                timeout=settings.knowledge_model_timeout_seconds,
                max_retries=0,
            )
        return self._client


def _load_asset_data_url(storage_path: str) -> tuple[str, str]:
    root = Path(settings.upload_root).resolve()
    candidate = (root / storage_path).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError("Visual asset path escapes the configured upload root")
    if not candidate.is_file():
        raise ValueError("Visual asset file is unavailable")
    data = candidate.read_bytes()
    if not data:
        raise ValueError("Visual asset file is empty")
    suffix = candidate.suffix.lower()
    mime_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(suffix)
    if mime_type is None:
        raise ValueError("Visual asset has an unsupported image format")
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}", hashlib.sha256(data).hexdigest()
