"""V2 fragment-first retrieval safety and CRAG tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient

from app.schemas.evidence import SourceFragment
from app.schemas.foxsay import Course, Material
from app.services import retrieval
from app.services.knowledge_jobs import enqueue_material_index_job
from app.services.source_fragments import build_source_fragments


COURSE_ID = "linear-algebra"


class FakeStore:
    def __init__(self, fragments: list[SourceFragment], *, course_exists: bool = True) -> None:
        self.fragments = {fragment.fragment_id: fragment for fragment in fragments}
        self.course_exists = course_exists
        self.list_calls: list[tuple[str, list[str] | None]] = []

    def get_course(self, course_id: str) -> object | None:
        return object() if self.course_exists and course_id == COURSE_ID else None

    def list_current_ready_source_fragments(
        self,
        course_id: str,
        *,
        fragment_ids: list[str] | None = None,
        material_ids: list[str] | None = None,
    ) -> list[SourceFragment]:
        assert course_id == COURSE_ID
        self.list_calls.append((course_id, material_ids))
        result = list(self.fragments.values())
        if fragment_ids is not None:
            result = [fragment for fragment in result if fragment.fragment_id in fragment_ids]
        if material_ids is not None:
            result = [fragment for fragment in result if fragment.material_id in material_ids]
        return sorted(result, key=lambda fragment: (fragment.material_id, fragment.ordinal))

    def get_current_ready_source_fragment_preview(
        self,
        course_id: str,
        fragment_id: str,
    ) -> tuple[SourceFragment, str] | None:
        fragment = self.fragments.get(fragment_id)
        if fragment is None or fragment.course_id != course_id:
            return None
        return fragment, f"{fragment.material_id}.md"


class FakeVectorStore:
    def __init__(self, response: list[dict[str, Any]] | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def search_source_fragments(
        self,
        course_id: str,
        query_embedding: list[float],
        material_scopes: list[tuple[str, int]],
        limit: int,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "course_id": course_id,
                "query_embedding": query_embedding,
                "material_scopes": material_scopes,
                "limit": limit,
            }
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def fragment(
    fragment_id: str,
    *,
    material_id: str = "lecture-a",
    revision: int = 1,
    ordinal: int = 0,
    text: str = "若 Av = λv，则 λ 是特征值。",
    heading_path: list[str] | None = None,
    content_hash: str | None = None,
    course_id: str = COURSE_ID,
) -> SourceFragment:
    return SourceFragment(
        fragment_id=fragment_id,
        course_id=course_id,
        material_id=material_id,
        material_revision=revision,
        ordinal=ordinal,
        text=text,
        heading_path=heading_path or ["第二章 特征值"],
        char_start=ordinal * 100,
        char_end=ordinal * 100 + len(text),
        kind="paragraph",
        parser_name="fragment-retrieval-test",
        content_hash=content_hash or f"hash-{fragment_id}",
    )


def status(
    *,
    source_status: str = "ready",
    total_materials: int = 1,
    ready_materials: int = 1,
    materials: list[object] | None = None,
) -> object:
    return SimpleNamespace(
        source_revision="src-linear-algebra",
        knowledge_revision=None,
        source_status=source_status,
        coverage=SimpleNamespace(
            total_materials=total_materials,
            ready_materials=ready_materials,
        ),
        materials=materials or [],
    )


def set_status(monkeypatch: pytest.MonkeyPatch, value: object) -> None:
    monkeypatch.setattr(retrieval, "build_knowledge_status", lambda _store, _course_id: value)


def payload(source: SourceFragment, score: float, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "source_fragment",
        "course_id": source.course_id,
        "fragment_id": source.fragment_id,
        "material_id": source.material_id,
        "material_revision": source.material_revision,
        "content_hash": source.content_hash,
    }
    value.update(overrides)
    return {"score": score, "payload": value}


def test_exact_grounded_result_skips_embedding_and_vector_when_limit_is_satisfied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = fragment("exact")
    store = FakeStore([source])
    vector = FakeVectorStore(RuntimeError("must not be called"))
    set_status(monkeypatch, status())

    def fail_embed(_: str) -> list[float]:
        pytest.fail("a complete grounded exact result must not embed")

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "特征值",
        limit=1,
        qdrant_store=vector,
        embed_query=fail_embed,
    )

    assert result.confidence == "grounded"
    assert result.error is None
    assert [hit.evidence.fragment_id for hit in result.hits] == [source.fragment_id]
    assert result.hits[0].channels == ["exact"]
    assert vector.calls == []


def test_numbered_heading_variant_matches_a_natural_language_question_without_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = fragment(
        "numbered-heading",
        heading_path=["第二章 特征值"],
        text="若 Av = λv，则 λ 是特征值。",
    )
    store = FakeStore([source])
    set_status(monkeypatch, status())

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "什么是特征值？",
        limit=1,
        qdrant_store=FakeVectorStore(RuntimeError("must not be called")),
        embed_query=lambda _: pytest.fail("number-stripped title hit must not embed"),
    )

    assert result.confidence == "grounded"
    assert result.hits[0].evidence.fragment_id == source.fragment_id
    assert result.hits[0].channels == ["exact"]


def test_exact_formula_matching_preserves_operators_and_only_folds_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plus = fragment("plus", text="A + B", heading_path=["矩阵运算"])
    store = FakeStore([plus])
    set_status(monkeypatch, status())

    matched = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "A+B",
        limit=1,
        embed_query=lambda _: pytest.fail("whitespace-only formula normalization must be exact"),
    )
    colliding = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "AB",
        enable_vector=False,
    )

    assert matched.confidence == "grounded"
    assert [hit.evidence.fragment_id for hit in matched.hits] == ["plus"]
    assert colliding.retrieval_availability == "available"
    assert colliding.confidence == "out_of_scope"
    assert colliding.hits == []


def test_vector_payloads_are_rehydrated_and_malformed_or_stale_ones_are_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = fragment("current")
    store = FakeStore([source])
    set_status(monkeypatch, status())
    vector = FakeVectorStore(
        [
            payload(source, 0.99, material_revision=0),
            payload(source, 0.98, course_id="other-course"),
            payload(source, 0.97, type="note"),
            payload(source, 0.965, fragment_id="unknown-fragment"),
            payload(source, 0.955, material_id="different-material"),
            payload(source, 0.945, content_hash="wrong-content-hash"),
            {"score": 0.96, "payload": {"fragment_id": source.fragment_id}},
            payload(source, 0.88),
        ]
    )

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "如何理解这一概念",
        qdrant_store=vector,
        embed_query=lambda _: [0.1, 0.2],
    )

    assert result.confidence == "grounded"
    assert [hit.evidence.fragment_id for hit in result.hits] == [source.fragment_id]
    assert result.hits[0].canonical_text == source.text
    assert result.hits[0].file_name == "lecture-a.md"
    assert [warning.warning_code for warning in result.warnings] == [
        "invalid_vector_payload_dropped"
    ]


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.72, "grounded"),
        (0.55, "ambiguous"),
        (0.54, "out_of_scope"),
    ],
)
def test_vector_crag_thresholds(
    monkeypatch: pytest.MonkeyPatch,
    score: float,
    expected: str,
) -> None:
    source = fragment("threshold")
    store = FakeStore([source])
    set_status(monkeypatch, status())
    vector = FakeVectorStore([payload(source, score)])

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "语义化问题",
        limit=1,
        qdrant_store=vector,
        embed_query=lambda _: [0.1],
    )

    assert result.confidence == expected
    assert result.relevance == score
    if expected == "out_of_scope":
        assert result.retrieval_availability == "available"
        assert result.hits == []
    else:
        assert [hit.evidence.fragment_id for hit in result.hits] == [source.fragment_id]


def test_vector_failure_is_an_error_without_exact_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = fragment("vector-failure")
    store = FakeStore([source])
    set_status(monkeypatch, status())

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "语义化问题",
        qdrant_store=FakeVectorStore(RuntimeError("qdrant unavailable")),
        embed_query=lambda _: [0.1],
    )

    assert result.confidence is None
    assert result.hits == []
    assert result.retrieval_availability == "unavailable"
    assert result.error is not None
    assert result.error.error_code == "source_fragment_vector_search_failed"


def test_vector_failure_keeps_exact_evidence_as_a_visible_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = fragment("exact-with-vector-failure")
    store = FakeStore([source])
    set_status(monkeypatch, status())

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "特征值",
        limit=2,
        qdrant_store=FakeVectorStore(RuntimeError("qdrant unavailable")),
        embed_query=lambda _: [0.1],
    )

    assert result.confidence == "grounded"
    assert result.error is None
    assert [hit.evidence.fragment_id for hit in result.hits] == [source.fragment_id]
    assert [warning.warning_code for warning in result.warnings] == [
        "source_fragment_vector_search_failed"
    ]


def test_same_text_in_different_materials_is_not_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = fragment("same-a", material_id="lecture-a", text="矩阵可对角化。")
    second = fragment("same-b", material_id="lecture-b", text="矩阵可对角化。")
    store = FakeStore([first, second])
    set_status(monkeypatch, status(total_materials=2, ready_materials=2))
    vector = FakeVectorStore([payload(first, 0.9), payload(second, 0.8)])

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "请解释这个结论",
        limit=2,
        qdrant_store=vector,
        embed_query=lambda _: [0.1],
    )

    assert [hit.evidence.fragment_id for hit in result.hits] == ["same-a", "same-b"]
    assert result.coverage == 1.0


def test_heading_neighbors_add_context_without_changing_crag_relevance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heading = ["第二章 谱理论"]
    before = fragment("before", ordinal=0, text="定义需要非零向量。", heading_path=heading)
    anchor = fragment("anchor", ordinal=1, text="Av = λv", heading_path=heading)
    after = fragment("after", ordinal=2, text="特征向量对应于该标量。", heading_path=heading)
    store = FakeStore([before, anchor, after])
    set_status(monkeypatch, status())

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "Av = λv",
        limit=3,
        qdrant_store=FakeVectorStore([]),
        embed_query=lambda _: [0.1],
    )

    assert result.confidence == "grounded"
    assert result.relevance == 0.98
    assert [hit.evidence.fragment_id for hit in result.hits] == ["anchor", "before", "after"]
    assert [hit.channels for hit in result.hits[1:]] == [
        ["heading_neighborhood"],
        ["heading_neighborhood"],
    ]
    assert [hit.score for hit in result.hits[1:]] == [0.71, 0.71]


def test_heading_neighbors_require_adjacent_ordinals_not_merely_adjacent_list_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heading = ["第二章 谱理论"]
    anchor = fragment("anchor-gap", ordinal=0, text="Av = λv", heading_path=heading)
    distant = fragment("distant-gap", ordinal=2, text="间隔片段。", heading_path=heading)
    store = FakeStore([anchor, distant])
    set_status(monkeypatch, status())

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "Av = λv",
        limit=2,
        qdrant_store=FakeVectorStore([]),
        embed_query=lambda _: [0.1],
    )

    assert result.confidence == "grounded"
    assert [hit.evidence.fragment_id for hit in result.hits] == ["anchor-gap"]


def test_selected_materials_only_shrink_canonical_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    included = fragment("included", material_id="lecture-a", text="向量空间。")
    excluded = fragment("excluded", material_id="lecture-b", text="向量空间。")
    store = FakeStore([included, excluded])
    set_status(monkeypatch, status(total_materials=2, ready_materials=2))
    vector = FakeVectorStore([payload(included, 0.9), payload(excluded, 0.99)])

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "语义化问题",
        selected_material_ids=["lecture-a"],
        qdrant_store=vector,
        embed_query=lambda _: [0.1],
    )

    assert [hit.evidence.fragment_id for hit in result.hits] == ["included"]
    assert vector.calls[0]["material_scopes"] == [("lecture-a", 1)]
    assert store.list_calls == [(COURSE_ID, ["lecture-a"])]


def test_empty_selected_material_scope_never_falls_back_to_the_whole_course(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = fragment("available-but-unselected")
    store = FakeStore([source])
    set_status(monkeypatch, status())
    vector = FakeVectorStore([payload(source, 0.99)])

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "语义化问题",
        selected_material_ids=[],
        qdrant_store=vector,
        embed_query=lambda _: pytest.fail("empty selected scope must not embed"),
    )

    assert result.retrieval_availability == "unavailable"
    assert result.confidence is None
    assert result.error is not None
    assert result.error.error_code == "selected_scope_has_no_ready_evidence"
    assert vector.calls == []
    assert store.list_calls == [(COURSE_ID, [])]


def test_partial_source_coverage_remains_visible_in_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = fragment("partial")
    store = FakeStore([source])
    set_status(
        monkeypatch,
        status(
            source_status="partial",
            total_materials=2,
            ready_materials=1,
            materials=[
                SimpleNamespace(material_id="lecture-a", status="ready"),
                SimpleNamespace(material_id="lecture-b", status="processing"),
            ],
        ),
    )

    result = retrieval.retrieve_current_fragments(
        store,
        COURSE_ID,
        "特征值",
        limit=1,
        embed_query=lambda _: pytest.fail("complete exact hit must skip embedding"),
    )

    assert result.confidence == "grounded"
    assert result.coverage == 0.5
    assert [warning.warning_code for warning in result.warnings] == [
        "partial_source_coverage"
    ]


@pytest.mark.parametrize(
    ("course_exists", "source_status", "materials", "expected_error", "retriable"),
    [
        (False, "empty", [], "course_not_found", False),
        (
            True,
            "processing",
            [SimpleNamespace(material_id="lecture-a", status="processing")],
            "source_evidence_unavailable",
            True,
        ),
        (
            True,
            "failed",
            [SimpleNamespace(material_id="lecture-a", status="failed")],
            "source_evidence_unavailable",
            False,
        ),
    ],
)
def test_unknown_or_unready_course_is_not_silently_treated_as_empty(
    monkeypatch: pytest.MonkeyPatch,
    course_exists: bool,
    source_status: str,
    materials: list[object],
    expected_error: str,
    retriable: bool,
) -> None:
    store = FakeStore([], course_exists=course_exists)
    set_status(monkeypatch, status(source_status=source_status, total_materials=1, ready_materials=0, materials=materials))

    result = retrieval.retrieve_current_fragments(store, COURSE_ID, "特征值")

    assert result.confidence is None
    assert result.retrieval_availability == "unavailable"
    assert result.error is not None
    assert result.error.error_code == expected_error
    assert result.error.retriable is retriable


def test_truly_empty_course_is_a_clean_out_of_scope_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeStore([])
    set_status(monkeypatch, status(source_status="empty", total_materials=0, ready_materials=0))

    result = retrieval.retrieve_current_fragments(store, COURSE_ID, "特征值")

    assert result.confidence == "out_of_scope"
    assert result.retrieval_availability == "available"
    assert result.error is None
    assert result.hits == []


async def test_retrieved_evidence_opens_through_the_current_fragment_endpoint(
    client: AsyncClient,
) -> None:
    """The ID emitted by retrieval remains usable by C1's citation endpoint."""
    from app.main import app

    course_id = "retrieval-preview-course"
    material_id = "retrieval-preview-material"
    store = app.state.store
    store.create_course(Course(id=course_id, title="检索预览", status="empty"))
    material = store.create_material(
        Material(
            id=material_id,
            course_id=course_id,
            filename="eigenvalue.md",
            kind="text_note",
            status="processing",
            content_hash="retrieval-preview-hash",
        )
    )
    job = enqueue_material_index_job(
        store,
        course_id=course_id,
        material_id=material_id,
        revision=material.revision,
    )
    claimed = store.claim_next_knowledge_job("retrieval-preview-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == job.job_id
    fragments = build_source_fragments(
        "# 特征值\n\n若 Av = λv，则 λ 是特征值。",
        course_id=course_id,
        material_id=material_id,
        material_revision=material.revision,
        parser_name="fragment-retrieval-preview-test",
    )
    store.replace_source_fragments(course_id, material_id, material.revision, fragments)
    assert store.update_material_status_if_revision(
        course_id,
        material_id,
        material.revision,
        "ready",
    )
    store.complete_knowledge_job(course_id, job.job_id, "retrieval-preview-worker")

    outcome = retrieval.retrieve_current_fragments(
        store,
        course_id,
        "特征值",
        limit=1,
        embed_query=lambda _: pytest.fail("complete exact hit must skip embedding"),
    )

    assert outcome.confidence == "grounded"
    hit = outcome.hits[0]
    preview = await client.get(
        f"/courses/{course_id}/source-fragments/{hit.evidence.fragment_id}"
    )
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["text"] == hit.canonical_text
    assert payload["locator"] == hit.evidence.locator
    assert payload["material_id"] == hit.evidence.material_id
    assert payload["material_revision"] == hit.evidence.material_revision
