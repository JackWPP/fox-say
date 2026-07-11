"""V2-F5 deep-dive service tests (8 scenarios from §10 of the design doc).

All providers are fakes; no external model or embedding is ever contacted.
These tests verify the bounded multi-agent workflow: Scout -> Mapper ->
Tutor -> Verifier, with graceful degradation, citation forgery rejection,
budget exhaustion, and the four honest CRAG states.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.course_projection import CourseOutline, CourseOutlineSection
from app.schemas.evidence import EvidenceRef, SourceFragment
from app.schemas.foxsay import Course, Material
from app.schemas.kc_relations import KCRelation
from app.schemas.knowledge_components import KnowledgeComponent
from app.schemas.terms import Term
from app.services.audited_chat_writer import AuditedChatWriter
from app.services.deep_dive_service import DeepDiveService
from app.services.knowledge_jobs import enqueue_material_index_job
from app.services.v2_agent_tools import V2AgentTools


# ---------------------------------------------------------------------------
# Fake provider client (multi-call: returns different content per call)
# ---------------------------------------------------------------------------


class FakeProviderError(Exception):
    """An exception with an HTTP-style status_code for error classification."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class FakeMultiCallClient:
    """A fake OpenAI-compatible client that returns canned JSON per call.

    ``contents`` is a list of response contents, consumed in order.
    ``errors`` is a parallel list of exceptions (or None) to raise instead.
    """

    def __init__(
        self,
        *,
        contents: list[str] | None = None,
        errors: list[Exception | None] | None = None,
    ) -> None:
        self._contents = contents or []
        self._errors: list[Exception | None] = (
            errors if errors is not None else [None] * len(self._contents)
        )
        self.call_count = 0
        self.calls: list[dict[str, Any]] = []

    @property
    def chat(self) -> "FakeMultiCallClient":
        return self

    @property
    def completions(self) -> "FakeMultiCallClient":
        return self

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        idx = self.call_count
        self.call_count += 1
        err = self._errors[idx] if idx < len(self._errors) else None
        if err is not None:
            raise err
        content = self._contents[idx] if idx < len(self._contents) else ""
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
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
# Fake projection tools
# ---------------------------------------------------------------------------


class FakeProjectionTools(V2AgentTools):
    """Fake V2AgentTools that returns canned projection data."""

    def __init__(
        self,
        store: SqliteStore,
        *,
        outline: CourseOutline | None = None,
        terms: list[Term] | None = None,
        kcs: list[KnowledgeComponent] | None = None,
        relations: list[KCRelation] | None = None,
    ) -> None:
        super().__init__(store)
        self._outline = outline
        self._terms = terms or []
        self._kcs = kcs or []
        self._relations = relations or []

    def get_current_outline(self, course_id: str) -> CourseOutline | None:
        return self._outline

    def get_current_terms(self, course_id: str) -> list[Term]:
        return self._terms

    def get_current_knowledge_components(self, course_id: str) -> list[KnowledgeComponent]:
        return self._kcs

    def get_current_kc_relations(self, course_id: str) -> list[KCRelation]:
        return self._relations


# ---------------------------------------------------------------------------
# Seed helpers
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
        parser_name="deep-dive-test",
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


def _mapper_json() -> str:
    return json.dumps(
        {
            "relevant_sections": [
                {"section_id": "sec_a", "title": "向量空间", "relevance_reason": "定义线性无关"},
                {"section_id": "sec_b", "title": "矩阵与方程组", "relevance_reason": "定义满秩"},
            ],
            "relevant_kcs": [
                {"kc_id": "kc_li", "name": "线性无关", "role": "source_concept"},
                {"kc_id": "kc_fr", "name": "满秩", "role": "target_concept"},
                {"kc_id": "kc_inv", "name": "可逆", "role": "bridge_concept"},
            ],
            "key_relationships": [
                {
                    "description": "线性无关的向量组构成满秩矩阵",
                    "involved_kc_ids": ["kc_li", "kc_fr"],
                    "evidence_supported": True,
                },
                {
                    "description": "满秩矩阵是可逆的",
                    "involved_kc_ids": ["kc_fr", "kc_inv"],
                    "evidence_supported": True,
                },
            ],
            "narrative_bridge": "线性无关、满秩和可逆是矩阵性质的三个递进层次。",
        },
        ensure_ascii=False,
    )


def _tutor_json(answer: str, citation_ids: list[str]) -> str:
    return json.dumps(
        {"answer": answer, "citation_fragment_ids": citation_ids},
        ensure_ascii=False,
    )


def _make_projection(
    course_id: str,
    source_revision: str,
    knowledge_revision: str,
    *,
    evidence: list[EvidenceRef],
) -> tuple[CourseOutline, list[Term], list[KnowledgeComponent], list[KCRelation]]:
    """Create canned projection data for tests."""
    outline = CourseOutline(
        course_id=course_id,
        source_revision=source_revision,
        knowledge_revision=knowledge_revision,
        compiler_version="d0-test",
        sections=[
            CourseOutlineSection(
                section_id="sec_a",
                title="向量空间",
                heading_path=["第一章 向量空间"],
                ordinal=0,
                evidence=evidence[:1] if evidence else [evidence[0]],
            ),
            CourseOutlineSection(
                section_id="sec_b",
                title="矩阵与方程组",
                heading_path=["第二章 矩阵与方程组"],
                ordinal=1,
                evidence=evidence[1:] if len(evidence) > 1 else evidence[:1],
            ),
        ],
        fragment_count=len(evidence),
    )

    terms = [
        Term(
            term_id="term_li",
            course_id=course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            canonical_name="线性无关",
            canonical_key="线性无关",
            term_kind="definition",
            definition="线性无关是向量组的一个性质。",
            definition_atom_id="atom_li",
            supporting_atom_ids=["atom_li"],
            evidence=evidence[:1],
        ),
        Term(
            term_id="term_fr",
            course_id=course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            canonical_name="满秩",
            canonical_key="满秩",
            term_kind="definition",
            definition="满秩是矩阵的一个性质。",
            definition_atom_id="atom_fr",
            supporting_atom_ids=["atom_fr"],
            evidence=evidence[1:2] if len(evidence) > 1 else evidence[:1],
        ),
        Term(
            term_id="term_inv",
            course_id=course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            canonical_name="可逆",
            canonical_key="可逆",
            term_kind="definition",
            definition="可逆是矩阵的一个性质。",
            definition_atom_id="atom_inv",
            supporting_atom_ids=["atom_inv"],
            evidence=evidence[1:2] if len(evidence) > 1 else evidence[:1],
        ),
    ]

    kcs = [
        KnowledgeComponent(
            kc_id="kc_li",
            course_id=course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            term_id="term_li",
            name="线性无关",
            kind="definition",
            definition="线性无关是向量组的一个性质。",
            section_id="sec_a",
            evidence=evidence[:1],
        ),
        KnowledgeComponent(
            kc_id="kc_fr",
            course_id=course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            term_id="term_fr",
            name="满秩",
            kind="definition",
            definition="满秩是矩阵的一个性质。",
            section_id="sec_b",
            evidence=evidence[1:2] if len(evidence) > 1 else evidence[:1],
        ),
        KnowledgeComponent(
            kc_id="kc_inv",
            course_id=course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            term_id="term_inv",
            name="可逆",
            kind="definition",
            definition="可逆是矩阵的一个性质。",
            section_id="sec_b",
            evidence=evidence[1:2] if len(evidence) > 1 else evidence[:1],
        ),
    ]

    relations = [
        KCRelation(
            relation_id="rel_1",
            course_id=course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            source_kc_id="kc_li",
            target_kc_id="kc_fr",
            relation_type="prerequisite",
            evidence=evidence[0],
            model_call_id="audit-rel-1",
        ),
        KCRelation(
            relation_id="rel_2",
            course_id=course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            source_kc_id="kc_fr",
            target_kc_id="kc_inv",
            relation_type="related",
            evidence=evidence[0],
            model_call_id="audit-rel-2",
        ),
    ]

    return outline, terms, kcs, relations


def _make_service(
    store: SqliteStore,
    client: FakeMultiCallClient,
    tools: V2AgentTools,
    *,
    course_budget_tokens: int = 100000,
    default_token_budget: int = 20000,
) -> DeepDiveService:
    writer = AuditedChatWriter(
        store,
        client=client,
        model="deepseek-v4-flash",
        course_budget_tokens=course_budget_tokens,
    )
    return DeepDiveService(
        store,
        writer,
        tools,
        default_token_budget=default_token_budget,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    db = SqliteStore(tmp_path / "deep-dive.db")
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Scenario 1: Successful deep-dive with grounded evidence
# ---------------------------------------------------------------------------


async def test_successful_deep_dive_with_grounded_evidence(store: SqliteStore) -> None:
    """Mapper + Tutor both succeed; grounded retrieval with multi-material evidence."""
    _seed_course(store, course_id="linalg", title="线性代数", session_id="sess-la")
    frag_a = _fragment(
        "frag_a_1",
        course_id="linalg",
        material_id="mat_a",
        text="线性无关是向量组的性质：若 c1v1 + ... + cnvn = 0 仅当 ci = 0。",
        heading="线性无关",
        content_hash="hash-a",
    )
    frag_b = _fragment(
        "frag_b_2",
        course_id="linalg",
        material_id="mat_b",
        text="满秩矩阵的秩等于矩阵的行数或列数。",
        heading="满秩",
        content_hash="hash-b",
    )
    _seed_ready_material(
        store,
        course_id="linalg",
        material_id="mat_a",
        filename="lecture-a.md",
        content_hash="hash-a",
        fragments=[frag_a],
    )
    _seed_ready_material(
        store,
        course_id="linalg",
        material_id="mat_b",
        filename="lecture-b.md",
        content_hash="hash-b",
        fragments=[frag_b],
    )

    evidence = [EvidenceRef.from_source_fragment(frag_a), EvidenceRef.from_source_fragment(frag_b)]
    outline, terms, kcs, relations = _make_projection(
        "linalg", "source-r1", "knowledge-r1", evidence=evidence
    )
    tools = FakeProjectionTools(
        store, outline=outline, terms=terms, kcs=kcs, relations=relations
    )

    client = FakeMultiCallClient(
        contents=[_mapper_json(), _tutor_json("线性无关、满秩和可逆是三个递进性质。", ["frag_a_1", "frag_b_2"])],
    )
    service = _make_service(store, client, tools)

    result = await service.answer(
        course_id="linalg",
        session_id="sess-la",
        turn_id="turn-1",
        query="线性无关、满秩和可逆之间是什么关系？",
    )

    assert result.run_status == "completed"
    assert result.mapper_ran is True
    assert client.call_count == 2  # mapper + tutor
    envelope = result.envelope
    assert envelope.confidence_status == "grounded"
    assert envelope.answer_source == "material"
    assert len(envelope.citations) == 2

    # AgentRun has 4 steps: scout, mapper, tutor, verifier (all completed).
    steps = store.get_agent_steps(result.run_id)
    assert len(steps) == 4
    assert all(step.status == "completed" for step in steps)
    roles = {step.agent_role for step in steps}
    assert roles == {"scout", "mapper", "tutor", "verifier"}

    # 2 generate steps with model_call_ids.
    gen_steps = [s for s in steps if s.step_type == "generate"]
    assert len(gen_steps) == 2
    assert all(s.model_call_id is not None for s in gen_steps)


# ---------------------------------------------------------------------------
# Scenario 2: Ambiguous retrieval with successful mapper
# ---------------------------------------------------------------------------


async def test_ambiguous_retrieval_with_successful_mapper(store: SqliteStore) -> None:
    """Ambiguous confidence is preserved; mapper adds structure, citations still exist."""
    _seed_course(store, course_id="amb", title="模糊课程", session_id="sess-amb")
    frag_a = _fragment(
        "amb_frag_a",
        course_id="amb",
        material_id="mat_amb_a",
        text="线性无关的定义。",
        heading="向量空间",
        content_hash="amb-hash-a",
    )
    frag_b = _fragment(
        "amb_frag_b",
        course_id="amb",
        material_id="mat_amb_b",
        text="满秩矩阵的定义。",
        heading="矩阵",
        content_hash="amb-hash-b",
    )
    _seed_ready_material(
        store,
        course_id="amb",
        material_id="mat_amb_a",
        filename="lecture-a.md",
        content_hash="amb-hash-a",
        fragments=[frag_a],
    )
    _seed_ready_material(
        store,
        course_id="amb",
        material_id="mat_amb_b",
        filename="lecture-b.md",
        content_hash="amb-hash-b",
        fragments=[frag_b],
    )

    evidence = [EvidenceRef.from_source_fragment(frag_a), EvidenceRef.from_source_fragment(frag_b)]
    outline, terms, kcs, relations = _make_projection(
        "amb", "source-r1", "knowledge-r1", evidence=evidence
    )
    tools = FakeProjectionTools(
        store, outline=outline, terms=terms, kcs=kcs, relations=relations
    )

    client = FakeMultiCallClient(
        contents=[_mapper_json(), _tutor_json("根据部分材料，这些概念相关。", ["amb_frag_a"])],
    )
    service = _make_service(store, client, tools)

    result = await service.answer(
        course_id="amb",
        session_id="sess-amb",
        turn_id="turn-amb",
        query="线性无关和满秩之间有什么关系",
        enable_vector=True,
        qdrant_store=FakeVectorStore(
            [_vector_payload(frag_a, 0.62), _vector_payload(frag_b, 0.60)]
        ),
        embed_query=lambda _: [0.1, 0.2, 0.3],
    )

    assert result.run_status == "completed"
    assert result.mapper_ran is True
    envelope = result.envelope
    # Original retrieval confidence is preserved.
    assert envelope.confidence_status == "ambiguous"
    # Mapper added structure, citations still exist -> material answer.
    assert envelope.answer_source == "material"
    assert len(envelope.citations) >= 1


# ---------------------------------------------------------------------------
# Scenario 3: Mapper fails -> degradation to quick-answer style
# ---------------------------------------------------------------------------


async def test_mapper_failure_degrades_to_quick_answer_style(store: SqliteStore) -> None:
    """Mapper model call fails; tutor still called with evidence only."""
    _seed_course(store, course_id="degrade", title="降级课程", session_id="sess-deg")
    frag = _fragment(
        "deg_frag_0",
        course_id="degrade",
        material_id="mat_deg",
        text="线性无关是向量组的性质。",
        heading="线性无关",
        content_hash="deg-hash",
    )
    _seed_ready_material(
        store,
        course_id="degrade",
        material_id="mat_deg",
        filename="lecture.md",
        content_hash="deg-hash",
        fragments=[frag],
    )

    evidence = [EvidenceRef.from_source_fragment(frag)]
    outline, terms, kcs, relations = _make_projection(
        "degrade", "source-r1", "knowledge-r1", evidence=evidence
    )
    tools = FakeProjectionTools(
        store, outline=outline, terms=terms, kcs=kcs, relations=relations
    )

    client = FakeMultiCallClient(
        contents=["", _tutor_json("基于证据的回答。", ["deg_frag_0"])],
        errors=[FakeProviderError("rate limited", 429), None],
    )
    service = _make_service(store, client, tools)

    result = await service.answer(
        course_id="degrade",
        session_id="sess-deg",
        turn_id="turn-deg",
        query="线性无关和满秩之间有什么关系",
    )

    assert result.run_status == "completed"  # NOT failed
    assert result.mapper_ran is False
    assert client.call_count == 2  # mapper attempted, tutor succeeded
    assert any("Mapper phase failed" in w for w in result.warnings)
    # Tutor still produced a material answer.
    assert result.envelope.answer_source == "material"
    assert len(result.envelope.citations) == 1

    # Steps: scout (completed), mapper (failed), tutor (completed), verifier (completed).
    steps = store.get_agent_steps(result.run_id)
    assert len(steps) == 4
    mapper_steps = [s for s in steps if s.agent_role == "mapper"]
    assert len(mapper_steps) == 1
    assert mapper_steps[0].status == "failed"
    tutor_steps = [s for s in steps if s.agent_role == "tutor"]
    assert len(tutor_steps) == 1
    assert tutor_steps[0].status == "completed"


# ---------------------------------------------------------------------------
# Scenario 4: Both mapper and tutor fail -> unavailable envelope
# ---------------------------------------------------------------------------


async def test_double_failure_returns_unavailable_envelope(store: SqliteStore) -> None:
    """Both mapper and tutor model calls fail -> unavailable envelope."""
    _seed_course(store, course_id="dblfail", title="双失败课程", session_id="sess-df")
    frag = _fragment(
        "df_frag_0",
        course_id="dblfail",
        material_id="mat_df",
        text="线性无关的定义。",
        heading="线性无关",
        content_hash="df-hash",
    )
    _seed_ready_material(
        store,
        course_id="dblfail",
        material_id="mat_df",
        filename="lecture.md",
        content_hash="df-hash",
        fragments=[frag],
    )

    evidence = [EvidenceRef.from_source_fragment(frag)]
    outline, terms, kcs, relations = _make_projection(
        "dblfail", "source-r1", "knowledge-r1", evidence=evidence
    )
    tools = FakeProjectionTools(
        store, outline=outline, terms=terms, kcs=kcs, relations=relations
    )

    client = FakeMultiCallClient(
        contents=["", ""],
        errors=[
            FakeProviderError("rate limited", 429),
            FakeProviderError("server error", 500),
        ],
    )
    service = _make_service(store, client, tools)

    result = await service.answer(
        course_id="dblfail",
        session_id="sess-df",
        turn_id="turn-df",
        query="线性无关和满秩之间有什么关系",
    )

    assert result.run_status == "failed"
    assert result.mapper_ran is False
    envelope = result.envelope
    assert envelope.retrieval_availability == "unavailable"
    assert envelope.answer_source == "supplementary"
    assert envelope.citations == []
    assert envelope.error is not None

    # Steps: scout (completed), mapper (failed), tutor (failed), verifier (none).
    steps = store.get_agent_steps(result.run_id)
    step_roles = [(s.agent_role, s.status) for s in steps]
    assert ("scout", "completed") in step_roles
    assert ("mapper", "failed") in step_roles
    assert ("tutor", "failed") in step_roles


# ---------------------------------------------------------------------------
# Scenario 5: Projection not ready -> mapper skipped
# ---------------------------------------------------------------------------


async def test_projection_not_ready_skips_mapper(store: SqliteStore) -> None:
    """No Terms/KCs/Relations exist -> mapper skipped, tutor runs with evidence only."""
    _seed_course(store, course_id="noproj", title="无投影课程", session_id="sess-np")
    frag = _fragment(
        "np_frag_0",
        course_id="noproj",
        material_id="mat_np",
        text="论点组织是学术写作的核心。",
        heading="论点",
        content_hash="np-hash",
    )
    _seed_ready_material(
        store,
        course_id="noproj",
        material_id="mat_np",
        filename="lecture.md",
        content_hash="np-hash",
        fragments=[frag],
    )

    # FakeProjectionTools with no projection data.
    tools = FakeProjectionTools(store)

    client = FakeMultiCallClient(
        contents=[_tutor_json("论点组织和论据呈现是不同环节。", ["np_frag_0"])],
    )
    service = _make_service(store, client, tools)

    result = await service.answer(
        course_id="noproj",
        session_id="sess-np",
        turn_id="turn-np",
        query="论点组织和论据呈现有什么区别？",
    )

    assert result.run_status == "completed"
    assert result.mapper_ran is False
    # Only 1 model call (tutor; mapper was skipped, not attempted).
    assert client.call_count == 1
    assert result.envelope.answer_source == "material"
    assert len(result.envelope.citations) == 1
    # No mapper-failure warnings (it was deliberately skipped).
    assert not any("Mapper phase failed" in w for w in result.warnings)

    # Mapper step is "skipped", not "failed".
    steps = store.get_agent_steps(result.run_id)
    mapper_steps = [s for s in steps if s.agent_role == "mapper"]
    assert len(mapper_steps) == 1
    assert mapper_steps[0].status == "skipped"
    assert mapper_steps[0].error is not None
    assert "projection not ready" in mapper_steps[0].error.lower()


# ---------------------------------------------------------------------------
# Scenario 6: Citation forgery rejected
# ---------------------------------------------------------------------------


async def test_citation_forgery_is_silently_dropped(store: SqliteStore) -> None:
    """Tutor returns a forged fragment ID -> verifier drops it with a warning."""
    _seed_course(store, course_id="forge", title="伪造课程", session_id="sess-fg")
    frag_a = _fragment(
        "forge_frag_a",
        course_id="forge",
        material_id="mat_fga",
        text="线性无关的定义。",
        heading="线性无关",
        content_hash="fga-hash",
    )
    frag_b = _fragment(
        "forge_frag_b",
        course_id="forge",
        material_id="mat_fgb",
        text="满秩矩阵的定义。",
        heading="满秩",
        content_hash="fgb-hash",
    )
    _seed_ready_material(
        store,
        course_id="forge",
        material_id="mat_fga",
        filename="lecture-a.md",
        content_hash="fga-hash",
        fragments=[frag_a],
    )
    _seed_ready_material(
        store,
        course_id="forge",
        material_id="mat_fgb",
        filename="lecture-b.md",
        content_hash="fgb-hash",
        fragments=[frag_b],
    )

    evidence = [EvidenceRef.from_source_fragment(frag_a), EvidenceRef.from_source_fragment(frag_b)]
    outline, terms, kcs, relations = _make_projection(
        "forge", "source-r1", "knowledge-r1", evidence=evidence
    )
    tools = FakeProjectionTools(
        store, outline=outline, terms=terms, kcs=kcs, relations=relations
    )

    client = FakeMultiCallClient(
        contents=[
            _mapper_json(),
            _tutor_json("回答文本。", ["forge_frag_a", "fake_frag_id", "forge_frag_b"]),
        ],
    )
    service = _make_service(store, client, tools)

    result = await service.answer(
        course_id="forge",
        session_id="sess-fg",
        turn_id="turn-fg",
        query="线性无关和满秩之间有什么关系",
    )

    assert result.run_status == "completed"
    envelope = result.envelope
    # Forged ID dropped; 2 valid citations remain.
    assert len(envelope.citations) == 2
    cited_ids = {c.evidence.fragment_id for c in envelope.citations}
    assert cited_ids == {"forge_frag_a", "forge_frag_b"}
    assert "fake_frag_id" not in cited_ids
    # Forged ID visible as a warning.
    forged_warnings = [
        w for w in envelope.warnings
        if w.warning_code == "unknown_citation_selection"
        and w.fragment_id == "fake_frag_id"
    ]
    assert len(forged_warnings) == 1


# ---------------------------------------------------------------------------
# Scenario 7: Budget exhaustion rejects both calls
# ---------------------------------------------------------------------------


async def test_budget_exhaustion_rejects_both_calls(store: SqliteStore) -> None:
    """token_budget too small -> both mapper and tutor rejected -> unavailable."""
    _seed_course(store, course_id="budget", title="预算课程", session_id="sess-bg")
    frag = _fragment(
        "bg_frag_0",
        course_id="budget",
        material_id="mat_bg",
        text="线性无关的定义。",
        heading="线性无关",
        content_hash="bg-hash",
    )
    _seed_ready_material(
        store,
        course_id="budget",
        material_id="mat_bg",
        filename="lecture.md",
        content_hash="bg-hash",
        fragments=[frag],
    )

    evidence = [EvidenceRef.from_source_fragment(frag)]
    outline, terms, kcs, relations = _make_projection(
        "budget", "source-r1", "knowledge-r1", evidence=evidence
    )
    tools = FakeProjectionTools(
        store, outline=outline, terms=terms, kcs=kcs, relations=relations
    )

    client = FakeMultiCallClient(contents=["should not be called", "should not be called"])
    service = _make_service(store, client, tools)

    result = await service.answer(
        course_id="budget",
        session_id="sess-bg",
        turn_id="turn-bg",
        query="线性无关和满秩之间有什么关系",
        token_budget=5,  # far too small for any reservation
    )

    assert client.call_count == 0  # provider never contacted
    assert result.run_status == "failed"
    assert result.error_code == "token_budget_exhausted"
    envelope = result.envelope
    assert envelope.retrieval_availability == "unavailable"
    assert envelope.answer_source == "supplementary"
    assert envelope.citations == []

    # Both mapper and tutor steps are failed.
    steps = store.get_agent_steps(result.run_id)
    gen_steps = [s for s in steps if s.step_type == "generate"]
    assert len(gen_steps) == 2
    assert all(s.status == "failed" for s in gen_steps)


# ---------------------------------------------------------------------------
# Scenario 8: Out-of-scope -> supplementary answer, no model calls
# ---------------------------------------------------------------------------


async def test_out_of_scope_returns_supplementary_without_model_calls(
    store: SqliteStore,
) -> None:
    """Out-of-scope retrieval -> skip mapper and tutor, return supplementary."""
    _seed_course(store, course_id="oos", title="范围外课程", session_id="sess-oos")
    frag = _fragment(
        "oos_frag_0",
        course_id="oos",
        material_id="mat_oos",
        text="线性代数的内容。",
        heading="线性代数",
        content_hash="oos-hash",
    )
    _seed_ready_material(
        store,
        course_id="oos",
        material_id="mat_oos",
        filename="lecture.md",
        content_hash="oos-hash",
        fragments=[frag],
    )

    tools = FakeProjectionTools(store)

    client = FakeMultiCallClient(contents=["should not be called", "should not be called"])
    service = _make_service(store, client, tools)

    result = await service.answer(
        course_id="oos",
        session_id="sess-oos",
        turn_id="turn-oos",
        query="光电效应和波粒二象性有什么关系？",
    )

    assert client.call_count == 0  # no model calls
    assert result.run_status == "completed"
    assert result.mapper_ran is False
    envelope = result.envelope
    assert envelope.confidence_status == "out_of_scope"
    assert envelope.answer_source == "supplementary"
    assert envelope.citations == []
    assert "未覆盖" in envelope.answer or "通用理解" in envelope.answer

    # Steps: scout (completed), mapper (skipped), tutor (skipped), verifier (completed).
    steps = store.get_agent_steps(result.run_id)
    step_map = {s.agent_role: s for s in steps}
    assert step_map["scout"].status == "completed"
    assert step_map["mapper"].status == "skipped"
    mapper_error = step_map["mapper"].error or ""
    assert "out_of_scope" in mapper_error
    assert step_map["tutor"].status == "skipped"
    assert step_map["verifier"].status == "completed"
