"""Persistent V2 knowledge-job queue tests (no worker execution loop)."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import Course, Material
from app.schemas.knowledge_jobs import KnowledgeJobCreate
from app.services.knowledge_jobs import (
    enqueue_course_compile_job,
    enqueue_material_index_job,
    enqueue_semantic_atom_extraction_job,
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


def test_enqueue_rejects_different_idempotency_key_for_same_logical_job(
    store: SqliteStore,
):
    material_job = enqueue_material_index_job(
        store, course_id="course-a", material_id="material-a", revision=1
    )
    duplicate_material = KnowledgeJobCreate(
        job_id=str(uuid.uuid4()),
        course_id="course-a",
        material_id="material-a",
        job_type="index_material",
        revision=1,
        scope="material",
        idempotency_key="different-material-key",
    )
    with pytest.raises(ValueError, match="logical identity"):
        store.enqueue_knowledge_job(duplicate_material)
    assert store.get_knowledge_job("course-a", material_job.job_id) is not None
    assert len(store.list_knowledge_jobs("course-a")) == 1

    course_job = enqueue_course_compile_job(
        store, course_id="course-a", source_revision="src_duplicate_course"
    )
    duplicate_course = KnowledgeJobCreate(
        job_id=str(uuid.uuid4()),
        course_id="course-a",
        material_id=None,
        job_type="compile_course",
        revision=None,
        scope="course",
        idempotency_key="different-course-key",
        target_source_revision="src_duplicate_course",
        target_knowledge_revision="kn_duplicate_course",
    )
    with pytest.raises(ValueError, match="logical identity"):
        store.enqueue_knowledge_job(duplicate_course)
    assert store.get_knowledge_job("course-a", course_job.job_id) is not None
    assert len(store.list_knowledge_jobs("course-a")) == 2


def test_semantic_atom_job_has_its_own_course_source_identity(store: SqliteStore) -> None:
    outline = enqueue_course_compile_job(
        store, course_id="course-a", source_revision="src_semantic_identity"
    )
    semantic = enqueue_semantic_atom_extraction_job(
        store,
        course_id="course-a",
        source_revision="src_semantic_identity",
        knowledge_revision=outline.target_knowledge_revision or "kn_missing",
    )
    duplicate = enqueue_semantic_atom_extraction_job(
        store,
        course_id="course-a",
        source_revision="src_semantic_identity",
        knowledge_revision=outline.target_knowledge_revision or "kn_missing",
    )
    other_course = enqueue_semantic_atom_extraction_job(
        store,
        course_id="course-b",
        source_revision="src_semantic_identity",
        knowledge_revision=outline.target_knowledge_revision or "kn_missing",
    )

    assert semantic.job_id != outline.job_id
    assert semantic.job_type == "extract_semantic_atoms"
    assert semantic.scope == "course"
    assert semantic.target_source_revision == outline.target_source_revision
    assert duplicate.job_id == semantic.job_id
    assert other_course.job_id != semantic.job_id
    assert len(store.list_knowledge_jobs("course-a")) == 2
    assert [job.job_id for job in store.list_knowledge_jobs("course-b")] == [other_course.job_id]


def test_store_refuses_existing_duplicate_logical_identity_on_startup(tmp_path: Path):
    db_path = tmp_path / "duplicate-knowledge-jobs.db"
    store = SqliteStore(db_path)
    try:
        store.create_course(Course(id="course-a", title="课程 A", status="empty"))
        store.create_material(
            Material(
                id="material-a",
                course_id="course-a",
                filename="notes.txt",
                kind="text_note",
                status="processing",
            )
        )
        existing = enqueue_material_index_job(
            store, course_id="course-a", material_id="material-a", revision=1
        )
        store._conn.execute("DROP INDEX uq_knowledge_jobs_material_identity")
        store._conn.execute("DROP INDEX uq_knowledge_jobs_course_identity")
        store._conn.execute(
            """
            INSERT INTO knowledge_jobs
                (job_id, course_id, material_id, job_type, revision, scope,
                 status, attempt, idempotency_key)
            VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, ?)
            """,
            (
                "forced-duplicate-job",
                "course-a",
                "material-a",
                "index_material",
                1,
                "material",
                "forced-duplicate-key",
            ),
        )
        store._conn.commit()
        assert existing.job_id
    finally:
        store.close()

    with pytest.raises(RuntimeError, match="duplicate logical identities"):
        SqliteStore(db_path)

    # The persisted duplicate remains untouched for an explicit operator fix.
    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM knowledge_jobs").fetchone()[0]
        assert count == 2
    finally:
        connection.close()


def test_store_migrates_pre_d0_course_job_schema_and_uses_source_identity(tmp_path: Path):
    db_path = tmp_path / "pre-d0-knowledge-jobs.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE knowledge_jobs (
                job_id TEXT PRIMARY KEY,
                course_id TEXT NOT NULL,
                material_id TEXT,
                job_type TEXT NOT NULL,
                revision INTEGER NOT NULL,
                scope TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                attempt INTEGER NOT NULL DEFAULT 0,
                idempotency_key TEXT NOT NULL UNIQUE,
                token_budget INTEGER,
                lease_owner TEXT,
                lease_expires_at TEXT,
                error_code TEXT,
                error_detail TEXT,
                error_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                started_at TEXT,
                finished_at TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    store = SqliteStore(db_path)
    try:
        column_names = {
            row["name"]
            for row in store._conn.execute("PRAGMA table_info(knowledge_jobs)").fetchall()
        }
        assert {
            "target_source_revision",
            "target_knowledge_revision",
            "max_attempts",
        } <= column_names
        store.create_course(Course(id="course-a", title="课程 A", status="empty"))
        first = enqueue_course_compile_job(
            store, course_id="course-a", source_revision="src_pre_d0_a"
        )
        second = enqueue_course_compile_job(
            store, course_id="course-a", source_revision="src_pre_d0_b"
        )
        assert first.revision == 0
        assert second.revision == 1
        assert first.target_source_revision == "src_pre_d0_a"
        assert second.target_source_revision == "src_pre_d0_b"
    finally:
        store.close()


def test_job_type_migration_preserves_d0_and_d1a_facts(tmp_path: Path) -> None:
    db_path = tmp_path / "old-job-type-check.db"
    store = SqliteStore(db_path)
    try:
        store.create_course(Course(id="course-a", title="课程 A", status="empty"))
        outline = enqueue_course_compile_job(
            store, course_id="course-a", source_revision="src_migration"
        )
        claimed = store.claim_next_knowledge_job("worker-a", lease_seconds=60)
        assert claimed is not None and claimed.job_id == outline.job_id
        store.complete_knowledge_job("course-a", outline.job_id, "worker-a")
        assert outline.target_knowledge_revision is not None
        store._conn.execute(
            """
            INSERT INTO course_compilations (
                course_id, source_revision, knowledge_revision, compiler_version, job_id,
                source_manifest_json, source_fragment_count, outline_section_count, warning_count
            ) VALUES (?, ?, ?, 'course-outline-d0', ?, '{}', 0, 0, 0)
            """,
            (
                "course-a",
                "src_migration",
                outline.target_knowledge_revision,
                outline.job_id,
            ),
        )
        store._conn.execute(
            """
            INSERT INTO course_projection_snapshots (
                course_id, knowledge_revision, projection_kind, payload_json
            ) VALUES ('course-a', ?, 'course_outline', '{}')
            """,
            (outline.target_knowledge_revision,),
        )
        store._conn.execute(
            """
            INSERT INTO course_model_budgets (course_id, source_revision, token_budget)
            VALUES ('course-a', 'src_migration', 100)
            """
        )
        store._conn.execute(
            """
            INSERT INTO model_call_audits (
                call_id, course_id, job_id, job_attempt, source_revision, knowledge_revision,
                call_kind, purpose, provider, model, request_fingerprint, status,
                input_token_upper_bound, max_output_tokens, reserved_tokens, usage_source,
                accounted_tokens, course_budget_tokens, job_budget_tokens
            ) VALUES (
                'audit-migration', 'course-a', ?, 1, 'src_migration', ?, 'text',
                'synthetic', 'fake', 'fake-model', ?, 'succeeded', 1, 1, 2,
                'unavailable', 2, 100, 12000
            )
            """,
            (outline.job_id, outline.target_knowledge_revision, "a" * 64),
        )
        store._conn.commit()
    finally:
        store.close()

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            """
            CREATE TABLE knowledge_jobs_old_constraint (
                job_id TEXT PRIMARY KEY,
                course_id TEXT NOT NULL,
                material_id TEXT,
                job_type TEXT NOT NULL,
                revision INTEGER NOT NULL,
                scope TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                attempt INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                idempotency_key TEXT NOT NULL UNIQUE,
                token_budget INTEGER,
                target_source_revision TEXT,
                target_knowledge_revision TEXT,
                lease_owner TEXT,
                lease_expires_at TEXT,
                error_code TEXT,
                error_detail TEXT,
                error_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                started_at TEXT,
                finished_at TEXT,
                CHECK (job_type IN ('index_material', 'compile_course')),
                CHECK (scope IN ('material', 'course')),
                CHECK (status IN ('queued', 'running', 'succeeded', 'retryable', 'failed')),
                CHECK (revision >= 0),
                CHECK (attempt >= 0),
                CHECK (max_attempts > 0),
                CHECK (token_budget IS NULL OR token_budget > 0)
            )
            """
        )
        connection.execute(
            "INSERT INTO knowledge_jobs_old_constraint SELECT * FROM knowledge_jobs"
        )
        connection.execute("DROP TABLE knowledge_jobs")
        connection.execute("ALTER TABLE knowledge_jobs_old_constraint RENAME TO knowledge_jobs")
        connection.commit()
    finally:
        connection.close()

    migrated = SqliteStore(db_path)
    try:
        assert migrated._conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert migrated.get_knowledge_job("course-a", outline.job_id) is not None
        assert migrated._conn.execute("SELECT COUNT(*) FROM course_compilations").fetchone()[0] == 1
        assert migrated._conn.execute("SELECT COUNT(*) FROM model_call_audits").fetchone()[0] == 1
        semantic = enqueue_semantic_atom_extraction_job(
            migrated,
            course_id="course-a",
            source_revision="src_migration",
            knowledge_revision=outline.target_knowledge_revision or "kn_missing",
        )
        assert semantic.job_type == "extract_semantic_atoms"
        assert semantic.status == "queued"
    finally:
        migrated.close()


def test_enqueue_rejects_material_from_another_course(store: SqliteStore):
    with pytest.raises(ValueError, match="does not belong to course"):
        enqueue_material_index_job(
            store, course_id="course-b", material_id="material-a", revision=1
        )


def test_claim_honors_lease_and_reclaims_expired_job(store: SqliteStore):
    queued = enqueue_course_compile_job(
        store, course_id="course-a", source_revision="src_claim"
    )

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


def test_renew_lease_requires_current_owner(store: SqliteStore):
    queued = enqueue_course_compile_job(
        store, course_id="course-a", source_revision="src_renew"
    )
    claimed = store.claim_next_knowledge_job("worker-a", lease_seconds=60)
    assert claimed is not None and claimed.job_id == queued.job_id

    assert store.renew_knowledge_job_lease(
        "course-a", queued.job_id, "worker-a", lease_seconds=120
    )
    refreshed = store.get_knowledge_job("course-a", queued.job_id)
    assert refreshed is not None and refreshed.lease_expires_at is not None
    assert not store.renew_knowledge_job_lease(
        "course-a", queued.job_id, "worker-b", lease_seconds=120
    )


def test_complete_fail_and_retry_preserve_explicit_state(store: SqliteStore):
    completed_job = enqueue_course_compile_job(
        store, course_id="course-a", source_revision="src_completed"
    )
    claimed = store.claim_next_knowledge_job("worker-a", lease_seconds=60)
    assert claimed is not None and claimed.job_id == completed_job.job_id

    completed = store.complete_knowledge_job("course-a", completed_job.job_id, "worker-a")
    assert completed.status == "succeeded"
    assert completed.finished_at is not None
    assert completed.lease_owner is None

    retry_job = enqueue_course_compile_job(
        store, course_id="course-a", source_revision="src_retry"
    )
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


def test_retry_ceiling_is_persisted_and_exhausted_jobs_are_not_reclaimed(
    store: SqliteStore,
) -> None:
    job = enqueue_material_index_job(
        store,
        course_id="course-a",
        material_id="material-a",
        revision=9,
        max_attempts=2,
    )
    first = store.claim_next_knowledge_job("worker-a", lease_seconds=60)
    assert first is not None and first.job_id == job.job_id and first.attempt == 1
    retryable = store.fail_knowledge_job(
        "course-a",
        job.job_id,
        "worker-a",
        "temporary provider outage",
        retryable=True,
        error_code="provider_timeout",
    )
    assert retryable.status == "retryable"
    store.retry_knowledge_job("course-a", job.job_id)

    second = store.claim_next_knowledge_job("worker-b", lease_seconds=60)
    assert second is not None and second.job_id == job.job_id and second.attempt == 2
    exhausted = store.fail_knowledge_job(
        "course-a",
        job.job_id,
        "worker-b",
        "temporary provider outage again",
        retryable=True,
        error_code="provider_timeout",
    )
    assert exhausted.status == "failed"
    assert exhausted.error_code == "retry_limit_exhausted"
    assert exhausted.error_detail == "temporary provider outage again"
    with pytest.raises(ValueError, match="Only failed or retryable"):
        store.retry_knowledge_job("course-a", job.job_id)
    assert store.claim_next_knowledge_job("worker-c", lease_seconds=60) is None
