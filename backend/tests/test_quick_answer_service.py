"""V2-F2 quick-answer service tests.

All providers are fakes; no external model or embedding is ever contacted.
These tests verify the four honest CRAG states (grounded / ambiguous /
out_of_scope+supplementary / unavailable), citation forgery rejection,
course isolation, stale-revision detection, budget gating, and provider
failure visibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.evidence import SourceFragment
from app.schemas.foxsay import Course, Material
from app.services.audited_chat_writer import AuditedChatWriter
from app.services.knowledge_jobs import enqueue_material_index_job
from app.services.quick_answer_service import QuickAnswerService


# ---------------------------------------------------------------------------
# Fake provider client
# ---------------------------------------------------------------------------


class FakeProviderError(Exception):
    """An exception with an HTTP-style status_code for error classification."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class FakeWriterClient:
    """A fake OpenAI-compatible client that returns canned JSON or raises."""

    def __init__(
        self,
        *,
        content: str = "",
        error: Exception | None = None,
        on_call: Any = None,
    ) -> None:
        self._content = content
        self._error = error
        self._on_call = on_call
        self.call_count = 0
        self.calls: list[dict[str, Any]] = []

    @property
    def chat(self) -> "FakeWriterClient":
        return self

    @property
    def completions(self) -> "FakeWriterClient":
        return self

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        self.call_count += 1
        if self._on_call is not None:
            self._on_call()
        if self._error is not None:
            raise self._error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


class FakeVectorStore:
    """A fake Qdrant store for vector-search tests."""

    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self._hits = hits
        self.calls: list[dict[str, Any]] = []

    def search_source_fragments(
        self,
        course_id: str,
        query_embedding: list[float],
        material_scopes: list[tuple[str, int]],
        limit: int,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {"course_id": course_id, "material_scopes": material_scopes, "limit": limit}
        )
        return self._hits


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fragment(
    fragment_id: str,
    *,
    course_id: str,
    material_id: str,
    text: str,
    heading: str = "第一章",
    ordinal: int = 0,
    content_hash: str = "frag-hash",
    revision: int = 1,
) -> SourceFragment:
    return SourceFragment(
        fragment_id=fragment_id,
        course_id=course_id,
        material_id=material_id,
        material_revision=revision,
        ordinal=ordinal,
        text=text,
        heading_path=[heading],
        char_start=ordinal * 100,
        char_end=ordinal * 100 + len(text),
        kind="paragraph",
        parser_name="quick-answer-test",
        content_hash=content_hash,
    )


def _vector_payload(source: SourceFragment, score: float) -> dict[str, Any]:
    return {
        "score": score,
        "payload": {
            "type": "source_fragment",
            "course_id": source.course_id,
            "fragment_id": source.fragment_id,
            "material_id": source.material_id,
            "material_revision": source.material_revision,
            "content_hash": source.content_hash,
        },
    }


def _seed_course(store: SqliteStore, *, course_id: str, title: str, session_id: str) -> None:
    store.create_course(Course(id=course_id, title=title, status="empty"))
    store.create_chat_session(session_id, course_id, "对话")


def _seed_ready_material(
    store: SqliteStore,
    *,
    course_id: str,
    material_id: str,
    filename: str,
    content_hash: str,
    fragments: list[SourceFragment],
    worker: str = "test-worker",
) -> None:
    store.create_material(
        Material(
            id=material_id,
            course_id=course_id,
            filename=filename,
            kind="text_note",
            status="processing",
            revision=1,
            content_hash=content_hash,
        )
    )
    job = enqueue_material_index_job(
        store, course_id=course_id, material_id=material_id, revision=1
    )
    claimed = store.claim_next_knowledge_job(worker, lease_seconds=60)
    assert claimed is not None and claimed.job_id == job.job_id
    store.replace_source_fragments(course_id, material_id, 1, fragments)
    store.update_material_status_if_revision(course_id, material_id, 1, "ready")
    store.complete_knowledge_job(course_id, job.job_id, worker)


def _seed_processing_material(
    store: SqliteStore,
    *,
    course_id: str,
    material_id: str,
    filename: str,
    content_hash: str,
    worker: str = "test-worker",
) -> None:
    """Create a material with a claimed-but-incomplete index job (processing)."""
    store.create_material(
        Material(
            id=material_id,
            course_id=course_id,
            filename=filename,
            kind="text_note",
            status="processing",
            revision=1,
            content_hash=content_hash,
        )
    )
    job = enqueue_material_index_job(
        store, course_id=course_id, material_id=material_id, revision=1
    )
    claimed = store.claim_next_knowledge_job(worker, lease_seconds=60)
    assert claimed is not None and claimed.job_id == job.job_id


def _writer_json(answer: str, citation_ids: list[str] | None = None) -> str:
    return json.dumps(
        {"answer": answer, "citation_fragment_ids": citation_ids or []},
        ensure_ascii=False,
    )


def _make_service(
    store: SqliteStore,
    client: FakeWriterClient,
    *,
    course_budget_tokens: int = 100000,
    max_output_tokens: int = 1024,
    default_token_budget: int = 10000,
) -> QuickAnswerService:
    writer = AuditedChatWriter(
        store,
        client=client,
        model="deepseek-v4-flash",
        course_budget_tokens=course_budget_tokens,
    )
    return QuickAnswerService(
        store,
        writer,
        max_output_tokens=max_output_tokens,
        default_token_budget=default_token_budget,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    db = SqliteStore(tmp_path / "quick-answer.db")
    yield db
    db.close()


# ---------------------------------------------------------------------------
# 1. grounded answer
# ---------------------------------------------------------------------------


async def test_grounded_answer_produces_material_envelope_with_citations(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="alpha", title="测试课程 A", session_id="sess-a")
    frag = _fragment(
        "alpha-frag-0",
        course_id="alpha",
        material_id="mat-a",
        text="若 Av = λv，则 λ 是特征值。",
        heading="特征值",
        content_hash="alpha-hash",
    )
    _seed_ready_material(
        store,
        course_id="alpha",
        material_id="mat-a",
        filename="lecture-a.md",
        content_hash="alpha-hash",
        fragments=[frag],
    )

    client = FakeWriterClient(
        content=_writer_json("特征值由方程 Av = λv 定义。", ["alpha-frag-0"]),
    )
    service = _make_service(store, client)

    result = await service.answer(
        course_id="alpha",
        session_id="sess-a",
        turn_id="turn-1",
        query="特征值",
    )

    assert result.run_status == "completed"
    assert client.call_count == 1
    envelope = result.envelope
    assert envelope.answer_source == "material"
    assert envelope.confidence_status == "grounded"
    assert len(envelope.citations) == 1
    assert envelope.citations[0].evidence.fragment_id == "alpha-frag-0"
    assert envelope.citations[0].file_name == "lecture-a.md"

    # AgentRun + AgentStep records persisted.
    run = store.get_agent_run("alpha", result.run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.workflow_kind == "quick_answer"
    steps = store.get_agent_steps(result.run_id)
    assert len(steps) == 3
    assert all(step.status == "completed" for step in steps)
    # Writer step has a model_call_id.
    writer_steps = [s for s in steps if s.step_type == "generate"]
    assert len(writer_steps) == 1
    assert writer_steps[0].model_call_id is not None


# ---------------------------------------------------------------------------
# 2. ambiguous answer
# ---------------------------------------------------------------------------


async def test_ambiguous_answer_includes_caveat_citations(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="amb", title="模糊课程", session_id="sess-amb")
    frag = _fragment(
        "amb-frag-0",
        course_id="amb",
        material_id="mat-amb",
        text="若 Av = λv，则 λ 是特征值。",
        heading="特征值",
        content_hash="amb-hash",
    )
    _seed_ready_material(
        store,
        course_id="amb",
        material_id="mat-amb",
        filename="lecture-amb.md",
        content_hash="amb-hash",
        fragments=[frag],
    )

    client = FakeWriterClient(
        content=_writer_json("根据部分材料，特征值大致由 Av = λv 定义。", ["amb-frag-0"]),
    )
    service = _make_service(store, client)

    result = await service.answer(
        course_id="amb",
        session_id="sess-amb",
        turn_id="turn-amb",
        query="请解释这个概念",
        enable_vector=True,
        qdrant_store=FakeVectorStore([_vector_payload(frag, 0.60)]),
        embed_query=lambda _: [0.1, 0.2, 0.3],
    )

    assert result.run_status == "completed"
    assert client.call_count == 1
    envelope = result.envelope
    assert envelope.confidence_status == "ambiguous"
    assert envelope.answer_source == "material"
    assert len(envelope.citations) == 1
    assert envelope.citations[0].evidence.fragment_id == "amb-frag-0"


# ---------------------------------------------------------------------------
# 3. out_of_scope answer
# ---------------------------------------------------------------------------


async def test_out_of_scope_produces_supplementary_answer_with_empty_context(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="oos", title="范围外课程", session_id="sess-oos")
    frag = _fragment(
        "oos-frag-0",
        course_id="oos",
        material_id="mat-oos",
        text="若 Av = λv，则 λ 是特征值。",
        heading="特征值",
        content_hash="oos-hash",
    )
    _seed_ready_material(
        store,
        course_id="oos",
        material_id="mat-oos",
        filename="lecture-oos.md",
        content_hash="oos-hash",
        fragments=[frag],
    )

    client = FakeWriterClient(
        content=_writer_json(
            "课程材料未覆盖此内容，以下为通用理解。", []
        ),
    )
    service = _make_service(store, client)

    result = await service.answer(
        course_id="oos",
        session_id="sess-oos",
        turn_id="turn-oos",
        query="什么是量子力学",
    )

    assert result.run_status == "completed"
    assert client.call_count == 1
    # Writer was called with empty context.
    user_msg = client.calls[0]["messages"][1]["content"]
    assert "未覆盖此内容" in user_msg
    assert "（无）" in user_msg
    envelope = result.envelope
    assert envelope.confidence_status == "out_of_scope"
    assert envelope.answer_source == "supplementary"
    assert envelope.citations == []


# ---------------------------------------------------------------------------
# 4. unavailable retrieval
# ---------------------------------------------------------------------------


async def test_unavailable_retrieval_returns_error_envelope_without_model_call(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="unavail", title="不可用课程", session_id="sess-u")
    _seed_processing_material(
        store,
        course_id="unavail",
        material_id="mat-u",
        filename="lecture-u.md",
        content_hash="unavail-hash",
    )

    client = FakeWriterClient(content="should not be called")
    service = _make_service(store, client)

    result = await service.answer(
        course_id="unavail",
        session_id="sess-u",
        turn_id="turn-u",
        query="任何问题",
    )

    assert client.call_count == 0
    envelope = result.envelope
    assert envelope.retrieval_availability == "unavailable"
    assert envelope.confidence_status is None
    assert envelope.answer_source == "supplementary"
    assert envelope.citations == []
    assert envelope.error is not None
    assert envelope.error.error_code == "source_evidence_unavailable"
    assert result.run_status == "completed"

    # Only the retrieval step was recorded.
    steps = store.get_agent_steps(result.run_id)
    assert len(steps) == 1
    assert steps[0].step_type == "retrieve"


# ---------------------------------------------------------------------------
# 5. forged citation rejection
# ---------------------------------------------------------------------------


async def test_forged_citation_fragment_id_is_silently_dropped(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="forge", title="伪造课程", session_id="sess-f")
    frag = _fragment(
        "forge-frag-0",
        course_id="forge",
        material_id="mat-f",
        text="若 Av = λv，则 λ 是特征值。",
        heading="特征值",
        content_hash="forge-hash",
    )
    _seed_ready_material(
        store,
        course_id="forge",
        material_id="mat-f",
        filename="lecture-f.md",
        content_hash="forge-hash",
        fragments=[frag],
    )

    client = FakeWriterClient(
        content=_writer_json(
            "特征值由方程 Av = λv 定义。",
            ["forge-frag-0", "forged-fake-id"],
        ),
    )
    service = _make_service(store, client)

    result = await service.answer(
        course_id="forge",
        session_id="sess-f",
        turn_id="turn-f",
        query="特征值",
    )

    envelope = result.envelope
    assert envelope.answer_source == "material"
    assert len(envelope.citations) == 1
    assert envelope.citations[0].evidence.fragment_id == "forge-frag-0"
    # Forged ID is visible as a warning.
    forged_warnings = [
        w for w in envelope.warnings
        if w.warning_code == "unknown_citation_selection"
        and w.fragment_id == "forged-fake-id"
    ]
    assert len(forged_warnings) == 1


# ---------------------------------------------------------------------------
# 6. cross-course isolation
# ---------------------------------------------------------------------------


async def test_cross_course_fragments_never_appear_in_hits_or_citations(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="cc-a", title="课程 A", session_id="sess-cca")
    _seed_course(store, course_id="cc-b", title="课程 B", session_id="sess-ccb")
    frag_a = _fragment(
        "cc-a-frag-0",
        course_id="cc-a",
        material_id="mat-cca",
        text="课程 A 的特征值定义。",
        heading="特征值",
        content_hash="cca-hash",
    )
    frag_b = _fragment(
        "cc-b-frag-0",
        course_id="cc-b",
        material_id="mat-ccb",
        text="课程 B 的离散数学内容。",
        heading="离散数学",
        content_hash="ccb-hash",
    )
    _seed_ready_material(
        store,
        course_id="cc-a",
        material_id="mat-cca",
        filename="lecture-a.md",
        content_hash="cca-hash",
        fragments=[frag_a],
    )
    _seed_ready_material(
        store,
        course_id="cc-b",
        material_id="mat-ccb",
        filename="lecture-b.md",
        content_hash="ccb-hash",
        fragments=[frag_b],
    )

    # Writer tries to cite BOTH courses' fragments.
    client = FakeWriterClient(
        content=_writer_json(
            "课程 A 的特征值定义。",
            ["cc-a-frag-0", "cc-b-frag-0"],
        ),
    )
    service = _make_service(store, client)

    result = await service.answer(
        course_id="cc-a",
        session_id="sess-cca",
        turn_id="turn-cc",
        query="特征值",
    )

    envelope = result.envelope
    # Only course A's fragment is cited.
    cited_ids = {c.evidence.fragment_id for c in envelope.citations}
    assert cited_ids == {"cc-a-frag-0"}
    assert "cc-b-frag-0" not in cited_ids
    # Course B's fragment is rejected as unknown.
    cross_warnings = [
        w for w in envelope.warnings
        if w.fragment_id == "cc-b-frag-0"
    ]
    assert len(cross_warnings) == 1
    assert cross_warnings[0].warning_code == "unknown_citation_selection"
    # Evidence pack only contains course A's hits.
    assert all(
        h.evidence.course_id == "cc-a" for h in result.evidence.selected_hits
    )


# ---------------------------------------------------------------------------
# 7. stale revision
# ---------------------------------------------------------------------------


async def test_stale_source_revision_marks_run_stale(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="stale", title="过期课程", session_id="sess-stale")
    frag = _fragment(
        "stale-frag-0",
        course_id="stale",
        material_id="mat-stale",
        text="若 Av = λv，则 λ 是特征值。",
        heading="特征值",
        content_hash="stale-hash",
    )
    _seed_ready_material(
        store,
        course_id="stale",
        material_id="mat-stale",
        filename="lecture-stale.md",
        content_hash="stale-hash",
        fragments=[frag],
    )

    def add_extra_material() -> None:
        """Simulate a new material upload during the writer call."""
        store.create_material(
            Material(
                id="mat-extra",
                course_id="stale",
                filename="extra.md",
                kind="text_note",
                status="processing",
                revision=1,
                content_hash="stale-extra-hash",
            )
        )

    client = FakeWriterClient(
        content=_writer_json("特征值由方程 Av = λv 定义。", ["stale-frag-0"]),
        on_call=add_extra_material,
    )
    service = _make_service(store, client)

    result = await service.answer(
        course_id="stale",
        session_id="sess-stale",
        turn_id="turn-stale",
        query="特征值",
    )

    assert result.run_status == "stale"
    assert any("source revision changed" in w.lower() for w in result.warnings)
    # The answer was still assembled.
    assert result.envelope.answer_source == "material"
    assert len(result.envelope.citations) == 1
    # Run is persisted as stale.
    run = store.get_agent_run("stale", result.run_id)
    assert run is not None
    assert run.status == "stale"
    assert run.error_code == "stale_source_revision"


# ---------------------------------------------------------------------------
# 8. budget exceeded
# ---------------------------------------------------------------------------


async def test_budget_exceeded_makes_no_provider_call_and_marks_run_failed(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="budget", title="预算课程", session_id="sess-budget")
    frag = _fragment(
        "budget-frag-0",
        course_id="budget",
        material_id="mat-budget",
        text="若 Av = λv，则 λ 是特征值。",
        heading="特征值",
        content_hash="budget-hash",
    )
    _seed_ready_material(
        store,
        course_id="budget",
        material_id="mat-budget",
        filename="lecture-budget.md",
        content_hash="budget-hash",
        fragments=[frag],
    )

    client = FakeWriterClient(content="should not be called")
    service = _make_service(store, client)

    result = await service.answer(
        course_id="budget",
        session_id="sess-budget",
        turn_id="turn-budget",
        query="特征值",
        token_budget=5,  # far too small for any reservation
    )

    assert client.call_count == 0
    assert result.run_status == "failed"
    assert result.error_code == "token_budget_exhausted"
    envelope = result.envelope
    assert envelope.answer_source == "supplementary"
    assert envelope.citations == []
    # Run persisted as failed.
    run = store.get_agent_run("budget", result.run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.error_code == "token_budget_exhausted"


# ---------------------------------------------------------------------------
# 9. provider failure
# ---------------------------------------------------------------------------


async def test_provider_failure_marks_run_failed_and_error_is_visible(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="pfail", title="失败课程", session_id="sess-pfail")
    frag = _fragment(
        "pfail-frag-0",
        course_id="pfail",
        material_id="mat-pfail",
        text="若 Av = λv，则 λ 是特征值。",
        heading="特征值",
        content_hash="pfail-hash",
    )
    _seed_ready_material(
        store,
        course_id="pfail",
        material_id="mat-pfail",
        filename="lecture-pfail.md",
        content_hash="pfail-hash",
        fragments=[frag],
    )

    client = FakeWriterClient(
        error=FakeProviderError("rate limited", status_code=429),
    )
    service = _make_service(store, client)

    result = await service.answer(
        course_id="pfail",
        session_id="sess-pfail",
        turn_id="turn-pfail",
        query="特征值",
    )

    assert client.call_count == 1  # provider WAS contacted
    assert result.run_status == "failed"
    assert result.error_code == "model_rate_limited"
    envelope = result.envelope
    assert envelope.answer_source == "supplementary"
    assert envelope.citations == []
    assert "rate limited" in envelope.answer or result.error_detail is not None
    # Run persisted as failed.
    run = store.get_agent_run("pfail", result.run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.error_code == "model_rate_limited"
    # Model call audit records the failure.
    writer_steps = [
        s for s in store.get_agent_steps(result.run_id) if s.step_type == "generate"
    ]
    assert len(writer_steps) == 1
    assert writer_steps[0].status == "failed"


# ---------------------------------------------------------------------------
# 10. empty selected material scope
# ---------------------------------------------------------------------------


async def test_empty_selected_material_scope_means_no_evidence_not_all_materials(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="emptyscope", title="空选课", session_id="sess-es")
    frag = _fragment(
        "es-frag-0",
        course_id="emptyscope",
        material_id="mat-es",
        text="若 Av = λv，则 λ 是特征值。",
        heading="特征值",
        content_hash="es-hash",
    )
    _seed_ready_material(
        store,
        course_id="emptyscope",
        material_id="mat-es",
        filename="lecture-es.md",
        content_hash="es-hash",
        fragments=[frag],
    )

    client = FakeWriterClient(content="should not be called")
    service = _make_service(store, client)

    result = await service.answer(
        course_id="emptyscope",
        session_id="sess-es",
        turn_id="turn-es",
        query="特征值",
        selected_material_ids=[],  # empty list = no evidence
    )

    assert client.call_count == 0
    envelope = result.envelope
    assert envelope.retrieval_availability == "unavailable"
    assert envelope.error is not None
    assert envelope.error.error_code == "selected_scope_has_no_ready_evidence"
    assert result.run_status == "completed"


# ---------------------------------------------------------------------------
# Bonus: malformed JSON fallback
# ---------------------------------------------------------------------------


async def test_malformed_writer_json_falls_back_to_raw_text_without_citations(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="malformed", title="格式错误", session_id="sess-m")
    frag = _fragment(
        "m-frag-0",
        course_id="malformed",
        material_id="mat-m",
        text="若 Av = λv，则 λ 是特征值。",
        heading="特征值",
        content_hash="m-hash",
    )
    _seed_ready_material(
        store,
        course_id="malformed",
        material_id="mat-m",
        filename="lecture-m.md",
        content_hash="m-hash",
        fragments=[frag],
    )

    client = FakeWriterClient(content="This is not JSON at all.")
    service = _make_service(store, client)

    result = await service.answer(
        course_id="malformed",
        session_id="sess-m",
        turn_id="turn-m",
        query="特征值",
    )

    assert result.run_status == "completed"
    # Raw text used as answer.
    assert result.envelope.answer == "This is not JSON at all."
    # No valid citation IDs were returned, so the assembler falls back to
    # the full allowed evidence pack (a grounded answer must never be
    # an uncited material claim).
    assert len(result.envelope.citations) == 1
    assert result.envelope.citations[0].evidence.fragment_id == "m-frag-0"
    # A warning about malformed JSON is present in the service result.
    assert any("not valid JSON" in w for w in result.warnings)
    # The assembler also recorded the fallback.
    assert any(
        w.warning_code == "fallback_to_allowed_evidence"
        for w in result.envelope.warnings
    )


# ---------------------------------------------------------------------------
# Bonus: cross-course session rejection
# ---------------------------------------------------------------------------


async def test_cross_course_session_is_rejected_before_any_work(
    store: SqliteStore,
) -> None:
    _seed_course(store, course_id="xvalid", title="有效课程", session_id="sess-xvalid")
    _seed_course(store, course_id="xother", title="其他课程", session_id="sess-xother")

    client = FakeWriterClient(content="should not be called")
    service = _make_service(store, client)

    with pytest.raises(ValueError, match="does not belong"):
        await service.answer(
            course_id="xvalid",
            session_id="sess-xother",  # belongs to xother, not xvalid
            turn_id="turn-x",
            query="任何问题",
        )

    assert client.call_count == 0
