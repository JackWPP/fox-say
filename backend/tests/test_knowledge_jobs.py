"""Persistent V2 knowledge-job queue tests (no worker execution loop)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import Course, Material
from app.services.knowledge_jobs import (
    enqueue_course_compile_job,
    enqueue_material_index_job,
)


@pytest.fixture
def store(tmp_path: Path):
    db = SqliteStore(tmp_path / "knowledge-jobs.db")
    db.create_course(Course(id="course-a", title="课程 A", status="empty"))
    db.create_course(Course(id="course-b", title="课程 B", status="empty"))
    db.create_material(
        Material(
            id="material-a",
            course_id="course-a",
            filename="notes.txt",
            kind="text_note",
            status="processing",
        )
    )
    yield db
    db.close()


def test_enqueue_material_job_is_idempotent_and_revision_scoped(store: SqliteStore):
    first = enqueue_material_index_job(
        store, course_id="course-a", material_id="material-a", revision=3
    )
    second = enqueue_material_index_job(
        store, course_id="course-a", material_id="material-a", revision=3
    )
    next_revision = enqueue_material_index_job(
        store, course_id="course-a", material_id="material-a", revision=4
    )

    assert first.job_id == second.job_id
    assert first.status == "queued"
    assert first.scope == "material"
    assert first.material_id == "material-a"
    assert first.token_budget is None
    assert next_revision.job_id != first.job_id
    assert len(store.list_knowledge_jobs("course-a")) == 2


def test_enqueue_rejects_material_from_another_course(store: SqliteStore):
    with pytest.raises(ValueError, match="does not belong to course"):
        enqueue_material_index_job(
            store, course_id="course-b", material_id="material-a", revision=1
        )


def test_claim_honors_lease_and_reclaims_expired_job(store: SqliteStore):
    queued = enqueue_course_compile_job(store, course_id="course-a", revision=7)

    first_claim = store.claim_next_knowledge_job("worker-a", lease_seconds=60)
    assert first_claim is not None
    assert first_claim.job_id == queued.job_id
    assert first_claim.status == "running"
    assert first_claim.lease_owner == "worker-a"
    assert first_claim.lease_expires_at is not None
    assert first_claim.attempt == 1
    assert store.claim_next_knowledge_job("worker-b", lease_seconds=60) is None

    store._conn.execute(
        "UPDATE knowledge_jobs SET lease_expires_at = datetime('now', '-1 second') WHERE job_id = ?",
        (queued.job_id,),
    )
    store._conn.commit()

    reclaimed = store.claim_next_knowledge_job("worker-b", lease_seconds=60)
    assert reclaimed is not None
    assert reclaimed.job_id == queued.job_id
    assert reclaimed.lease_owner == "worker-b"
    assert reclaimed.attempt == 2
    with pytest.raises(ValueError, match="lease owner"):
        store.complete_knowledge_job("course-a", queued.job_id, "worker-a")


def test_complete_fail_and_retry_preserve_explicit_state(store: SqliteStore):
    completed_job = enqueue_course_compile_job(store, course_id="course-a", revision=1)
    claimed = store.claim_next_knowledge_job("worker-a", lease_seconds=60)
    assert claimed is not None and claimed.job_id == completed_job.job_id

    completed = store.complete_knowledge_job("course-a", completed_job.job_id, "worker-a")
    assert completed.status == "succeeded"
    assert completed.finished_at is not None
    assert completed.lease_owner is None

    retry_job = enqueue_course_compile_job(store, course_id="course-a", revision=2)
    claimed_retry_job = store.claim_next_knowledge_job("worker-b", lease_seconds=60)
    assert claimed_retry_job is not None and claimed_retry_job.job_id == retry_job.job_id

    retryable = store.fail_knowledge_job(
        "course-a",
        retry_job.job_id,
        "worker-b",
        "embedding provider timed out",
        retryable=True,
        error_code="embedding_timeout",
    )
    assert retryable.status == "retryable"
    assert retryable.error_code == "embedding_timeout"
    assert retryable.error_detail == "embedding provider timed out"
    assert retryable.lease_owner is None

    requeued = store.retry_knowledge_job("course-a", retry_job.job_id)
    assert requeued.status == "queued"
    assert requeued.error_detail == "embedding provider timed out"
    assert requeued.finished_at is None

    second_attempt = store.claim_next_knowledge_job("worker-c", lease_seconds=60)
    assert second_attempt is not None and second_attempt.job_id == retry_job.job_id
    assert second_attempt.attempt == 2

    terminal = store.fail_knowledge_job(
        "course-a",
        retry_job.job_id,
        "worker-c",
        "unsupported source format",
        retryable=False,
        error_code="unsupported_source",
    )
    assert terminal.status == "failed"
    assert terminal.error_code == "unsupported_source"
    assert terminal.finished_at is not None
