"""Tests for the controlled V2 worker; no HTTP background task is involved."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import Course, Material
from app.services.knowledge_jobs import (
    enqueue_course_compile_job,
    enqueue_material_index_job,
)
from app.services.knowledge_worker import (
    KnowledgeJobExecutionError,
    KnowledgeJobWorker,
)


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    result = SqliteStore(tmp_path / "knowledge-worker.db")
    result.create_course(Course(id="course-a", title="线性代数", status="empty"))
    result.create_material(
        Material(
            id="material-a",
            course_id="course-a",
            filename="chapter-1.md",
            kind="text_note",
            status="processing",
        ),
        file_path="chapter-1.md",
    )
    yield result
    result.close()


async def test_worker_completes_registered_job(store: SqliteStore) -> None:
    enqueued = enqueue_material_index_job(
        store, course_id="course-a", material_id="material-a", revision=1
    )
    handled: list[str] = []

    async def handle(job):
        handled.append(job.job_id)

    worker = KnowledgeJobWorker(
        store,
        worker_id="worker-a",
        handlers={"index_material": handle},
    )

    claimed = await worker.run_once()
    persisted = store.get_knowledge_job("course-a", enqueued.job_id)

    assert claimed is not None and claimed.job_id == enqueued.job_id
    assert handled == [enqueued.job_id]
    assert persisted is not None and persisted.status == "succeeded"


async def test_worker_persists_declared_failure(store: SqliteStore) -> None:
    enqueued = enqueue_course_compile_job(store, course_id="course-a", revision=1)

    async def fail(_job):
        raise KnowledgeJobExecutionError(
            "model budget exhausted", code="token_budget_exhausted", retryable=False
        )

    worker = KnowledgeJobWorker(
        store,
        worker_id="worker-a",
        handlers={"compile_course": fail},
    )

    await worker.run_once()
    persisted = store.get_knowledge_job("course-a", enqueued.job_id)

    assert persisted is not None
    assert persisted.status == "failed"
    assert persisted.error_code == "token_budget_exhausted"
    assert persisted.error_detail == "model budget exhausted"


async def test_worker_retries_unexpected_failure(store: SqliteStore) -> None:
    enqueued = enqueue_course_compile_job(store, course_id="course-a", revision=2)

    async def explode(_job):
        raise RuntimeError("temporary provider outage")

    worker = KnowledgeJobWorker(
        store,
        worker_id="worker-a",
        handlers={"compile_course": explode},
    )

    await worker.run_once()
    persisted = store.get_knowledge_job("course-a", enqueued.job_id)

    assert persisted is not None
    assert persisted.status == "retryable"
    assert persisted.error_code == "unexpected_knowledge_job_failure"
    assert "temporary provider outage" in (persisted.error_detail or "")


async def test_worker_marks_unknown_job_type_failed(store: SqliteStore) -> None:
    enqueued = enqueue_course_compile_job(store, course_id="course-a", revision=3)
    worker = KnowledgeJobWorker(store, worker_id="worker-a", handlers={})

    await worker.run_once()
    persisted = store.get_knowledge_job("course-a", enqueued.job_id)

    assert persisted is not None
    assert persisted.status == "failed"
    assert persisted.error_code == "unsupported_knowledge_job_type"


async def test_worker_renews_lease_while_handler_is_running(
    store: SqliteStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueued = enqueue_course_compile_job(store, course_id="course-a", revision=4)
    original_renew = store.renew_knowledge_job_lease
    renew_calls = 0

    def record_renew(*args, **kwargs):
        nonlocal renew_calls
        renew_calls += 1
        return original_renew(*args, **kwargs)

    monkeypatch.setattr(store, "renew_knowledge_job_lease", record_renew)

    async def handle(_job):
        await asyncio.sleep(0.04)

    worker = KnowledgeJobWorker(
        store,
        worker_id="worker-a",
        handlers={"compile_course": handle},
        lease_seconds=5,
        heartbeat_interval_seconds=0.01,
    )

    await worker.run_once()
    persisted = store.get_knowledge_job("course-a", enqueued.job_id)

    assert renew_calls >= 1
    assert persisted is not None and persisted.status == "succeeded"
