"""D0 deterministic course-compilation regression tests (zero model calls)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import Course, Material
from app.schemas.evidence import SourceFragment
from app.schemas.knowledge_jobs import KnowledgeJob
from app.services.course_compiler import CourseCompiler
from app.services.knowledge_jobs import enqueue_course_compile_job, enqueue_material_index_job
from app.services.knowledge_status import build_knowledge_status
from app.services.knowledge_worker import KnowledgeJobWorker


def _fragment(
    *,
    course_id: str,
    material_id: str,
    ordinal: int,
    heading_path: list[str],
    text: str,
) -> SourceFragment:
    return SourceFragment(
        fragment_id=f"fragment-{course_id}-{material_id}-{ordinal}",
        course_id=course_id,
        material_id=material_id,
        material_revision=1,
        ordinal=ordinal,
        text=text,
        heading_path=heading_path,
        char_start=ordinal * 100,
        char_end=ordinal * 100 + len(text),
        kind="paragraph",
        parser_name="synthetic-d0",
        content_hash=f"hash-{material_id}",
    )


def _seed_ready_material(
    store: SqliteStore,
    *,
    course_id: str,
    material_id: str,
    fragments: list[SourceFragment],
) -> None:
    store.create_material(
        Material(
            id=material_id,
            course_id=course_id,
            filename=f"{material_id}.md",
            kind="text_note",
            status="ready",
            revision=1,
            content_hash=f"hash-{material_id}",
        )
    )
    store.replace_source_fragments(course_id, material_id, 1, fragments)
    job = enqueue_material_index_job(
        store, course_id=course_id, material_id=material_id, revision=1
    )
    claimed = store.claim_next_knowledge_job("seed-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == job.job_id
    store.complete_knowledge_job(course_id, job.job_id, "seed-worker")


@pytest.fixture
def store(tmp_path: Path) -> Generator[SqliteStore, None, None]:
    database = SqliteStore(tmp_path / "course-compiler.db")
    database.create_course(Course(id="linear", title="线性代数", status="empty"))
    yield database
    database.close()


async def _compile_current_course(
    store: SqliteStore, course_id: str
) -> tuple[KnowledgeJob, tuple[str, str]]:
    manifest = store.get_compilable_source_manifest(course_id)
    assert manifest is not None
    job = enqueue_course_compile_job(
        store,
        course_id=course_id,
        source_revision=manifest[0],
    )
    worker = KnowledgeJobWorker(
        store,
        worker_id="compiler-worker",
        handlers={"compile_course": CourseCompiler(store)},
    )
    completed = await worker.run_once()
    assert completed is not None and completed.job_id == job.job_id
    return job, manifest


@pytest.mark.asyncio
async def test_compiler_publishes_source_pinned_outline_and_ready_status(store: SqliteStore) -> None:
    _seed_ready_material(
        store,
        course_id="linear",
        material_id="vectors",
        fragments=[
            _fragment(
                course_id="linear",
                material_id="vectors",
                ordinal=0,
                heading_path=["第一章 向量空间"],
                text="向量空间对加法封闭。",
            ),
            _fragment(
                course_id="linear",
                material_id="vectors",
                ordinal=1,
                heading_path=["第一章 向量空间", "1.1 子空间"],
                text="子空间必须包含零向量。",
            ),
        ],
    )
    _seed_ready_material(
        store,
        course_id="linear",
        material_id="matrix",
        fragments=[
            _fragment(
                course_id="linear",
                material_id="matrix",
                ordinal=0,
                heading_path=["第二章 矩阵"],
                text="矩阵乘法通常不可交换。",
            )
        ],
    )

    job, manifest = await _compile_current_course(store, "linear")

    persisted = store.get_knowledge_job("linear", job.job_id)
    assert persisted is not None and persisted.status == "succeeded"
    assert persisted.target_source_revision == manifest[0]
    outline = store.get_current_course_outline("linear", manifest[0])
    assert outline is not None
    assert outline.fragment_count == 3
    assert [section.title for section in outline.sections] == [
        "第二章 矩阵",
        "第一章 向量空间",
        "1.1 子空间",
    ]
    assert all(ref.course_id == "linear" for section in outline.sections for ref in section.evidence)
    assert all(
        store.get_current_ready_source_fragment_preview("linear", ref.fragment_id) is not None
        for section in outline.sections
        for ref in section.evidence
    )

    status = build_knowledge_status(store, "linear")
    assert status.status == "ready"
    assert status.source_status == "ready"
    assert status.projection_status == "ready"
    assert status.source_revision == manifest[0]
    assert status.knowledge_revision == outline.knowledge_revision
    assert status.compiled_from_source_revision == manifest[0]


def test_ready_sources_show_processing_while_the_current_compile_job_is_queued(
    store: SqliteStore,
) -> None:
    _seed_ready_material(
        store,
        course_id="linear",
        material_id="vectors",
        fragments=[
            _fragment(
                course_id="linear",
                material_id="vectors",
                ordinal=0,
                heading_path=["向量空间"],
                text="向量空间。",
            )
        ],
    )
    manifest = store.get_compilable_source_manifest("linear")
    assert manifest is not None
    enqueue_course_compile_job(store, course_id="linear", source_revision=manifest[0])

    status = build_knowledge_status(store, "linear")
    assert status.status == "partial"
    assert status.source_status == "ready"
    assert status.projection_status == "processing"


@pytest.mark.asyncio
async def test_compiler_rejects_stale_source_without_publishing_snapshot(store: SqliteStore) -> None:
    _seed_ready_material(
        store,
        course_id="linear",
        material_id="vectors",
        fragments=[
            _fragment(
                course_id="linear",
                material_id="vectors",
                ordinal=0,
                heading_path=["向量空间"],
                text="向量空间。",
            )
        ],
    )
    manifest = store.get_compilable_source_manifest("linear")
    assert manifest is not None
    job = enqueue_course_compile_job(
        store,
        course_id="linear",
        source_revision=manifest[0],
    )
    advanced = store.advance_material_revision(
        "linear", "vectors", "hash-vectors-next", status="processing"
    )
    assert advanced is not None and advanced.revision == 2

    worker = KnowledgeJobWorker(
        store,
        worker_id="stale-compiler-worker",
        handlers={"compile_course": CourseCompiler(store)},
    )
    await worker.run_once()

    persisted = store.get_knowledge_job("linear", job.job_id)
    assert persisted is not None
    assert persisted.status == "failed"
    assert persisted.error_code == "stale_course_source_revision"
    assert store.get_current_course_outline("linear", manifest[0]) is None
    status = build_knowledge_status(store, "linear")
    assert status.projection_status == "not_started"


@pytest.mark.asyncio
async def test_completed_outline_becomes_stale_after_current_material_changes(
    store: SqliteStore,
) -> None:
    _seed_ready_material(
        store,
        course_id="linear",
        material_id="vectors",
        fragments=[
            _fragment(
                course_id="linear",
                material_id="vectors",
                ordinal=0,
                heading_path=["向量空间"],
                text="向量空间。",
            )
        ],
    )
    _, manifest = await _compile_current_course(store, "linear")
    advanced = store.advance_material_revision(
        "linear", "vectors", "hash-vectors-next", status="processing"
    )
    assert advanced is not None

    status = build_knowledge_status(store, "linear")
    assert status.status == "stale"
    assert status.projection_status == "stale"
    assert status.source_revision != manifest[0]
    assert status.knowledge_revision is not None
    assert status.compiled_from_source_revision == manifest[0]


@pytest.mark.asyncio
async def test_same_source_compile_job_is_idempotent_and_course_scoped(store: SqliteStore) -> None:
    _seed_ready_material(
        store,
        course_id="linear",
        material_id="vectors",
        fragments=[
            _fragment(
                course_id="linear",
                material_id="vectors",
                ordinal=0,
                heading_path=[],
                text="无标题材料也必须可定位。",
            )
        ],
    )
    manifest = store.get_compilable_source_manifest("linear")
    assert manifest is not None
    store.create_course(Course(id="linear-b", title="线性代数 B", status="empty"))
    _seed_ready_material(
        store,
        course_id="linear-b",
        material_id="vectors-b",
        fragments=[
            _fragment(
                course_id="linear-b",
                material_id="vectors-b",
                ordinal=0,
                heading_path=["向量空间"],
                text="另一门课的向量空间。",
            )
        ],
    )
    other_manifest = store.get_compilable_source_manifest("linear-b")
    assert other_manifest is not None
    first = enqueue_course_compile_job(
        store, course_id="linear", source_revision=manifest[0]
    )
    second = enqueue_course_compile_job(
        store, course_id="linear", source_revision=manifest[0]
    )
    assert first.job_id == second.job_id
    other = enqueue_course_compile_job(
        store, course_id="linear-b", source_revision=other_manifest[0]
    )
    assert other.job_id != first.job_id

    worker = KnowledgeJobWorker(
        store,
        worker_id="isolation-compiler-worker",
        handlers={"compile_course": CourseCompiler(store)},
    )
    await worker.run_once()
    await worker.run_once()
    assert store.get_current_course_outline("linear", manifest[0]) is not None
    assert store.get_current_course_outline("linear-b", other_manifest[0]) is not None
    assert store.get_current_course_outline("linear-b", manifest[0]) is None
