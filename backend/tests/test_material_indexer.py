"""Material-index job integration tests using synthetic linear-algebra Markdown."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import Course, Material
from app.services.knowledge_jobs import enqueue_material_index_job
from app.services.knowledge_worker import KnowledgeJobWorker
from app.services.material_indexer import MaterialIndexer
from app.services.parser_interface import (
    BoundingBox,
    DocumentParsingException,
    ExtractedAssetMeta,
    UnifiedParserOutput,
)


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []
        self.upserts: list[tuple[str, list, list, str]] = []

    def delete_source_fragments_by_material(self, course_id: str, material_id: str) -> None:
        self.deleted.append((course_id, material_id))

    def upsert_source_fragments(
        self, course_id: str, fragments: list, embeddings: list, *, file_name: str
    ) -> None:
        self.upserts.append((course_id, fragments, embeddings, file_name))


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    database = SqliteStore(tmp_path / "material-indexer.db")
    database.create_course(Course(id="linear-algebra", title="线性代数", status="empty"))
    yield database
    database.close()


def _create_material(store: SqliteStore, tmp_path: Path, *, revision: int = 1) -> Material:
    file_path = tmp_path / "linear-algebra.md"
    file_path.write_text("# 线性代数\n\n向量空间是封闭的集合。", encoding="utf-8")
    material = Material(
        id="la-notes",
        course_id="linear-algebra",
        filename="linear-algebra.md",
        kind="text_note",
        status="processing",
        revision=revision,
        content_hash=f"source-v{revision}",
    )
    store.create_material(material, file_path=str(file_path))
    return material


def _parse_success(_file_path: str, _kind: str) -> UnifiedParserOutput:
    return UnifiedParserOutput(
        document_id="linear-algebra-doc",
        raw_input_type="TEXT",
        markdown_content="# 第一章 向量空间\n\n向量空间对加法和数乘封闭。",
        parser_name="synthetic-parser",
    )


def _parse_success_with_asset(_file_path: str, _kind: str) -> UnifiedParserOutput:
    return UnifiedParserOutput(
        document_id="linear-algebra-doc",
        raw_input_type="TEXT",
        markdown_content="# 第一章 向量空间\n\n向量空间对加法和数乘封闭。",
        extracted_assets=[
            ExtractedAssetMeta(
                element_id="asset-vector-space",
                element_type="Image",
                sequential_label="[Image_1]",
                page_number=1,
                source_chapter="第一章 向量空间",
                storage_path="images/linear-algebra/vector-space.png",
                alt_text="向量空间示意图",
                bounding_box=BoundingBox(x0=1, y0=2, x1=3, y1=4),
            )
        ],
        parser_name="synthetic-parser",
    )


async def test_index_job_persists_markdown_fragments_and_stable_vector_payload(
    store: SqliteStore, tmp_path: Path
) -> None:
    material = _create_material(store, tmp_path)
    vector_store = FakeVectorStore()
    indexer = MaterialIndexer(
        store,
        vector_store=vector_store,  # type: ignore[arg-type]
        parse_document=_parse_success,
        embed=lambda texts: [[0.1, 0.2] for _ in texts],
    )
    job = enqueue_material_index_job(
        store,
        course_id=material.course_id,
        material_id=material.id,
        revision=material.revision,
    )
    worker = KnowledgeJobWorker(
        store,
        worker_id="indexer-worker",
        handlers={"index_material": indexer},
    )

    await worker.run_once()

    persisted_material = store.get_material(material.course_id, material.id)
    fragments = store.list_source_fragments(
        material.course_id, material_id=material.id, material_revision=material.revision
    )
    persisted_job = store.get_knowledge_job(material.course_id, job.job_id)
    compile_jobs = [
        queued
        for queued in store.list_knowledge_jobs(material.course_id)
        if queued.job_type == "compile_course"
    ]

    assert persisted_material is not None and persisted_material.status == "ready"
    assert store.get_parsed_text(material.course_id, material.id) is not None
    assert len(fragments) == 1
    assert fragments[0].heading_path == ["第一章 向量空间"]
    assert vector_store.deleted == [(material.course_id, material.id)]
    assert len(vector_store.upserts) == 1
    assert vector_store.upserts[0][1][0].fragment_id == fragments[0].fragment_id
    assert persisted_job is not None and persisted_job.status == "succeeded"
    assert len(compile_jobs) == 1
    assert compile_jobs[0].status == "queued"
    assert compile_jobs[0].target_source_revision is not None
    assert compile_jobs[0].target_knowledge_revision is not None


async def test_indexed_assets_are_current_only_and_revision_advance_clears_them(
    store: SqliteStore, tmp_path: Path
) -> None:
    material = _create_material(store, tmp_path)
    indexer = MaterialIndexer(
        store,
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        parse_document=_parse_success_with_asset,
        embed=lambda texts: [[0.1, 0.2] for _ in texts],
    )
    job = enqueue_material_index_job(
        store,
        course_id=material.course_id,
        material_id=material.id,
        revision=material.revision,
    )
    worker = KnowledgeJobWorker(
        store,
        worker_id="indexer-worker",
        handlers={"index_material": indexer},
    )

    await worker.run_once()

    assets = store.get_extracted_assets(material.course_id, material.id)
    persisted_job = store.get_knowledge_job(material.course_id, job.job_id)
    assert persisted_job is not None and persisted_job.status == "succeeded"
    assert len(assets) == 1
    assert assets[0]["asset_id"] == "asset-vector-space"
    assert (assets[0]["x0"], assets[0]["y0"], assets[0]["x1"], assets[0]["y1"]) == (
        1.0,
        2.0,
        3.0,
        4.0,
    )

    advanced = store.advance_material_revision(
        material.course_id,
        material.id,
        "source-v2",
    )
    assert advanced is not None and advanced.revision == 2
    assert store.get_extracted_assets(material.course_id, material.id) == []


async def test_stale_material_job_cannot_write_newer_revision(
    store: SqliteStore, tmp_path: Path
) -> None:
    material = _create_material(store, tmp_path)
    vector_store = FakeVectorStore()
    indexer = MaterialIndexer(
        store,
        vector_store=vector_store,  # type: ignore[arg-type]
        parse_document=_parse_success_with_asset,
        embed=lambda texts: [[0.1, 0.2] for _ in texts],
    )
    old_job = enqueue_material_index_job(
        store, course_id=material.course_id, material_id=material.id, revision=1
    )
    advanced = store.advance_material_revision(
        material.course_id, material.id, "source-v2"
    )
    assert advanced is not None and advanced.revision == 2
    worker = KnowledgeJobWorker(
        store,
        worker_id="indexer-worker",
        handlers={"index_material": indexer},
    )

    await worker.run_once()

    persisted_material = store.get_material(material.course_id, material.id)
    persisted_job = store.get_knowledge_job(material.course_id, old_job.job_id)
    assert persisted_material is not None and persisted_material.status == "processing"
    assert store.list_source_fragments(material.course_id, material_id=material.id) == []
    assert vector_store.deleted == []
    assert persisted_job is not None
    assert persisted_job.status == "failed"
    assert persisted_job.error_code == "stale_material_revision"


async def test_replacement_between_initial_check_and_publish_cannot_touch_vector_index(
    store: SqliteStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replacement can win after parse, but before the fenced publication.

    This reproduces the former race window: the job has already passed its
    first revision check and parsed/embedded the old file when a replacement
    advances the material revision.  The publish fence must reject that stale
    job before its delete/upsert callbacks run.
    """
    material = _create_material(store, tmp_path)
    vector_store = FakeVectorStore()
    indexer = MaterialIndexer(
        store,
        vector_store=vector_store,  # type: ignore[arg-type]
        parse_document=_parse_success_with_asset,
        embed=lambda texts: [[0.1, 0.2] for _ in texts],
    )
    original_save = store.save_parsed_text_if_revision

    def save_then_replace(
        course_id: str, material_id: str, revision: int, text: str
    ) -> bool:
        saved = original_save(course_id, material_id, revision, text)
        if saved:
            advanced = store.advance_material_revision(
                course_id,
                material_id,
                "source-v2",
            )
            assert advanced is not None and advanced.revision == revision + 1
        return saved

    monkeypatch.setattr(store, "save_parsed_text_if_revision", save_then_replace)
    job = enqueue_material_index_job(
        store,
        course_id=material.course_id,
        material_id=material.id,
        revision=material.revision,
    )
    worker = KnowledgeJobWorker(
        store,
        worker_id="indexer-worker",
        handlers={"index_material": indexer},
    )

    await worker.run_once()

    persisted_material = store.get_material(material.course_id, material.id)
    persisted_job = store.get_knowledge_job(material.course_id, job.job_id)
    assert persisted_material is not None
    assert persisted_material.revision == 2
    assert persisted_material.status == "processing"
    assert vector_store.deleted == []
    assert vector_store.upserts == []
    assert store.list_source_fragments(material.course_id, material_id=material.id) == []
    assert store.get_extracted_assets(material.course_id, material.id) == []
    assert persisted_job is not None
    assert persisted_job.status == "failed"
    assert persisted_job.error_code == "stale_material_revision"


async def test_parse_failure_is_visible_on_material_and_job(
    store: SqliteStore, tmp_path: Path
) -> None:
    material = _create_material(store, tmp_path)

    def parse_failure(file_path: str, _kind: str) -> UnifiedParserOutput:
        raise DocumentParsingException(Path(file_path), "synthetic parse failure")

    indexer = MaterialIndexer(
        store,
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        parse_document=parse_failure,
        embed=lambda texts: [[0.1, 0.2] for _ in texts],
    )
    job = enqueue_material_index_job(
        store,
        course_id=material.course_id,
        material_id=material.id,
        revision=material.revision,
    )
    worker = KnowledgeJobWorker(
        store,
        worker_id="indexer-worker",
        handlers={"index_material": indexer},
    )

    await worker.run_once()

    persisted_material = store.get_material(material.course_id, material.id)
    persisted_job = store.get_knowledge_job(material.course_id, job.job_id)
    assert persisted_material is not None and persisted_material.status == "failed"
    assert persisted_job is not None
    assert persisted_job.status == "failed"
    assert persisted_job.error_code == "material_parse_failed"
