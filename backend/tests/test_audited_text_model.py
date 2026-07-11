"""D1a model-call auditing tests. Every provider is a local fake."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.evidence import SourceFragment
from app.schemas.foxsay import Course, Material
from app.services.audited_text_model import (
    AuditedDeepSeekTextModel,
    AuditedModelCallError,
    AuditedTextResult,
    build_audited_deepseek_text_model,
)
from app.services.knowledge_jobs import enqueue_course_compile_job, enqueue_material_index_job
from app.services.knowledge_status import build_knowledge_status


class FakeProviderError(Exception):
    def __init__(self, status_code: int, message: str = "synthetic provider error") -> None:
        super().__init__(message)
        self.status_code = status_code


class FakeClient:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        if callable(self.outcome):
            return self.outcome()
        return self.outcome


def _response(*, usage: Any = None, content: str = "可追溯的结果") -> Any:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage
    )


def _usage(*, prompt: int = 12, completion: int = 7, total: int = 19, reasoning: int = 3) -> Any:
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    result = SqliteStore(tmp_path / "audited-text-model.db")
    result.create_course(Course(id="linear", title="线性代数", status="empty"))
    result.create_material(
        Material(
            id="vectors",
            course_id="linear",
            filename="vectors.md",
            kind="text_note",
            status="ready",
            revision=1,
            content_hash="vectors-hash",
        )
    )
    result.replace_source_fragments(
        "linear",
        "vectors",
        1,
        [
            SourceFragment(
                fragment_id="linear-vectors-0",
                course_id="linear",
                material_id="vectors",
                material_revision=1,
                ordinal=0,
                text="向量空间对线性组合封闭。",
                heading_path=["向量空间"],
                char_start=0,
                char_end=12,
                kind="paragraph",
                parser_name="synthetic-d1a",
                content_hash="vectors-hash",
            )
        ],
    )
    index_job = enqueue_material_index_job(
        result, course_id="linear", material_id="vectors", revision=1
    )
    claimed = result.claim_next_knowledge_job("seed-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == index_job.job_id
    result.complete_knowledge_job("linear", index_job.job_id, "seed-worker")
    yield result
    result.close()


def _claim_course_job(
    store: SqliteStore, *, token_budget: int = 1000, max_attempts: int = 3
):
    manifest = store.get_compilable_source_manifest("linear")
    assert manifest is not None
    job = enqueue_course_compile_job(
        store,
        course_id="linear",
        source_revision=manifest[0],
        token_budget=token_budget,
        max_attempts=max_attempts,
    )
    claimed = store.claim_next_knowledge_job("model-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == job.job_id
    return claimed


async def test_audited_text_completion_persists_provider_usage_and_status_budget(
    store: SqliteStore,
) -> None:
    job = _claim_course_job(store)
    client = FakeClient(_response(usage=_usage()))
    model = AuditedDeepSeekTextModel(
        store, client=client, model="deepseek-v4-flash", course_budget_tokens=500
    )

    result = await model.complete(
        job,
        lease_owner="model-worker",
        purpose="semantic_atom_extract",
        messages=[{"role": "user", "content": "只提取给定片段。"}],
        max_output_tokens=40,
    )

    assert result.content == "可追溯的结果"
    assert len(client.calls) == 1
    audit = store.get_model_call_audit("linear", result.call_id)
    assert audit is not None
    assert audit.status == "succeeded"
    assert audit.call_kind == "text"
    assert audit.job_id == job.job_id
    assert audit.job_attempt == 1
    assert audit.source_revision == job.target_source_revision
    assert audit.knowledge_revision == job.target_knowledge_revision
    assert audit.input_tokens == 12
    assert audit.output_tokens == 7
    assert audit.reasoning_tokens == 3
    assert audit.total_tokens == audit.accounted_tokens == 19
    assert audit.usage_source == "provider"
    assert audit.elapsed_ms is not None
    assert audit.request_fingerprint != "只提取给定片段。"
    assert len(audit.request_fingerprint) == 64
    status = build_knowledge_status(store, "linear")
    assert status.model_budget is not None
    assert status.model_budget.token_budget == 500
    assert status.model_budget.accounted_tokens == 19
    assert status.model_budget.available_tokens == 481


async def test_budget_rejection_is_audited_before_the_fake_provider_is_called(
    store: SqliteStore,
) -> None:
    job = _claim_course_job(store, token_budget=1000)
    client = FakeClient(_response(usage=_usage()))
    model = AuditedDeepSeekTextModel(
        store, client=client, model="deepseek-v4-flash", course_budget_tokens=1
    )

    with pytest.raises(AuditedModelCallError, match="budget") as exc_info:
        await model.complete(
            job,
            lease_owner="model-worker",
            purpose="semantic_atom_extract",
            messages=[{"role": "user", "content": "x"}],
            max_output_tokens=1,
        )

    assert exc_info.value.code == "token_budget_exhausted"
    assert client.calls == []
    audits = store.list_model_call_audits("linear", job_id=job.job_id)
    assert len(audits) == 1
    assert audits[0].status == "rejected"
    assert audits[0].accounted_tokens == 0
    assert store.get_course_model_budget("linear", job.target_source_revision or "") is not None


@pytest.mark.parametrize(
    ("outcome", "expected_code", "retryable"),
    [
        (TimeoutError("synthetic timeout"), "model_timeout", True),
        (FakeProviderError(429), "model_rate_limited", True),
        (FakeProviderError(503), "model_provider_server_error", True),
        (FakeProviderError(400), "model_provider_request_error", False),
        (_response(usage=_usage(), content=""), "invalid_model_response", True),
    ],
)
async def test_provider_failures_are_visible_and_keep_their_reservation(
    store: SqliteStore,
    outcome: Any,
    expected_code: str,
    retryable: bool,
) -> None:
    job = _claim_course_job(store)
    client = FakeClient(outcome)
    model = AuditedDeepSeekTextModel(
        store, client=client, model="deepseek-v4-flash", course_budget_tokens=500
    )

    with pytest.raises(AuditedModelCallError) as exc_info:
        await model.complete(
            job,
            lease_owner="model-worker",
            purpose="semantic_atom_extract",
            messages=[{"role": "user", "content": "片段"}],
            max_output_tokens=40,
        )

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is retryable
    audit = store.list_model_call_audits("linear", job_id=job.job_id)[0]
    assert audit.status == "failed"
    assert audit.error_code == expected_code
    assert audit.usage_source == "unavailable"
    assert audit.accounted_tokens == audit.reserved_tokens
    status = build_knowledge_status(store, "linear")
    assert status.model_budget is not None
    assert status.model_budget.last_error_code == expected_code


async def test_usage_missing_keeps_reservation_and_exposes_a_warning(store: SqliteStore) -> None:
    job = _claim_course_job(store)
    client = FakeClient(_response(usage=None))
    model = AuditedDeepSeekTextModel(
        store, client=client, model="deepseek-v4-flash", course_budget_tokens=500
    )

    result = await model.complete(
        job,
        lease_owner="model-worker",
        purpose="semantic_atom_extract",
        messages=[{"role": "user", "content": "片段"}],
        max_output_tokens=40,
    )

    audit = store.get_model_call_audit("linear", result.call_id)
    assert audit is not None
    assert audit.status == "succeeded"
    assert audit.usage_source == "unavailable"
    assert audit.accounted_tokens == audit.reserved_tokens
    assert audit.error_code == "model_usage_unavailable"


async def test_lost_lease_after_audited_provider_response_cannot_be_used(store: SqliteStore) -> None:
    job = _claim_course_job(store)

    def expire_lease() -> Any:
        store._conn.execute(
            "UPDATE knowledge_jobs SET lease_expires_at = datetime('now', '-1 second') WHERE job_id = ?",
            (job.job_id,),
        )
        store._conn.commit()
        return _response(usage=_usage())

    client = FakeClient(expire_lease)
    model = AuditedDeepSeekTextModel(
        store, client=client, model="deepseek-v4-flash", course_budget_tokens=500
    )

    with pytest.raises(AuditedModelCallError) as exc_info:
        await model.complete(
            job,
            lease_owner="model-worker",
            purpose="semantic_atom_extract",
            messages=[{"role": "user", "content": "片段"}],
            max_output_tokens=40,
        )

    assert exc_info.value.code == "knowledge_job_lease_lost"
    audit = store.list_model_call_audits("linear", job_id=job.job_id)[0]
    assert audit.status == "succeeded"
    assert audit.total_tokens == 19


async def test_stale_course_source_is_rejected_before_the_fake_provider_is_called(
    store: SqliteStore,
) -> None:
    job = _claim_course_job(store)
    store._conn.execute("UPDATE materials SET content_hash = 'new-vectors-hash' WHERE id = 'vectors'")
    store._conn.commit()
    client = FakeClient(_response(usage=_usage()))
    model = AuditedDeepSeekTextModel(
        store, client=client, model="deepseek-v4-flash", course_budget_tokens=500
    )

    with pytest.raises(AuditedModelCallError) as exc_info:
        await model.complete(
            job,
            lease_owner="model-worker",
            purpose="semantic_atom_extract",
            messages=[{"role": "user", "content": "片段"}],
            max_output_tokens=40,
        )

    assert exc_info.value.code == "stale_course_source_revision"
    assert client.calls == []
    audit = store.list_model_call_audits("linear", job_id=job.job_id)[0]
    assert audit.status == "rejected"
    assert audit.error_code == "stale_course_source_revision"


async def test_concurrent_reservations_cannot_exceed_the_same_course_job_cap(
    store: SqliteStore,
) -> None:
    job = _claim_course_job(store, token_budget=1000)
    client = FakeClient(_response(usage=None))
    model = AuditedDeepSeekTextModel(
        store, client=client, model="deepseek-v4-flash", course_budget_tokens=250
    )
    request = dict(
        lease_owner="model-worker",
        purpose="semantic_atom_extract",
        messages=[{"role": "user", "content": "x"}],
        max_output_tokens=1,
    )

    outcomes = await asyncio.gather(
        model.complete(job, **request),
        model.complete(job, **request),
        return_exceptions=True,
    )

    assert sum(isinstance(item, AuditedTextResult) for item in outcomes) == 1
    failures = [item for item in outcomes if isinstance(item, AuditedModelCallError)]
    assert len(failures) == 1 and failures[0].code == "token_budget_exhausted"
    assert len(client.calls) == 1


def test_production_factory_disables_openai_sdk_retries(
    store: SqliteStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> FakeClient:
        captured.update(kwargs)
        return FakeClient(_response(usage=_usage()))

    monkeypatch.setattr("app.services.audited_text_model.OpenAI", fake_openai)
    model = build_audited_deepseek_text_model(store)

    assert isinstance(model, AuditedDeepSeekTextModel)
    assert captured["max_retries"] == 0
    assert captured["timeout"] > 0
