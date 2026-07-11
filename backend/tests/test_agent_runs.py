"""V2-F1 agent run, agent step, and agent-run-owned model call tests.

All providers are fakes; no external model is ever contacted.  These tests
verify the durable schema, course/session isolation, budget gating and the
backward-compatible migration of legacy ``model_call_audits`` rows.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from pathlib import Path

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.agent_runs import AgentRun, AgentRunStatus, AgentStep, WorkflowKind
from app.schemas.evidence import SourceFragment
from app.schemas.foxsay import Course, Material
from app.schemas.model_calls import ModelCallReservationRequest
from app.services.knowledge_jobs import (
    enqueue_course_compile_job,
    enqueue_material_index_job,
)


def _fingerprint(seed: bytes = b"agent-run-test-input") -> str:
    return hashlib.sha256(seed).hexdigest()


def _make_run(
    course_id: str,
    session_id: str,
    *,
    run_id: str | None = None,
    token_budget: int = 1000,
    status: AgentRunStatus = "accepted",
    workflow_kind: WorkflowKind = "quick_answer",
) -> AgentRun:
    return AgentRun(
        run_id=run_id or str(uuid.uuid4()),
        turn_id=str(uuid.uuid4()),
        course_id=course_id,
        session_id=session_id,
        workflow_kind=workflow_kind,
        source_revision="src-test",
        knowledge_revision="kn-test",
        status=status,
        token_budget=token_budget,
        created_at="2026-01-01 00:00:00",
        updated_at="2026-01-01 00:00:00",
    )


def _make_run_reservation(
    course_id: str,
    run_id: str,
    *,
    call_id: str | None = None,
    input_tokens: int = 10,
    output_tokens: int = 20,
    course_budget: int = 5000,
) -> ModelCallReservationRequest:
    return ModelCallReservationRequest(
        call_id=call_id or str(uuid.uuid4()),
        course_id=course_id,
        owner_type="agent_run",
        run_id=run_id,
        budget_scope="interactive",
        call_kind="text",
        purpose="quick_answer",
        provider="deepseek",
        model="deepseek-v4-flash",
        request_fingerprint=_fingerprint(),
        input_token_upper_bound=input_tokens,
        max_output_tokens=output_tokens,
        course_budget_tokens=course_budget,
    )


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    db = SqliteStore(tmp_path / "agent-runs.db")
    db.create_course(Course(id="alpha", title="线性代数", status="empty"))
    db.create_course(Course(id="beta", title="离散数学", status="empty"))
    db.create_chat_session("session-alpha", "alpha", "对话 A")
    db.create_chat_session("session-beta", "beta", "对话 B")
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Acceptance 1: fresh DB creates agent_runs and agent_steps tables
# ---------------------------------------------------------------------------


def test_fresh_db_creates_agent_runs_and_steps_tables(store: SqliteStore) -> None:
    rows = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('agent_runs','agent_steps')"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert names == {"agent_runs", "agent_steps"}

    # model_call_audits should have been migrated to include owner columns.
    cols = {
        r["name"]
        for r in store._conn.execute("PRAGMA table_info(model_call_audits)").fetchall()
    }
    assert {"owner_type", "owner_id", "budget_scope", "run_id"} <= cols


# ---------------------------------------------------------------------------
# Acceptance 2: legacy DB migration preserves data
# ---------------------------------------------------------------------------


_LEGACY_KNOWLEDGE_JOBS_SQL = """
CREATE TABLE knowledge_jobs (
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
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (material_id) REFERENCES materials(id),
    CHECK (job_type IN ('index_material', 'compile_course', 'extract_semantic_atoms', 'compile_terms', 'compile_kcs', 'extract_kc_relations', 'visual_analysis')),
    CHECK (scope IN ('material', 'course')),
    CHECK (status IN ('queued', 'running', 'succeeded', 'retryable', 'failed')),
    CHECK (revision >= 0),
    CHECK (attempt >= 0),
    CHECK (max_attempts > 0),
    CHECK (token_budget IS NULL OR token_budget > 0),
    CHECK ((scope = 'material' AND material_id IS NOT NULL) OR (scope = 'course' AND material_id IS NULL))
)
"""

_LEGACY_MODEL_CALL_AUDITS_SQL = """
CREATE TABLE model_call_audits (
    call_id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    job_attempt INTEGER NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    call_kind TEXT NOT NULL,
    purpose TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    input_token_upper_bound INTEGER NOT NULL,
    max_output_tokens INTEGER NOT NULL,
    reserved_tokens INTEGER NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    reasoning_tokens INTEGER,
    total_tokens INTEGER,
    usage_source TEXT NOT NULL,
    accounted_tokens INTEGER NOT NULL,
    course_budget_tokens INTEGER NOT NULL,
    job_budget_tokens INTEGER,
    elapsed_ms INTEGER,
    error_code TEXT,
    error_detail TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (job_id) REFERENCES knowledge_jobs(job_id),
    CHECK (job_attempt > 0),
    CHECK (call_kind IN ('text', 'embedding', 'vision')),
    CHECK (status IN ('reserved', 'succeeded', 'failed', 'rejected')),
    CHECK (input_token_upper_bound > 0),
    CHECK (max_output_tokens > 0),
    CHECK (reserved_tokens >= 0),
    CHECK (input_tokens IS NULL OR input_tokens >= 0),
    CHECK (output_tokens IS NULL OR output_tokens >= 0),
    CHECK (reasoning_tokens IS NULL OR reasoning_tokens >= 0),
    CHECK (total_tokens IS NULL OR total_tokens >= 0),
    CHECK (usage_source IN ('provider', 'estimated', 'unavailable')),
    CHECK (accounted_tokens >= 0),
    CHECK (course_budget_tokens > 0),
    CHECK (job_budget_tokens IS NULL OR job_budget_tokens > 0),
    CHECK (elapsed_ms IS NULL OR elapsed_ms >= 0)
)
"""


def test_legacy_model_call_audits_migrates_safely(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    raw = sqlite3.connect(str(db_path))
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.execute(
        "CREATE TABLE courses (id TEXT PRIMARY KEY, title TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'empty', teacher TEXT, exam_date TEXT, "
        "summary TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    raw.execute(_LEGACY_KNOWLEDGE_JOBS_SQL)
    raw.execute(_LEGACY_MODEL_CALL_AUDITS_SQL)
    raw.execute("INSERT INTO courses (id, title, status) VALUES ('legacy', 'Legacy', 'empty')")
    raw.execute(
        "INSERT INTO knowledge_jobs (job_id, course_id, material_id, job_type, revision, "
        "scope, status, attempt, idempotency_key, token_budget) "
        "VALUES ('job-legacy', 'legacy', NULL, 'compile_course', 0, 'course', 'succeeded', 1, 'legacy-key', 1000)"
    )
    raw.execute(
        "INSERT INTO model_call_audits (call_id, course_id, job_id, job_attempt, "
        "source_revision, knowledge_revision, call_kind, purpose, provider, model, "
        "request_fingerprint, status, input_token_upper_bound, max_output_tokens, "
        "reserved_tokens, usage_source, accounted_tokens, course_budget_tokens, "
        "job_budget_tokens) VALUES ('call-legacy', 'legacy', 'job-legacy', 1, 'src', 'kn', "
        "'text', 'legacy', 'deepseek', 'm', 'fp', 'succeeded', 10, 5, 15, 'provider', 15, 100, 100)"
    )
    raw.execute("PRAGMA foreign_keys=ON")
    raw.commit()
    raw.close()

    # Open with current code -> _migrate rebuilds model_call_audits.
    store = SqliteStore(db_path)
    try:
        audit = store.get_model_call_audit("legacy", "call-legacy")
        assert audit is not None
        # Data preserved.
        assert audit.job_id == "job-legacy"
        assert audit.job_attempt == 1
        assert audit.status == "succeeded"
        assert audit.accounted_tokens == 15
        # New owner columns back-filled for legacy rows.
        assert audit.owner_type == "knowledge_job"
        assert audit.owner_id == "job-legacy"
        assert audit.budget_scope == "knowledge_build"
        assert audit.run_id is None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Acceptance 3: create_agent_run rejects cross-course sessions
# ---------------------------------------------------------------------------


def test_create_agent_run_rejects_session_from_another_course(store: SqliteStore) -> None:
    run = _make_run("alpha", "session-beta")  # beta session under alpha course
    with pytest.raises(ValueError, match="does not belong"):
        store.create_agent_run(run)


def test_create_agent_run_rejects_unknown_session(store: SqliteStore) -> None:
    run = _make_run("alpha", "no-such-session")
    with pytest.raises(ValueError, match="unknown chat session"):
        store.create_agent_run(run)


def test_create_agent_run_persists_and_round_trips(store: SqliteStore) -> None:
    run = _make_run("alpha", "session-alpha", run_id="run-1", workflow_kind="deep_dive")
    store.create_agent_run(run)
    loaded = store.get_agent_run("alpha", "run-1")
    assert loaded is not None
    assert loaded.run_id == "run-1"
    assert loaded.course_id == "alpha"
    assert loaded.session_id == "session-alpha"
    assert loaded.workflow_kind == "deep_dive"
    assert loaded.status == "accepted"
    assert loaded.token_budget == 1000


# ---------------------------------------------------------------------------
# Acceptance 4: update_agent_run_status with wrong course_id is a no-op
# ---------------------------------------------------------------------------


def test_update_agent_run_status_with_wrong_course_is_a_noop(store: SqliteStore) -> None:
    run = _make_run("alpha", "session-alpha", run_id="run-2")
    store.create_agent_run(run)
    # Wrong course_id -> no update, no error.
    store.update_agent_run_status("beta", "run-2", "completed")
    loaded = store.get_agent_run("alpha", "run-2")
    assert loaded is not None
    assert loaded.status == "accepted"  # unchanged

    # Correct course_id -> updates.
    store.update_agent_run_status("alpha", "run-2", "completed")
    loaded = store.get_agent_run("alpha", "run-2")
    assert loaded is not None
    assert loaded.status == "completed"


def test_get_agent_run_returns_none_for_wrong_course(store: SqliteStore) -> None:
    run = _make_run("alpha", "session-alpha", run_id="run-3")
    store.create_agent_run(run)
    assert store.get_agent_run("beta", "run-3") is None


# ---------------------------------------------------------------------------
# Agent steps
# ---------------------------------------------------------------------------


def test_create_and_update_agent_steps(store: SqliteStore) -> None:
    run = _make_run("alpha", "session-alpha", run_id="run-steps", token_budget=10000)
    store.create_agent_run(run)
    # Reserve a real agent-run model call so the step can link to it.
    reservation = _make_run_reservation("alpha", "run-steps", call_id="call-real")
    store.reserve_agent_run_model_call(reservation)

    step = AgentStep(
        step_id="step-1",
        run_id="run-steps",
        agent_role="scout",
        step_type="retrieve",
        status="pending",
        created_at="2026-01-01 00:00:00",
    )
    store.create_agent_step(step)

    store.update_agent_step(
        "step-1",
        "completed",
        elapsed_ms=42,
        output_type="evidence_pack",
        model_call_id="call-real",
    )

    steps = store.get_agent_steps("run-steps")
    assert len(steps) == 1
    assert steps[0].step_id == "step-1"
    assert steps[0].status == "completed"
    assert steps[0].elapsed_ms == 42
    assert steps[0].output_type == "evidence_pack"
    assert steps[0].model_call_id == "call-real"
    assert steps[0].completed_at is not None


# ---------------------------------------------------------------------------
# Acceptance 5: reserve_agent_run_model_call rejects terminal status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "terminal_status",
    ["completed", "failed", "cancelled", "interrupted", "stale"],
)
def test_reserve_agent_run_model_call_rejects_terminal_status(
    store: SqliteStore, terminal_status: AgentRunStatus
) -> None:
    run = _make_run(
        "alpha", "session-alpha", run_id=f"run-{terminal_status}", status=terminal_status
    )
    store.create_agent_run(run)
    request = _make_run_reservation("alpha", run.run_id)
    with pytest.raises(ValueError, match="terminal status"):
        store.reserve_agent_run_model_call(request)


def test_reserve_agent_run_model_call_rejects_unknown_run(store: SqliteStore) -> None:
    request = _make_run_reservation("alpha", "no-such-run")
    with pytest.raises(ValueError, match="unknown agent run"):
        store.reserve_agent_run_model_call(request)


def test_reserve_agent_run_model_call_rejects_cross_course_run(store: SqliteStore) -> None:
    run = _make_run("alpha", "session-alpha", run_id="run-cross")
    store.create_agent_run(run)
    request = _make_run_reservation("beta", "run-cross")  # beta course, alpha run
    with pytest.raises(ValueError, match="unknown agent run"):
        store.reserve_agent_run_model_call(request)


# ---------------------------------------------------------------------------
# Acceptance 6: reserve_agent_run_model_call rejects when budget exceeded
# (no provider is contacted)
# ---------------------------------------------------------------------------


def test_reserve_agent_run_model_call_rejects_when_run_budget_exceeded(
    store: SqliteStore,
) -> None:
    run = _make_run(
        "alpha",
        "session-alpha",
        run_id="run-budget",
        token_budget=5,  # too small for a 30-token reservation
    )
    store.create_agent_run(run)
    request = _make_run_reservation("alpha", "run-budget", input_tokens=10, output_tokens=20)
    audit = store.reserve_agent_run_model_call(request)
    assert audit.status == "rejected"
    assert audit.error_code == "token_budget_exhausted"
    assert audit.accounted_tokens == 0
    assert audit.owner_type == "agent_run"
    assert audit.owner_id == "run-budget"
    assert audit.run_id == "run-budget"


def test_reserve_agent_run_model_call_rejects_when_course_interactive_budget_exceeded(
    store: SqliteStore,
) -> None:
    # First run exhausts the course interactive budget (course_budget=50).
    run_a = _make_run(
        "alpha",
        "session-alpha",
        run_id="run-interactive-a",
        token_budget=10000,
    )
    store.create_agent_run(run_a)
    # Reserve a call that uses most of the 50-token interactive budget.
    first = store.reserve_agent_run_model_call(
        _make_run_reservation(
            "alpha",
            "run-interactive-a",
            input_tokens=20,
            output_tokens=20,
            course_budget=50,
        )
    )
    assert first.status == "reserved"

    # Second run in the same course should be rejected at the interactive budget.
    run_b = _make_run(
        "alpha",
        "session-alpha",
        run_id="run-interactive-b",
        token_budget=10000,
    )
    store.create_agent_run(run_b)
    second = store.reserve_agent_run_model_call(
        _make_run_reservation(
            "alpha",
            "run-interactive-b",
            input_tokens=20,
            output_tokens=20,
            course_budget=50,  # same course budget -> only 10 tokens left
        )
    )
    assert second.status == "rejected"
    assert second.error_code == "token_budget_exhausted"


def test_reserve_agent_run_model_call_succeeds_for_active_run(store: SqliteStore) -> None:
    run = _make_run("alpha", "session-alpha", run_id="run-ok", token_budget=10000)
    store.create_agent_run(run)
    request = _make_run_reservation("alpha", "run-ok", input_tokens=10, output_tokens=20)
    audit = store.reserve_agent_run_model_call(request)
    assert audit.status == "reserved"
    assert audit.owner_type == "agent_run"
    assert audit.owner_id == "run-ok"
    assert audit.run_id == "run-ok"
    assert audit.budget_scope == "interactive"
    assert audit.job_id is None
    assert audit.job_attempt is None
    assert audit.accounted_tokens == request.reserved_tokens


# ---------------------------------------------------------------------------
# Acceptance 7: existing reserve_model_call (knowledge_job path) unchanged
# ---------------------------------------------------------------------------


@pytest.fixture
def knowledge_job_store(tmp_path: Path) -> SqliteStore:
    """A store with one claimed course-scoped knowledge job, like D1a tests."""
    store = SqliteStore(tmp_path / "kj.db")
    store.create_course(Course(id="linear", title="线性代数", status="empty"))
    store.create_material(
        Material(
            id="vectors",
            course_id="linear",
            filename="vectors.md",
            kind="text_note",
            status="ready",
            revision=1,
            content_hash="vectors-hash",
        )
    )
    store.replace_source_fragments(
        "linear",
        "vectors",
        1,
        [
            SourceFragment(
                fragment_id="linear-vectors-0",
                course_id="linear",
                material_id="vectors",
                material_revision=1,
                ordinal=0,
                text="向量空间对线性组合封闭。",
                heading_path=["向量空间"],
                char_start=0,
                char_end=12,
                kind="paragraph",
                parser_name="synthetic-f1",
                content_hash="vectors-hash",
            )
        ],
    )
    index_job = enqueue_material_index_job(
        store, course_id="linear", material_id="vectors", revision=1
    )
    claimed = store.claim_next_knowledge_job("seed-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == index_job.job_id
    store.complete_knowledge_job("linear", index_job.job_id, "seed-worker")
    yield store
    store.close()


def _claim_course_job(store: SqliteStore, *, token_budget: int = 1000):
    manifest = store.get_compilable_source_manifest("linear")
    assert manifest is not None
    job = enqueue_course_compile_job(
        store,
        course_id="linear",
        source_revision=manifest[0],
        token_budget=token_budget,
    )
    claimed = store.claim_next_knowledge_job("model-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == job.job_id
    return claimed


def test_reserve_model_call_knowledge_job_path_unchanged(
    knowledge_job_store: SqliteStore,
) -> None:
    job = _claim_course_job(knowledge_job_store, token_budget=1000)
    assert job.target_source_revision is not None
    assert job.target_knowledge_revision is not None
    request = ModelCallReservationRequest(
        call_id=str(uuid.uuid4()),
        course_id="linear",
        job_id=job.job_id,
        lease_owner="model-worker",
        job_attempt=job.attempt,
        source_revision=job.target_source_revision,
        knowledge_revision=job.target_knowledge_revision,
        call_kind="text",
        purpose="semantic_atom_extract",
        provider="deepseek",
        model="deepseek-v4-flash",
        request_fingerprint=_fingerprint(b"kj"),
        input_token_upper_bound=10,
        max_output_tokens=20,
        course_budget_tokens=500,
    )
    audit = knowledge_job_store.reserve_model_call(request)
    assert audit.status == "reserved"
    # Legacy defaults preserved.
    assert audit.owner_type == "knowledge_job"
    assert audit.owner_id == job.job_id
    assert audit.budget_scope == "knowledge_build"
    assert audit.run_id is None
    assert audit.job_id == job.job_id
    assert audit.job_attempt == job.attempt


def test_reserve_model_call_rejects_agent_run_request(
    knowledge_job_store: SqliteStore,
) -> None:
    _claim_course_job(knowledge_job_store)
    request = ModelCallReservationRequest(
        call_id=str(uuid.uuid4()),
        course_id="linear",
        owner_type="agent_run",
        run_id="some-run",
        budget_scope="interactive",
        call_kind="text",
        purpose="quick_answer",
        provider="deepseek",
        model="deepseek-v4-flash",
        request_fingerprint=_fingerprint(b"bad"),
        input_token_upper_bound=10,
        max_output_tokens=20,
        course_budget_tokens=500,
    )
    with pytest.raises(ValueError, match="only handles knowledge_job owners"):
        knowledge_job_store.reserve_model_call(request)


# ---------------------------------------------------------------------------
# Acceptance 8: session touch/delete/save_message course fence
# ---------------------------------------------------------------------------


def test_touch_chat_session_with_wrong_course_is_a_noop(store: SqliteStore) -> None:
    before = store._conn.execute(
        "SELECT updated_at FROM chat_sessions WHERE id = ?", ("session-alpha",)
    ).fetchone()["updated_at"]
    store.touch_chat_session("session-alpha", course_id="beta")
    after = store._conn.execute(
        "SELECT updated_at FROM chat_sessions WHERE id = ?", ("session-alpha",)
    ).fetchone()["updated_at"]
    assert before == after  # unchanged -> no-op


def test_touch_chat_session_with_correct_course_updates(store: SqliteStore) -> None:
    store.touch_chat_session("session-alpha", course_id="alpha")
    after = store._conn.execute(
        "SELECT updated_at FROM chat_sessions WHERE id = ?", ("session-alpha",)
    ).fetchone()["updated_at"]
    assert after is not None


def test_delete_chat_session_with_wrong_course_is_a_noop(store: SqliteStore) -> None:
    store.delete_chat_session("session-alpha", course_id="beta")
    # Session-alpha should still exist.
    row = store._conn.execute(
        "SELECT 1 FROM chat_sessions WHERE id = ?", ("session-alpha",)
    ).fetchone()
    assert row is not None


def test_delete_chat_session_with_correct_course_removes(store: SqliteStore) -> None:
    store.delete_chat_session("session-alpha", course_id="alpha")
    row = store._conn.execute(
        "SELECT 1 FROM chat_sessions WHERE id = ?", ("session-alpha",)
    ).fetchone()
    assert row is None


def test_save_chat_message_rejects_cross_course_session(store: SqliteStore) -> None:
    with pytest.raises(ValueError, match="does not belong"):
        store.save_chat_message(
            "msg-1", "alpha", "user", "hello", session_id="session-beta"
        )


def test_save_chat_message_with_matching_session_succeeds(store: SqliteStore) -> None:
    store.save_chat_message(
        "msg-2", "alpha", "user", "hello", session_id="session-alpha"
    )
    row = store._conn.execute(
        "SELECT * FROM chat_messages WHERE id = ?", ("msg-2",)
    ).fetchone()
    assert row is not None
    assert row["course_id"] == "alpha"
    assert row["session_id"] == "session-alpha"


def test_save_chat_message_unknown_session_rejected(store: SqliteStore) -> None:
    with pytest.raises(ValueError, match="unknown chat session"):
        store.save_chat_message(
            "msg-3", "alpha", "user", "hello", session_id="no-such-session"
        )


# ---------------------------------------------------------------------------
# Schema validators
# ---------------------------------------------------------------------------


def test_reservation_request_knowledge_job_requires_job_id() -> None:
    with pytest.raises(ValueError, match="knowledge_job owners require job_id"):
        ModelCallReservationRequest(
            call_id="c",
            course_id="course",
            owner_type="knowledge_job",
            call_kind="text",
            purpose="p",
            provider="deepseek",
            model="m",
            request_fingerprint=_fingerprint(),
            input_token_upper_bound=1,
            max_output_tokens=1,
            course_budget_tokens=1,
        )


def test_reservation_request_agent_run_requires_run_id() -> None:
    with pytest.raises(ValueError, match="agent_run owners require run_id"):
        ModelCallReservationRequest(
            call_id="c",
            course_id="course",
            owner_type="agent_run",
            call_kind="text",
            purpose="p",
            provider="deepseek",
            model="m",
            request_fingerprint=_fingerprint(),
            input_token_upper_bound=1,
            max_output_tokens=1,
            course_budget_tokens=1,
        )
