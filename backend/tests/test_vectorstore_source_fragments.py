"""Qdrant contract tests for V2 source-fragment evidence vectors.

The client is deliberately mocked: these tests verify the point and filter
contracts without creating a local collection or making a network connection.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qdrant_client.models import Filter, MatchAny

from app.schemas.evidence import SourceFragment
from app.services import vectorstore
from app.services.vectorstore import QdrantStore


class MockQdrantClient:
    def __init__(self) -> None:
        self.collections: set[str] = set()
        self.create_calls: list[dict] = []
        self.upsert_calls: list[dict] = []
        self.delete_calls: list[dict] = []
        self.query_calls: list[dict] = []
        self.query_response_points: list[SimpleNamespace] = []

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def create_collection(self, **kwargs) -> None:
        self.create_calls.append(kwargs)
        self.collections.add(kwargs["collection_name"])

    def upsert(self, **kwargs) -> None:
        self.upsert_calls.append(kwargs)

    def delete(self, **kwargs) -> None:
        self.delete_calls.append(kwargs)

    def query_points(self, **kwargs) -> SimpleNamespace:
        self.query_calls.append(kwargs)
        return SimpleNamespace(points=self.query_response_points)


@pytest.fixture
def qdrant_client(monkeypatch: pytest.MonkeyPatch) -> MockQdrantClient:
    client = MockQdrantClient()
    monkeypatch.setattr(vectorstore, "_get_client", lambda: client)
    return client


@pytest.fixture
def fragments() -> list[SourceFragment]:
    return [
        SourceFragment(
            fragment_id="sf-linear-algebra-1",
            course_id="linear-algebra",
            material_id="lecture-01",
            material_revision=3,
            ordinal=0,
            text="向量空间对加法和数乘封闭。",
            heading_path=["第一章 向量空间", "1.1 定义"],
            page_start=2,
            page_end=3,
            char_start=11,
            char_end=24,
            kind="paragraph",
            parser_name="test-parser",
            content_hash="hash-vector-space",
        ),
        SourceFragment(
            fragment_id="sf-linear-algebra-2",
            course_id="linear-algebra",
            material_id="lecture-01",
            material_revision=3,
            ordinal=1,
            text="A v = λ v",
            slide_start=4,
            slide_end=4,
            char_start=30,
            char_end=39,
            kind="formula",
            parser_name="test-parser",
            content_hash="hash-eigenvalue",
        ),
    ]


def test_upsert_source_fragments_has_stable_ids_and_evidence_payload(
    qdrant_client: MockQdrantClient,
    fragments: list[SourceFragment],
):
    store = QdrantStore()
    embeddings = [[0.1, 0.2], [0.3, 0.4]]

    store.upsert_source_fragments(
        "linear-algebra",
        fragments,
        embeddings,
        file_name="lecture-01.pdf",
    )
    store.upsert_source_fragments(
        "linear-algebra",
        fragments,
        embeddings,
        file_name="lecture-01.pdf",
    )

    assert len(qdrant_client.create_calls) == 1
    assert len(qdrant_client.upsert_calls) == 2
    first_points = qdrant_client.upsert_calls[0]["points"]
    second_points = qdrant_client.upsert_calls[1]["points"]
    assert [point.id for point in first_points] == [point.id for point in second_points]

    first_payload = first_points[0].payload
    assert first_payload == {
        "type": "source_fragment",
        "course_id": "linear-algebra",
        "fragment_id": "sf-linear-algebra-1",
        "material_id": "lecture-01",
        "material_revision": 3,
        "ordinal": 0,
        "text": "向量空间对加法和数乘封闭。",
        "heading_path": ["第一章 向量空间", "1.1 定义"],
        "page_start": 2,
        "page_end": 3,
        "slide_start": None,
        "slide_end": None,
        "char_start": 11,
        "char_end": 24,
        "kind": "paragraph",
        "asset_id": None,
        "parser_name": "test-parser",
        "content_hash": "hash-vector-space",
        "file_name": "lecture-01.pdf",
        "locator": "第一章 向量空间 > 1.1 定义；pp.2-3",
    }

    second_payload = first_points[1].payload
    assert second_payload["slide_start"] == 4
    assert second_payload["slide_end"] == 4
    assert second_payload["page_start"] is None
    assert second_payload["file_name"] == "lecture-01.pdf"


def test_upsert_source_fragments_rejects_mismatched_scope_or_lengths(
    qdrant_client: MockQdrantClient,
    fragments: list[SourceFragment],
):
    store = QdrantStore()

    with pytest.raises(ValueError, match="same length"):
        store.upsert_source_fragments(
            "linear-algebra",
            fragments,
            [[0.1, 0.2]],
            file_name="lecture-01.pdf",
        )

    with pytest.raises(ValueError, match="must match the requested course_id"):
        store.upsert_source_fragments(
            "another-course",
            fragments,
            [[0.1, 0.2], [0.3, 0.4]],
            file_name="lecture-01.pdf",
        )

    with pytest.raises(ValueError, match="course_id is required"):
        store.upsert_source_fragments(
            " ",
            [],
            [],
            file_name="lecture-01.pdf",
        )

    assert not qdrant_client.create_calls
    assert not qdrant_client.upsert_calls


def test_delete_source_fragments_by_material_filters_to_source_evidence_only(
    qdrant_client: MockQdrantClient,
):
    qdrant_client.collections.add("course_linear-algebra")

    QdrantStore().delete_source_fragments_by_material("linear-algebra", "lecture-01")

    assert len(qdrant_client.delete_calls) == 1
    delete_call = qdrant_client.delete_calls[0]
    assert delete_call["collection_name"] == "course_linear-algebra"
    conditions = {
        condition.key: condition.match.value
        for condition in delete_call["points_selector"].must
    }
    assert conditions == {
        "type": "source_fragment",
        "course_id": "linear-algebra",
        "material_id": "lecture-01",
    }


def test_delete_source_fragments_by_material_skips_missing_collection(
    qdrant_client: MockQdrantClient,
):
    QdrantStore().delete_source_fragments_by_material("linear-algebra", "lecture-01")

    assert not qdrant_client.delete_calls


def test_source_fragment_search_keeps_material_revision_scope_pairs(
    qdrant_client: MockQdrantClient,
):
    qdrant_client.collections.add("course_linear-algebra")
    payload = {
        "type": "source_fragment",
        "course_id": "linear-algebra",
        "fragment_id": "sf-linear-algebra-1",
        "material_id": "lecture-01",
        "material_revision": 3,
        "text": "向量空间对加法和数乘封闭。",
    }
    qdrant_client.query_response_points = [SimpleNamespace(score=0.91, payload=payload)]

    results = QdrantStore().search_source_fragments(
        "linear-algebra",
        [0.1, 0.2],
        [("lecture-01", 3), ("lecture-02", 5)],
        limit=7,
    )

    assert results == [{"score": 0.91, "payload": payload}]
    assert len(qdrant_client.query_calls) == 1
    query_call = qdrant_client.query_calls[0]
    assert query_call["collection_name"] == "course_linear-algebra"
    assert query_call["query"] == [0.1, 0.2]
    assert query_call["limit"] == 7

    source_filter = query_call["query_filter"]
    assert isinstance(source_filter, Filter)
    assert {
        condition.key: condition.match.value
        for condition in source_filter.must
    } == {
        "type": "source_fragment",
        "course_id": "linear-algebra",
    }
    assert source_filter.should is not None
    assert all(isinstance(scope_filter, Filter) for scope_filter in source_filter.should)
    assert [
        {
            condition.key: condition.match.value
            for condition in scope_filter.must
        }
        for scope_filter in source_filter.should
    ] == [
        {"material_id": "lecture-01", "material_revision": 3},
        {"material_id": "lecture-02", "material_revision": 5},
    ]
    assert all(
        not isinstance(condition.match, MatchAny)
        for scope_filter in source_filter.should
        for condition in scope_filter.must
    )


def test_source_fragment_search_skips_qdrant_for_empty_scope(
    monkeypatch: pytest.MonkeyPatch,
):
    def fail_if_called():
        pytest.fail("empty source-fragment scope must not initialize or query Qdrant")

    monkeypatch.setattr(vectorstore, "_get_client", fail_if_called)

    assert QdrantStore().search_source_fragments(
        "linear-algebra",
        [0.1, 0.2],
        [],
    ) == []
