"""Focused contracts for the read-only V2 Agent tool facade."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.course_projection import CourseOutline
from app.schemas.evidence import EvidenceRef, SourceFragment
from app.schemas.knowledge_components import KnowledgeComponent
from app.schemas.kc_relations import KCRelation
from app.schemas.retrieval_answer import RetrievalOutcome
from app.schemas.terms import Term
from app.services import v2_agent_tools
from app.services.v2_agent_tools import V2AgentTools


def _fragment(*, course_id: str = "linear", revision: int = 1) -> SourceFragment:
    return SourceFragment(
        fragment_id="fragment-1",
        course_id=course_id,
        material_id="lecture-1",
        material_revision=revision,
        ordinal=0,
        text="特征值是满足 Av = λv 的标量 λ。",
        heading_path=["第二章 特征值"],
        page_start=2,
        page_end=2,
        char_start=0,
        char_end=20,
        kind="paragraph",
        parser_name="test",
        content_hash="content-hash",
    )


def _evidence(fragment: SourceFragment) -> EvidenceRef:
    return EvidenceRef.from_source_fragment(fragment)


def test_search_evidence_delegates_to_current_retriever_without_vector_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = object()
    expected = RetrievalOutcome(
        course_id="linear",
        confidence="out_of_scope",
        relevance=0,
        coverage=0,
    )
    captured: dict[str, object] = {}

    def fake_retrieve(*args: object, **kwargs: object) -> RetrievalOutcome:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(v2_agent_tools, "retrieve_current_fragments", fake_retrieve)

    result = V2AgentTools(store).search_evidence(
        "linear", "特征值", limit=2, selected_material_ids=["lecture-1"]
    )

    assert result is expected
    assert captured["args"] == (store, "linear", "特征值")
    assert captured["kwargs"] == {
        "limit": 2,
        "selected_material_ids": ["lecture-1"],
        "enable_vector": False,
    }


def test_open_evidence_requires_matching_current_fragment_identity() -> None:
    fragment = _fragment()

    class Store:
        def get_current_ready_source_fragment_preview(
            self, course_id: str, fragment_id: str
        ) -> tuple[SourceFragment, str] | None:
            assert (course_id, fragment_id) == ("linear", "fragment-1")
            return fragment, "lecture-1.md"

    tools = V2AgentTools(Store())

    preview = tools.open_evidence("linear", _evidence(fragment))

    assert preview is not None
    assert preview.file_name == "lecture-1.md"
    assert preview.locator == "第二章 特征值；p.2"
    assert tools.open_evidence("linear", _evidence(_fragment(revision=2))) is None
    with pytest.raises(ValueError, match="does not belong"):
        tools.open_evidence("linear", _evidence(_fragment(course_id="other")))


def test_current_outline_is_hidden_until_current_projection_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outline = CourseOutline(
        course_id="linear",
        source_revision="source-r1",
        knowledge_revision="knowledge-r1",
        compiler_version="d0",
        fragment_count=0,
    )

    class Store:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def get_current_course_outline(self, course_id: str, source_revision: str) -> CourseOutline:
            self.calls.append((course_id, source_revision))
            return outline

    store = Store()
    tools = V2AgentTools(store)
    monkeypatch.setattr(
        v2_agent_tools,
        "build_knowledge_status",
        lambda _store, _course_id: SimpleNamespace(
            projection_status="stale", source_revision="source-r1"
        ),
    )
    assert tools.get_current_outline("linear") is None
    assert store.calls == []

    monkeypatch.setattr(
        v2_agent_tools,
        "build_knowledge_status",
        lambda _store, _course_id: SimpleNamespace(
            projection_status="ready", source_revision="source-r1"
        ),
    )
    assert tools.get_current_outline("linear") == outline
    assert store.calls == [("linear", "source-r1")]


def test_current_terms_and_components_are_filtered_to_status_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _evidence(_fragment())
    current_term = Term(
        term_id="term-current",
        course_id="linear",
        source_revision="source-r1",
        knowledge_revision="knowledge-r1",
        canonical_name="特征值",
        canonical_key="特征值",
        term_kind="definition",
        definition="特征值是满足 Av = λv 的标量 λ。",
        definition_atom_id="atom-current",
        supporting_atom_ids=["atom-current"],
        evidence=[evidence],
    )
    stale_term = current_term.model_copy(
        update={"term_id": "term-stale", "knowledge_revision": "knowledge-old"}
    )
    current_component = KnowledgeComponent(
        kc_id="kc-current",
        course_id="linear",
        source_revision="source-r1",
        knowledge_revision="knowledge-r1",
        term_id=current_term.term_id,
        name=current_term.canonical_name,
        kind="definition",
        definition=current_term.definition,
        section_id="section-1",
        evidence=[evidence],
    )
    foreign_component = current_component.model_copy(
        update={"kc_id": "kc-foreign", "course_id": "other"}
    )

    class Store:
        def __init__(self) -> None:
            self.term_calls: list[tuple[str, str]] = []
            self.component_calls: list[tuple[str, str]] = []

        def get_current_terms(self, course_id: str, source_revision: str) -> list[Term]:
            self.term_calls.append((course_id, source_revision))
            return [current_term, stale_term]

        def get_current_knowledge_components(
            self, course_id: str, source_revision: str
        ) -> list[KnowledgeComponent]:
            self.component_calls.append((course_id, source_revision))
            return [current_component, foreign_component]

    store = Store()
    monkeypatch.setattr(
        v2_agent_tools,
        "build_knowledge_status",
        lambda _store, _course_id: SimpleNamespace(
            projection_status="ready",
            source_revision="source-r1",
            knowledge_revision="knowledge-r1",
        ),
    )
    tools = V2AgentTools(store)

    assert tools.get_current_terms("linear") == [current_term]
    assert tools.get_current_knowledge_components("linear") == [current_component]
    assert store.term_calls == [("linear", "source-r1")]
    assert store.component_calls == [("linear", "source-r1")]


def test_current_terms_and_components_hide_incomplete_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Store:
        def get_current_terms(self, *_args: str) -> list[Term]:
            pytest.fail("stale projection must not read terms")

        def get_current_knowledge_components(self, *_args: str) -> list[KnowledgeComponent]:
            pytest.fail("stale projection must not read components")

    monkeypatch.setattr(
        v2_agent_tools,
        "build_knowledge_status",
        lambda _store, _course_id: SimpleNamespace(
            projection_status="stale",
            source_revision="source-r1",
            knowledge_revision="knowledge-r1",
        ),
    )
    tools = V2AgentTools(Store())

    assert tools.get_current_terms("linear") == []
    assert tools.get_current_knowledge_components("linear") == []


def test_current_relations_are_filtered_to_status_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _evidence(_fragment())
    current = KCRelation(
        relation_id="relation-current", course_id="linear", source_revision="source-r1",
        knowledge_revision="knowledge-r1", source_kc_id="kc-a", target_kc_id="kc-b",
        relation_type="related", evidence=evidence, model_call_id="audit-1",
    )
    stale = current.model_copy(update={"relation_id": "relation-stale", "knowledge_revision": "old"})

    class Store:
        def get_current_kc_relations(self, course_id: str, source_revision: str) -> list[KCRelation]:
            assert (course_id, source_revision) == ("linear", "source-r1")
            return [current, stale]

    monkeypatch.setattr(
        v2_agent_tools,
        "build_knowledge_status",
        lambda _store, _course_id: SimpleNamespace(
            projection_status="ready", source_revision="source-r1", knowledge_revision="knowledge-r1"
        ),
    )
    assert V2AgentTools(Store()).get_current_kc_relations("linear") == [current]
