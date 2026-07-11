import json
import sqlite3
import threading
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.schemas.foxsay import (
    ChapterWiki,
    Course,
    CourseSkeleton,
    Citation,
    DMAP,
    KC,
    Material,
    MerkleTree,
    Note,
    ReviewPlan,
)
from app.schemas.knowledge_jobs import KnowledgeJob, KnowledgeJobCreate
from app.schemas.agent_runs import AGENT_RUN_ACTIVE_STATUSES, AgentRun, AgentStep
from app.schemas.model_calls import (
    CourseModelBudget,
    ModelCallAudit,
    ModelCallReservationRequest,
    ModelCallUsage,
)
from app.schemas.semantic_atoms import SemanticAtom, SemanticAtomCompilation
from app.schemas.terms import (
    TERM_COMPILER_VERSION,
    Term,
    TermCompilation,
    build_term_id,
    normalise_term_key,
)
from app.schemas.knowledge_components import (
    KC_COMPILER_VERSION,
    KnowledgeComponent,
    build_knowledge_component_id,
)
from app.schemas.kc_relations import (
    KC_RELATION_COMPILER_VERSION,
    KCRelation,
    build_kc_relation_id,
)
from app.services.semantic_atom_compiler import (
    SEMANTIC_ATOM_COMPILER_VERSION,
    build_semantic_atom_id,
)
from app.schemas.course_projection import CourseCompilation, CourseOutline
from app.schemas.evidence import EvidenceRef, SourceFragment
from app.services.source_revision import build_knowledge_revision, build_source_revision

_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "foxsay.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'empty',
    teacher TEXT,
    exam_date TEXT,
    summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    file_path TEXT,
    degraded INTEGER NOT NULL DEFAULT 0,
    parsed_text TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 0),
    content_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS skeletons (
    course_id TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS review_plans (
    course_id TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    step TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '新对话',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT,
    confidence_status TEXT,
    refusal_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS review_sessions (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    current_day INTEGER NOT NULL DEFAULT 1,
    current_step TEXT,
    completed_steps TEXT NOT NULL DEFAULT '[]',
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS user_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ===== Wiki-First Pipeline (阶段 2 新增) =====

CREATE TABLE IF NOT EXISTS dmaps (
    course_id TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS merkle_trees (
    course_id TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS wiki_kcs (
    kc_id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    chapter_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    layer TEXT NOT NULL DEFAULT 'micro',
    bloom_level TEXT NOT NULL DEFAULT 'Understanding',
    data_json TEXT NOT NULL,
    valid_at TEXT NOT NULL,
    invalid_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    content_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_wiki_kcs_course ON wiki_kcs(course_id);
CREATE INDEX IF NOT EXISTS idx_wiki_kcs_chapter ON wiki_kcs(course_id, chapter_id);

CREATE TABLE IF NOT EXISTS wiki_chapters (
    chapter_id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS course_indices (
    course_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_citations_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
CREATE INDEX IF NOT EXISTS idx_notes_course ON notes(course_id);

CREATE TABLE IF NOT EXISTS extracted_assets (
    asset_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    element_type TEXT NOT NULL,
    sequential_label TEXT NOT NULL,
    page_number INTEGER NOT NULL DEFAULT 1,
    closest_heading TEXT NOT NULL DEFAULT '',
    storage_path TEXT NOT NULL DEFAULT '',
    alt_text TEXT NOT NULL DEFAULT '',
    x0 REAL, y0 REAL, x1 REAL, y1 REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_asset_material ON extracted_assets(material_id);
CREATE INDEX IF NOT EXISTS idx_asset_course ON extracted_assets(course_id);

-- ===== Knowledge System V2: durable material evidence =====

CREATE TABLE IF NOT EXISTS source_fragments (
    fragment_id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    material_revision INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    heading_path_json TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    slide_start INTEGER,
    slide_end INTEGER,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    kind TEXT NOT NULL,
    asset_id TEXT,
    parser_name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (material_id) REFERENCES materials(id),
    UNIQUE(course_id, material_id, material_revision, ordinal),
    CHECK (material_revision >= 0),
    CHECK (ordinal >= 0),
    CHECK (char_start >= 0),
    CHECK (char_end >= char_start),
    CHECK (page_start IS NULL OR page_start >= 1),
    CHECK (page_end IS NULL OR page_end >= 1),
    CHECK (page_start IS NULL OR page_end IS NULL OR page_end >= page_start),
    CHECK (slide_start IS NULL OR slide_start >= 1),
    CHECK (slide_end IS NULL OR slide_end >= 1),
    CHECK (slide_start IS NULL OR slide_end IS NULL OR slide_end >= slide_start),
    CHECK (kind IN ('paragraph', 'formula', 'table', 'figure_context', 'visual_derived'))
);
CREATE INDEX IF NOT EXISTS idx_source_fragments_course_revision
    ON source_fragments(course_id, material_revision, material_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_source_fragments_material_revision
    ON source_fragments(course_id, material_id, material_revision, ordinal);

-- ===== Knowledge System V2: persistent, recoverable job queue =====

CREATE TABLE IF NOT EXISTS knowledge_jobs (
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
    CHECK (
        (scope = 'material' AND material_id IS NOT NULL)
        OR (scope = 'course' AND material_id IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_knowledge_jobs_claim
    ON knowledge_jobs(status, lease_expires_at, created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_jobs_course
    ON knowledge_jobs(course_id, revision, created_at);

-- V2-E: an explicit asset selection is immutable job input. Visual output is
-- intentionally isolated from source facts until a later evidence projection
-- validates and publishes it.
CREATE TABLE IF NOT EXISTS visual_analysis_requests (
    job_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    PRIMARY KEY (job_id, asset_id),
    FOREIGN KEY (job_id) REFERENCES knowledge_jobs(job_id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    CHECK (reason_code IN ('missing_alt_text', 'unreadable_formula', 'unreadable_diagram'))
);
CREATE INDEX IF NOT EXISTS idx_visual_requests_course_revision
    ON visual_analysis_requests(course_id, source_revision, job_id);

CREATE TABLE IF NOT EXISTS visual_analysis_results (
    job_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    model_call_id TEXT NOT NULL,
    analysis_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (job_id, asset_id),
    FOREIGN KEY (job_id, asset_id) REFERENCES visual_analysis_requests(job_id, asset_id),
    FOREIGN KEY (model_call_id) REFERENCES model_call_audits(call_id)
);

-- ===== Knowledge System V2: model-call audit and budget reservations =====

CREATE TABLE IF NOT EXISTS course_model_budgets (
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    token_budget INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (course_id, source_revision),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    CHECK (token_budget > 0)
);

CREATE TABLE IF NOT EXISTS model_call_audits (
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
);
CREATE INDEX IF NOT EXISTS idx_model_call_audits_course_source
    ON model_call_audits(course_id, source_revision, started_at DESC, call_id DESC);
CREATE INDEX IF NOT EXISTS idx_model_call_audits_job
    ON model_call_audits(job_id, started_at DESC, call_id DESC);
-- idx_model_call_audits_owner is created by _migrate_model_call_audit_owner
-- because the table starts with the legacy schema (no owner_type column).

-- ===== Knowledge System V2-F1: agent runs and steps =====
-- An agent run is the interactive counterpart to a knowledge_job: a course-
-- scoped, session-bound owner of an audited model workflow (quick answer,
-- review session, study artifact, ...).  It does NOT require a knowledge_job
-- lease and owns its own token budget; agent_steps reference either a
-- model_call_audits row (for steps that made a provider call) or only an
-- input_fingerprint (for retrieval/skipped steps).  No chain-of-thought is
-- persisted here.

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    workflow_kind TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'accepted',
    scope_mode TEXT NOT NULL DEFAULT 'all_ready',
    selected_material_ids_json TEXT,  -- JSON array, NULL = all_ready
    selected_note_ids_json TEXT,
    review_context_json TEXT,
    token_budget INTEGER NOT NULL,
    error_code TEXT,
    error_detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    CHECK (workflow_kind IN ('quick_answer', 'deep_dive', 'course_brief', 'study_artifact', 'review_plan', 'review_session', 'btw')),
    CHECK (status IN ('accepted', 'retrieving', 'planning', 'executing', 'composing', 'verifying', 'completed', 'failed', 'interrupted', 'cancelled', 'stale')),
    CHECK (scope_mode IN ('all_ready', 'selected')),
    CHECK (token_budget > 0)
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_course_session
    ON agent_runs(course_id, session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_turn
    ON agent_runs(turn_id);

CREATE TABLE IF NOT EXISTS agent_steps (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent_role TEXT NOT NULL,
    step_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    model_call_id TEXT,  -- references model_call_audits.call_id if set
    output_type TEXT,
    input_fingerprint TEXT,
    elapsed_ms INTEGER,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id),
    FOREIGN KEY (model_call_id) REFERENCES model_call_audits(call_id),
    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    CHECK (elapsed_ms IS NULL OR elapsed_ms >= 0)
);
CREATE INDEX IF NOT EXISTS idx_agent_steps_run
    ON agent_steps(run_id, created_at);

CREATE TABLE IF NOT EXISTS course_compilations (
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    compiler_version TEXT NOT NULL,
    job_id TEXT NOT NULL,
    source_manifest_json TEXT NOT NULL,
    source_fragment_count INTEGER NOT NULL,
    outline_section_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (course_id, knowledge_revision),
    UNIQUE (course_id, source_revision, compiler_version),
    UNIQUE (job_id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (job_id) REFERENCES knowledge_jobs(job_id),
    CHECK (source_fragment_count >= 0),
    CHECK (outline_section_count >= 0),
    CHECK (warning_count >= 0)
);
CREATE INDEX IF NOT EXISTS idx_course_compilations_current
    ON course_compilations(course_id, source_revision, created_at DESC);

CREATE TABLE IF NOT EXISTS course_projection_snapshots (
    course_id TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    projection_kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (course_id, knowledge_revision, projection_kind),
    FOREIGN KEY (course_id, knowledge_revision)
        REFERENCES course_compilations(course_id, knowledge_revision),
    CHECK (projection_kind IN ('course_outline'))
);

CREATE TABLE IF NOT EXISTS semantic_atom_compilations (
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    compiler_version TEXT NOT NULL,
    job_id TEXT NOT NULL,
    atom_count INTEGER NOT NULL,
    rejected_candidate_count INTEGER NOT NULL DEFAULT 0,
    model_call_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (course_id, knowledge_revision),
    UNIQUE (course_id, source_revision, compiler_version),
    UNIQUE (job_id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (job_id) REFERENCES knowledge_jobs(job_id),
    CHECK (atom_count >= 0),
    CHECK (rejected_candidate_count >= 0),
    CHECK (model_call_count >= 0)
);
CREATE INDEX IF NOT EXISTS idx_semantic_atom_compilations_current
    ON semantic_atom_compilations(course_id, source_revision, created_at DESC);

CREATE TABLE IF NOT EXISTS semantic_atoms (
    atom_id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    section_id TEXT NOT NULL,
    atom_type TEXT NOT NULL,
    statement TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    model_call_id TEXT NOT NULL,
    generation_method TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id, knowledge_revision)
        REFERENCES semantic_atom_compilations(course_id, knowledge_revision),
    FOREIGN KEY (model_call_id) REFERENCES model_call_audits(call_id),
    CHECK (atom_type IN ('concept', 'definition', 'formula', 'condition', 'theorem', 'procedure', 'example', 'pitfall')),
    CHECK (generation_method = 'model')
);
CREATE INDEX IF NOT EXISTS idx_semantic_atoms_current
    ON semantic_atoms(course_id, source_revision, knowledge_revision, section_id);

-- ===== Knowledge System V2: rule-derived terminology projection =====

CREATE TABLE IF NOT EXISTS term_compilations (
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    compiler_version TEXT NOT NULL,
    job_id TEXT NOT NULL,
    term_count INTEGER NOT NULL,
    rejected_atom_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (course_id, knowledge_revision),
    UNIQUE (course_id, source_revision, compiler_version),
    UNIQUE (job_id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (job_id) REFERENCES knowledge_jobs(job_id),
    CHECK (term_count >= 0),
    CHECK (rejected_atom_count >= 0)
);
CREATE INDEX IF NOT EXISTS idx_term_compilations_current
    ON term_compilations(course_id, source_revision, created_at DESC);

CREATE TABLE IF NOT EXISTS terms (
    term_id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    term_kind TEXT NOT NULL,
    definition TEXT NOT NULL,
    definition_atom_id TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    generation_method TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id, knowledge_revision)
        REFERENCES term_compilations(course_id, knowledge_revision),
    CHECK (term_kind IN ('concept', 'definition', 'formula', 'theorem', 'procedure')),
    CHECK (generation_method = 'rule'),
    UNIQUE (course_id, source_revision, knowledge_revision, canonical_key)
);
CREATE INDEX IF NOT EXISTS idx_terms_current
    ON terms(course_id, source_revision, knowledge_revision, canonical_key);

CREATE TABLE IF NOT EXISTS term_atom_links (
    term_id TEXT NOT NULL,
    atom_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (term_id, atom_id),
    FOREIGN KEY (term_id) REFERENCES terms(term_id),
    FOREIGN KEY (atom_id) REFERENCES semantic_atoms(atom_id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
CREATE INDEX IF NOT EXISTS idx_term_atom_links_atom
    ON term_atom_links(course_id, source_revision, knowledge_revision, atom_id);

-- ===== Knowledge System V2: rule-derived Term to KC projection =====

CREATE TABLE IF NOT EXISTS knowledge_component_compilations (
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    compiler_version TEXT NOT NULL,
    job_id TEXT NOT NULL,
    kc_count INTEGER NOT NULL,
    rejected_term_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (course_id, knowledge_revision),
    UNIQUE (course_id, source_revision, compiler_version),
    UNIQUE (job_id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (job_id) REFERENCES knowledge_jobs(job_id),
    CHECK (kc_count >= 0),
    CHECK (rejected_term_count >= 0)
);
CREATE INDEX IF NOT EXISTS idx_kc_compilations_current
    ON knowledge_component_compilations(course_id, source_revision, created_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_components (
    kc_id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    term_id TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    definition TEXT NOT NULL,
    section_id TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    generation_method TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id, knowledge_revision)
        REFERENCES knowledge_component_compilations(course_id, knowledge_revision),
    FOREIGN KEY (term_id) REFERENCES terms(term_id),
    CHECK (kind IN ('concept', 'definition', 'formula', 'theorem', 'procedure')),
    CHECK (generation_method = 'rule'),
    UNIQUE (course_id, source_revision, knowledge_revision, term_id)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_components_current
    ON knowledge_components(course_id, source_revision, knowledge_revision, section_id);

-- ===== Knowledge System V2: audited KC relation projection =====

CREATE TABLE IF NOT EXISTS kc_relation_compilations (
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    compiler_version TEXT NOT NULL,
    job_id TEXT NOT NULL,
    relation_count INTEGER NOT NULL,
    rejected_candidate_count INTEGER NOT NULL DEFAULT 0,
    model_call_count INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (course_id, knowledge_revision),
    UNIQUE (course_id, source_revision, compiler_version),
    UNIQUE (job_id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (job_id) REFERENCES knowledge_jobs(job_id),
    CHECK (relation_count >= 0), CHECK (rejected_candidate_count >= 0),
    CHECK (model_call_count = 1)
);
CREATE TABLE IF NOT EXISTS kc_relations (
    relation_id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    source_kc_id TEXT NOT NULL,
    target_kc_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    model_call_id TEXT NOT NULL,
    generation_method TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id, knowledge_revision)
        REFERENCES kc_relation_compilations(course_id, knowledge_revision),
    FOREIGN KEY (source_kc_id) REFERENCES knowledge_components(kc_id),
    FOREIGN KEY (target_kc_id) REFERENCES knowledge_components(kc_id),
    FOREIGN KEY (model_call_id) REFERENCES model_call_audits(call_id),
    CHECK (source_kc_id <> target_kc_id),
    CHECK (relation_type IN ('prerequisite', 'related')),
    CHECK (generation_method = 'model'),
    UNIQUE (course_id, source_revision, knowledge_revision, source_kc_id, target_kc_id, relation_type, model_call_id)
);
CREATE INDEX IF NOT EXISTS idx_kc_relations_current
    ON kc_relations(course_id, source_revision, knowledge_revision, source_kc_id);
"""


class SqliteStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # The current SQLite queue is intentionally single-process.  This lock
        # prevents two in-process workers from interleaving BEGIN IMMEDIATE.
        self._knowledge_job_lock = threading.RLock()
        self._source_fragment_lock = threading.RLock()
        # Vector replacement cannot participate in a SQLite transaction.  In
        # the SQLite MVP, serialise a material revision advance with the
        # corresponding fragment/vector publication so a stale worker cannot
        # delete a newer revision's Qdrant points in the gap between its
        # revision check and the external write.
        self._material_index_publish_lock = threading.RLock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._migrate()
        self._ensure_knowledge_job_logical_identity_indexes()

    def _migrate(self) -> None:
        """Add columns/tables that may be missing from older databases."""
        migrations = [
            "ALTER TABLE chat_messages ADD COLUMN session_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE courses ADD COLUMN summary TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE materials ADD COLUMN parsed_text TEXT",
            # Existing rows remain explicitly identifiable as legacy inputs.
            "ALTER TABLE materials ADD COLUMN revision INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE materials ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE courses ADD COLUMN icon TEXT NOT NULL DEFAULT '📚'",
            "ALTER TABLE knowledge_jobs ADD COLUMN target_source_revision TEXT",
            "ALTER TABLE knowledge_jobs ADD COLUMN target_knowledge_revision TEXT",
            "ALTER TABLE knowledge_jobs ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3",
            # V2-F3: chat messages carry full V2 AnswerEnvelope metadata.
            "ALTER TABLE chat_messages ADD COLUMN run_id TEXT",
            "ALTER TABLE chat_messages ADD COLUMN source_revision TEXT",
            "ALTER TABLE chat_messages ADD COLUMN knowledge_revision TEXT",
            "ALTER TABLE chat_messages ADD COLUMN answer_source TEXT",
            "ALTER TABLE chat_messages ADD COLUMN envelope_json TEXT",
        ]
        for sql in migrations:
            try:
                self._conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists
        self._migrate_knowledge_job_type_constraint()
        self._migrate_model_call_audit_owner()
        self._conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE title = ?",
            ("新对话", "New Chat"),
        )
        self._conn.commit()

    def _migrate_knowledge_job_type_constraint(self) -> None:
        """Extend the old SQLite job-type CHECK without losing durable facts.

        SQLite cannot alter a CHECK in place. The replacement retains every
        stable queue column and leaves foreign-key child tables pointing at
        the same ``knowledge_jobs`` table name; a post-migration integrity
        check makes any unexpected reference break visible at startup.
        """
        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'knowledge_jobs'"
        ).fetchone()
        if row is None:
            raise RuntimeError("knowledge_jobs table is missing during migration")
        table_sql = str(row["sql"] or "")
        if "extract_kc_relations" in table_sql:
            return

        # PRAGMA foreign_keys cannot change inside an active transaction. The
        # store has just completed its small column migrations, so this is a
        # controlled startup-only rebuild before any worker can claim a job.
        self._conn.commit()
        self._conn.execute("PRAGMA foreign_keys=OFF")
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                CREATE TABLE knowledge_jobs_rebuilt (
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
                    CHECK (
                        (scope = 'material' AND material_id IS NOT NULL)
                        OR (scope = 'course' AND material_id IS NULL)
                    )
                )
                """
            )
            self._conn.execute(
                """
                INSERT INTO knowledge_jobs_rebuilt (
                    job_id, course_id, material_id, job_type, revision, scope, status,
                    attempt, max_attempts, idempotency_key, token_budget,
                    target_source_revision, target_knowledge_revision, lease_owner,
                    lease_expires_at, error_code, error_detail, error_at, created_at,
                    updated_at, started_at, finished_at
                )
                SELECT job_id, course_id, material_id, job_type, revision, scope, status,
                       attempt, max_attempts, idempotency_key, token_budget,
                       target_source_revision, target_knowledge_revision, lease_owner,
                       lease_expires_at, error_code, error_detail, error_at, created_at,
                       updated_at, started_at, finished_at
                FROM knowledge_jobs
                """
            )
            self._conn.execute("DROP TABLE knowledge_jobs")
            self._conn.execute("ALTER TABLE knowledge_jobs_rebuilt RENAME TO knowledge_jobs")
            self._conn.execute(
                """
                CREATE INDEX idx_knowledge_jobs_claim
                ON knowledge_jobs(status, lease_expires_at, created_at)
                """
            )
            self._conn.execute(
                """
                CREATE INDEX idx_knowledge_jobs_course
                ON knowledge_jobs(course_id, revision, created_at)
                """
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            self._conn.execute("PRAGMA foreign_keys=ON")
        violations = self._conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                "knowledge_jobs type migration broke foreign-key references; restore the database "
                "and inspect the reported rows before starting FoxSay"
            )

    def _migrate_model_call_audit_owner(self) -> None:
        """Generalise ``model_call_audits`` to support agent-run owners.

        The legacy table had ``job_id TEXT NOT NULL`` and ``job_attempt INTEGER
        NOT NULL`` and no owner identity.  V2-F1 makes ``job_id``/``job_attempt``
        nullable and adds ``owner_type``, ``owner_id``, ``budget_scope`` and
        ``run_id`` so that interactive agent runs can own audited calls without
        a knowledge-job lease.

        SQLite cannot alter NOT NULL or add CHECK constraints in place, so we
        rebuild the table the same way ``_migrate_knowledge_job_type_constraint``
        does.  Existing rows are preserved and back-filled with
        ``owner_type='knowledge_job'``, ``owner_id=job_id``,
        ``budget_scope='knowledge_build'``.
        """
        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'model_call_audits'"
        ).fetchone()
        if row is None:
            raise RuntimeError("model_call_audits table is missing during migration")
        table_sql = str(row["sql"] or "")
        if "owner_type" not in table_sql:
            # Legacy table: rebuild with the owner-generalised schema.
            #
            # PRAGMA foreign_keys cannot change inside an active transaction.
            # The store has just finished its column migrations, so this is a
            # controlled startup-only rebuild before any worker can reserve a
            # call.
            self._conn.commit()
            self._conn.execute("PRAGMA foreign_keys=OFF")
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute(
                    """
                    CREATE TABLE model_call_audits_rebuilt (
                        call_id TEXT PRIMARY KEY,
                        course_id TEXT NOT NULL,
                        job_id TEXT,
                        job_attempt INTEGER,
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
                        owner_type TEXT NOT NULL DEFAULT 'knowledge_job',
                        owner_id TEXT,
                        budget_scope TEXT NOT NULL DEFAULT 'knowledge_build',
                        run_id TEXT,
                        FOREIGN KEY (course_id) REFERENCES courses(id),
                        FOREIGN KEY (job_id) REFERENCES knowledge_jobs(job_id),
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
                        CHECK (elapsed_ms IS NULL OR elapsed_ms >= 0),
                        CHECK (owner_type IN ('knowledge_job', 'agent_run')),
                        CHECK (budget_scope IN ('knowledge_build', 'interactive', 'review', 'artifact')),
                        CHECK (job_attempt IS NULL OR job_attempt > 0)
                    )
                    """
                )
                self._conn.execute(
                    """
                    INSERT INTO model_call_audits_rebuilt (
                        call_id, course_id, job_id, job_attempt, source_revision, knowledge_revision,
                        call_kind, purpose, provider, model, request_fingerprint, status,
                        input_token_upper_bound, max_output_tokens, reserved_tokens, input_tokens,
                        output_tokens, reasoning_tokens, total_tokens, usage_source, accounted_tokens,
                        course_budget_tokens, job_budget_tokens, elapsed_ms, error_code, error_detail,
                        started_at, finished_at, owner_type, owner_id, budget_scope, run_id
                    )
                    SELECT call_id, course_id, job_id, job_attempt, source_revision, knowledge_revision,
                           call_kind, purpose, provider, model, request_fingerprint, status,
                           input_token_upper_bound, max_output_tokens, reserved_tokens, input_tokens,
                           output_tokens, reasoning_tokens, total_tokens, usage_source, accounted_tokens,
                           course_budget_tokens, job_budget_tokens, elapsed_ms, error_code, error_detail,
                           started_at, finished_at,
                           'knowledge_job' AS owner_type,
                           job_id AS owner_id,
                           'knowledge_build' AS budget_scope,
                           NULL AS run_id
                    FROM model_call_audits
                    """
                )
                self._conn.execute("DROP TABLE model_call_audits")
                self._conn.execute("ALTER TABLE model_call_audits_rebuilt RENAME TO model_call_audits")
                self._conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_model_call_audits_course_source
                        ON model_call_audits(course_id, source_revision, started_at DESC, call_id DESC)
                    """
                )
                self._conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_model_call_audits_job
                        ON model_call_audits(job_id, started_at DESC, call_id DESC)
                    """
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                self._conn.execute("PRAGMA foreign_keys=ON")
            violations = self._conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(
                    "model_call_audits owner migration broke foreign-key references; restore the database "
                    "and inspect the reported rows before starting FoxSay"
                )

        # Always ensure the owner index exists.  On a freshly rebuilt table the
        # indexes above already cover it; on an already-migrated database this
        # is a no-op.  CREATE INDEX IF NOT EXISTS is idempotent.
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_model_call_audits_owner
                ON model_call_audits(owner_type, owner_id, started_at DESC, call_id DESC)
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- Courses ---

    def create_course(self, course: Course) -> Course:
        self._conn.execute(
            "INSERT INTO courses (id, title, status, teacher, exam_date, summary, icon) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (course.id, course.title, course.status, course.teacher, course.exam_date, course.summary, course.icon),
        )
        self._conn.commit()
        return course

    def get_course(self, course_id: str) -> Course | None:
        row = self._conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if row is None:
            return None
        mat_count = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM materials WHERE course_id = ?", (course_id,)
        ).fetchone()["cnt"]
        return Course(
            id=row["id"], title=row["title"], status=row["status"],
            teacher=row["teacher"], exam_date=row["exam_date"],
            summary=row["summary"] if "summary" in row.keys() else "",
            icon=row["icon"] if "icon" in row.keys() else "📚",
            material_count=mat_count,
        )

    def get_all_courses(self) -> list[Course]:
        rows = self._conn.execute("SELECT * FROM courses ORDER BY created_at DESC").fetchall()
        courses = []
        for r in rows:
            mat_count = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM materials WHERE course_id = ?", (r["id"],)
            ).fetchone()["cnt"]
            courses.append(Course(
                id=r["id"], title=r["title"], status=r["status"],
                teacher=r["teacher"], exam_date=r["exam_date"],
                summary=r["summary"] if "summary" in r.keys() else "",
                icon=r["icon"] if "icon" in r.keys() else "📚",
                material_count=mat_count,
            ))
        return courses

    def update_course(self, course_id: str, course: Course) -> Course | None:
        existing = self.get_course(course_id)
        if existing is None:
            return None
        self._conn.execute(
            "UPDATE courses SET title=?, status=?, teacher=?, exam_date=?, summary=?, icon=? WHERE id=?",
            (course.title, course.status, course.teacher, course.exam_date, course.summary, course.icon, course_id),
        )
        self._conn.commit()
        return course

    def update_course_summary(self, course_id: str, summary: str) -> None:
        self._conn.execute(
            "UPDATE courses SET summary=? WHERE id=?",
            (summary, course_id),
        )
        self._conn.commit()

    # --- Materials ---

    def create_material(self, material: Material, file_path: str | None = None, degraded: bool = False) -> Material:
        self._conn.execute(
            """
            INSERT INTO materials
                (id, course_id, filename, kind, status, file_path, degraded, revision, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                material.id,
                material.course_id,
                material.filename,
                material.kind,
                material.status,
                file_path,
                int(degraded),
                material.revision,
                material.content_hash,
            ),
        )
        self._conn.commit()
        return material.model_copy(update={"degraded": degraded})

    def _ensure_knowledge_job_logical_identity_indexes(self) -> None:
        """Enforce one durable job per explicit material/course scope.

        SQLite treats ``NULL`` values as distinct in a regular unique index,
        so material and course jobs need separate partial indexes.  We never
        silently delete old queue rows to make this migration succeed: an
        existing duplicate is an auditable integrity error that must be
        resolved deliberately before the service continues.
        """
        statements = (
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_jobs_material_identity
            ON knowledge_jobs(course_id, material_id, job_type, revision)
            WHERE material_id IS NOT NULL
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_jobs_course_identity
            ON knowledge_jobs(course_id, job_type, revision)
            WHERE material_id IS NULL AND target_source_revision IS NULL
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_jobs_course_target_identity
            ON knowledge_jobs(course_id, job_type, target_source_revision)
            WHERE material_id IS NULL AND target_source_revision IS NOT NULL
            """,
        )
        try:
            # Historic course jobs use only their integer revision.  D0 course
            # jobs are instead idempotent by the explicit source manifest.
            self._conn.execute("DROP INDEX IF EXISTS uq_knowledge_jobs_course_identity")
            for statement in statements:
                self._conn.execute(statement)
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            self._conn.rollback()
            raise RuntimeError(
                "knowledge_jobs contains duplicate logical identities; resolve duplicate "
                "course/material/revision job rows before starting FoxSay"
            ) from exc

    def get_material(self, course_id: str, material_id: str) -> Material | None:
        row = self._conn.execute(
            "SELECT * FROM materials WHERE id = ? AND course_id = ?", (material_id, course_id)
        ).fetchone()
        if row is None:
            return None
        return self._material_from_row(row)

    def get_all_materials(self, course_id: str) -> list[Material]:
        rows = self._conn.execute(
            """
            SELECT id, course_id, filename, kind, status, degraded, revision, content_hash
            FROM materials
            WHERE course_id = ?
            ORDER BY created_at DESC
            """,
            (course_id,),
        ).fetchall()
        return [self._material_from_row(row) for row in rows]

    def get_knowledge_status_snapshot(self, course_id: str) -> list[dict[str, Any]]:
        """Read current material/job/fragment facts in one SQLite statement.

        This is a deliberately narrow status projection: it never loads parsed
        Markdown or fragment text, and the statement-level SQLite snapshot
        avoids combining material, job and fragment reads from different
        moments during a worker update.
        """
        if not course_id.strip():
            raise ValueError("course_id is required for knowledge status")
        rows = self._conn.execute(
            """
            SELECT
                m.id AS material_id,
                m.filename AS filename,
                m.kind AS material_kind,
                m.status AS material_status,
                m.revision AS material_revision,
                m.content_hash AS content_hash,
                COALESCE(fragment_counts.fragment_count, 0) AS fragment_count,
                job.status AS job_status,
                job.error_code AS error_code,
                job.error_detail AS error_detail
            FROM materials AS m
            LEFT JOIN (
                SELECT sf.material_id, sf.material_revision, COUNT(*) AS fragment_count
                FROM source_fragments AS sf
                WHERE sf.course_id = ?
                GROUP BY sf.material_id, sf.material_revision
            ) AS fragment_counts
                ON fragment_counts.material_id = m.id
               AND fragment_counts.material_revision = m.revision
            LEFT JOIN knowledge_jobs AS job
                ON job.course_id = m.course_id
               AND job.material_id = m.id
               AND job.revision = m.revision
               AND job.job_type = 'index_material'
            WHERE m.course_id = ?
            ORDER BY m.created_at DESC, m.id
            """,
            (course_id, course_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_compilable_source_manifest(
        self,
        course_id: str,
        *,
        allow_running_index_job_id: str | None = None,
    ) -> tuple[str, str] | None:
        """Return the complete current source manifest only when it is compilable.

        ``allow_running_index_job_id`` exists solely for the material indexer:
        after it has atomically published its fragments but before the worker
        marks that same index job succeeded, it may enqueue the next durable
        course job.  The compiler itself never uses this relaxation.
        """
        if not course_id.strip():
            raise ValueError("course_id is required for source manifest")
        rows = self._conn.execute(
            """
            SELECT
                m.id AS material_id,
                m.revision AS material_revision,
                m.content_hash AS content_hash,
                m.kind AS material_kind,
                m.status AS material_status,
                COALESCE(fragment_counts.fragment_count, 0) AS fragment_count,
                job.job_id AS job_id,
                job.status AS job_status
            FROM materials AS m
            LEFT JOIN (
                SELECT material_id, material_revision, COUNT(*) AS fragment_count
                FROM source_fragments
                WHERE course_id = ?
                GROUP BY material_id, material_revision
            ) AS fragment_counts
                ON fragment_counts.material_id = m.id
               AND fragment_counts.material_revision = m.revision
            LEFT JOIN knowledge_jobs AS job
                ON job.course_id = m.course_id
               AND job.material_id = m.id
               AND job.revision = m.revision
               AND job.job_type = 'index_material'
            WHERE m.course_id = ?
            ORDER BY m.id
            """,
            (course_id, course_id),
        ).fetchall()
        if not rows:
            return None
        normalized_rows = [dict(row) for row in rows]
        for row in normalized_rows:
            current_or_allowed = (
                row["job_status"] == "succeeded"
                or (
                    allow_running_index_job_id is not None
                    and row["job_id"] == allow_running_index_job_id
                    and row["job_status"] == "running"
                )
            )
            if (
                row["material_status"] != "ready"
                or not row["content_hash"]
                or int(row["fragment_count"]) <= 0
                or not current_or_allowed
            ):
                return None
        return build_source_revision(normalized_rows)

    def get_current_course_compilation(
        self, course_id: str, source_revision: str
    ) -> CourseCompilation | None:
        """Read a succeeded compiler header for this exact current source set."""
        row = self._conn.execute(
            """
            SELECT cc.*
            FROM course_compilations AS cc
            INNER JOIN knowledge_jobs AS job
                ON job.job_id = cc.job_id
               AND job.course_id = cc.course_id
               AND job.status = 'succeeded'
               AND job.target_source_revision = cc.source_revision
               AND job.target_knowledge_revision = cc.knowledge_revision
            WHERE cc.course_id = ? AND cc.source_revision = ?
            """,
            (course_id, source_revision),
        ).fetchone()
        return self._row_to_course_compilation(row) if row is not None else None

    def get_latest_course_compilation(self, course_id: str) -> CourseCompilation | None:
        """Return the latest succeeded compilation header for stale-state audit."""
        row = self._conn.execute(
            """
            SELECT cc.*
            FROM course_compilations AS cc
            INNER JOIN knowledge_jobs AS job
                ON job.job_id = cc.job_id
               AND job.course_id = cc.course_id
               AND job.status = 'succeeded'
            WHERE cc.course_id = ?
            ORDER BY cc.created_at DESC, cc.knowledge_revision DESC
            LIMIT 1
            """,
            (course_id,),
        ).fetchone()
        return self._row_to_course_compilation(row) if row is not None else None

    def get_course_compile_job_for_source(
        self, course_id: str, source_revision: str
    ) -> KnowledgeJob | None:
        row = self._conn.execute(
            """
            SELECT * FROM knowledge_jobs
            WHERE course_id = ?
              AND material_id IS NULL
              AND job_type = 'compile_course'
              AND target_source_revision = ?
            ORDER BY created_at DESC, job_id DESC
            LIMIT 1
            """,
            (course_id, source_revision),
        ).fetchone()
        return self._row_to_knowledge_job(row) if row is not None else None

    def get_current_course_outline(
        self, course_id: str, source_revision: str
    ) -> CourseOutline | None:
        """Read only the current, successfully compiled D0 outline snapshot."""
        compilation = self.get_current_course_compilation(course_id, source_revision)
        if compilation is None:
            return None
        row = self._conn.execute(
            """
            SELECT payload_json FROM course_projection_snapshots
            WHERE course_id = ? AND knowledge_revision = ? AND projection_kind = 'course_outline'
            """,
            (course_id, compilation.knowledge_revision),
        ).fetchone()
        if row is None:
            raise RuntimeError("Succeeded course compilation has no course_outline snapshot")
        outline = CourseOutline.model_validate_json(row["payload_json"])
        if (
            outline.course_id != course_id
            or outline.source_revision != source_revision
            or outline.knowledge_revision != compilation.knowledge_revision
        ):
            raise RuntimeError("Course outline snapshot identity does not match compilation header")
        return outline

    def publish_semantic_atoms_if_current(
        self,
        *,
        course_id: str,
        job_id: str,
        job_attempt: int,
        lease_owner: str,
        source_revision: str,
        knowledge_revision: str,
        atoms: list[SemanticAtom],
        rejected_candidate_count: int,
    ) -> bool:
        """Atomically publish only a current, leased, evidence-verified atom set."""
        if job_attempt < 1 or not lease_owner.strip() or rejected_candidate_count < 0:
            raise ValueError("Semantic atom publication requires a claimed lease and valid counts")
        if any(
            atom.course_id != course_id
            or atom.source_revision != source_revision
            or atom.knowledge_revision != knowledge_revision
            for atom in atoms
        ):
            raise ValueError("Semantic atom identity does not match its publication target")

        with self._knowledge_job_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                job = self._conn.execute(
                    """
                    SELECT status, attempt, lease_owner, lease_expires_at,
                           target_source_revision, target_knowledge_revision
                    FROM knowledge_jobs
                    WHERE job_id = ? AND course_id = ? AND job_type = 'extract_semantic_atoms'
                    """,
                    (job_id, course_id),
                ).fetchone()
                if (
                    job is None
                    or job["status"] != "running"
                    or job["attempt"] != job_attempt
                    or job["lease_owner"] != lease_owner
                    or job["lease_expires_at"] is None
                    or job["lease_expires_at"] <= self._conn.execute("SELECT datetime('now')").fetchone()[0]
                    or job["target_source_revision"] != source_revision
                    or job["target_knowledge_revision"] != knowledge_revision
                ):
                    self._conn.rollback()
                    return False
                current_manifest = self.get_compilable_source_manifest(course_id)
                if current_manifest is None or current_manifest[0] != source_revision:
                    self._conn.rollback()
                    return False
                outline = self.get_current_course_outline(course_id, source_revision)
                if outline is None or outline.knowledge_revision != knowledge_revision:
                    self._conn.rollback()
                    return False
                self._validate_semantic_atoms_for_publication(
                    course_id=course_id,
                    job_id=job_id,
                    source_revision=source_revision,
                    knowledge_revision=knowledge_revision,
                    atoms=atoms,
                    outline=outline,
                )
                model_call_count = len({atom.model_call_id for atom in atoms})
                self._conn.execute(
                    """
                    INSERT INTO semantic_atom_compilations (
                        course_id, source_revision, knowledge_revision, compiler_version, job_id,
                        atom_count, rejected_candidate_count, model_call_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(course_id, source_revision, compiler_version) DO NOTHING
                    """,
                    (
                        course_id,
                        source_revision,
                        knowledge_revision,
                        SEMANTIC_ATOM_COMPILER_VERSION,
                        job_id,
                        len(atoms),
                        rejected_candidate_count,
                        model_call_count,
                    ),
                )
                header = self._conn.execute(
                    """
                    SELECT knowledge_revision, job_id, atom_count, rejected_candidate_count, model_call_count
                    FROM semantic_atom_compilations
                    WHERE course_id = ? AND source_revision = ? AND compiler_version = ?
                    """,
                    (course_id, source_revision, SEMANTIC_ATOM_COMPILER_VERSION),
                ).fetchone()
                if (
                    header is None
                    or header["knowledge_revision"] != knowledge_revision
                    or header["job_id"] != job_id
                    or int(header["atom_count"]) != len(atoms)
                    or int(header["rejected_candidate_count"]) != rejected_candidate_count
                    or int(header["model_call_count"]) != model_call_count
                ):
                    raise RuntimeError("Semantic atom target is already bound to another projection")
                for atom in atoms:
                    self._conn.execute(
                        """
                        INSERT INTO semantic_atoms (
                            atom_id, course_id, source_revision, knowledge_revision, section_id,
                            atom_type, statement, evidence_json, model_call_id, generation_method
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(atom_id) DO NOTHING
                        """,
                        (
                            atom.atom_id,
                            atom.course_id,
                            atom.source_revision,
                            atom.knowledge_revision,
                            atom.section_id,
                            atom.atom_type,
                            atom.statement,
                            json.dumps(
                                [evidence.model_dump() for evidence in atom.evidence],
                                ensure_ascii=False,
                                separators=(",", ":"),
                                sort_keys=True,
                            ),
                            atom.model_call_id,
                            atom.generation_method,
                        ),
                    )
                self._enqueue_term_job_if_absent(
                    course_id=course_id,
                    source_revision=source_revision,
                    knowledge_revision=knowledge_revision,
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return True

    def _enqueue_term_job_if_absent(
        self,
        *,
        course_id: str,
        source_revision: str,
        knowledge_revision: str,
    ) -> None:
        """Create the zero-model child in its semantic publication transaction."""
        existing = self._conn.execute(
            """
            SELECT job_id FROM knowledge_jobs
            WHERE course_id = ? AND job_type = 'compile_terms'
              AND target_source_revision = ?
            """,
            (course_id, source_revision),
        ).fetchone()
        if existing is not None:
            return
        next_revision = self._conn.execute(
            """
            SELECT COALESCE(MAX(revision), -1) + 1 AS next_revision
            FROM knowledge_jobs
            WHERE course_id = ? AND material_id IS NULL AND job_type = 'compile_terms'
            """,
            (course_id,),
        ).fetchone()
        if next_revision is None:
            raise RuntimeError("Could not allocate term compilation job revision")
        self._conn.execute(
            """
            INSERT INTO knowledge_jobs (
                job_id, course_id, material_id, job_type, revision, scope, status,
                attempt, max_attempts, idempotency_key, token_budget,
                target_source_revision, target_knowledge_revision
            ) VALUES (?, ?, NULL, 'compile_terms', ?, 'course', 'queued', 0, 3, ?, NULL, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                course_id,
                int(next_revision["next_revision"]),
                f"knowledge:compile_terms:{course_id}:source:{source_revision}",
                source_revision,
                knowledge_revision,
            ),
        )

    def _validate_semantic_atoms_for_publication(
        self,
        *,
        course_id: str,
        job_id: str,
        source_revision: str,
        knowledge_revision: str,
        atoms: list[SemanticAtom],
        outline: CourseOutline,
    ) -> None:
        fragments = self.list_current_ready_source_fragments(course_id)
        fragment_by_id = {fragment.fragment_id: fragment for fragment in fragments}
        section_fragment_ids = {
            section.section_id: {evidence.fragment_id for evidence in section.evidence}
            for section in outline.sections
        }
        for atom in atoms:
            allowed_fragment_ids = section_fragment_ids.get(atom.section_id)
            if allowed_fragment_ids is None:
                raise ValueError("Semantic atom section is absent from the current course outline")
            evidence_ids = [evidence.fragment_id for evidence in atom.evidence]
            if len(set(evidence_ids)) != len(evidence_ids) or not evidence_ids or any(
                fragment_id not in allowed_fragment_ids or fragment_id not in fragment_by_id
                for fragment_id in evidence_ids
            ):
                raise ValueError("Semantic atom evidence is not current evidence for its outline section")
            expected_evidence = [
                fragment_by_id[fragment_id] for fragment_id in evidence_ids
            ]
            if [evidence.model_dump() for evidence in atom.evidence] != [
                EvidenceRef.from_source_fragment(fragment).model_dump()
                for fragment in expected_evidence
            ]:
                raise ValueError("Semantic atom evidence was not rehydrated from canonical fragments")
            expected_atom_id = build_semantic_atom_id(
                course_id=course_id,
                source_revision=source_revision,
                knowledge_revision=knowledge_revision,
                section_id=atom.section_id,
                atom_type=atom.atom_type,
                statement=atom.statement,
                evidence_fragment_ids=evidence_ids,
            )
            if atom.atom_id != expected_atom_id:
                raise ValueError("Semantic atom ID is not the stable evidence-derived identity")
            audit = self._conn.execute(
                """
                SELECT status FROM model_call_audits
                WHERE call_id = ? AND course_id = ? AND job_id = ?
                  AND source_revision = ? AND knowledge_revision = ?
                """,
                (atom.model_call_id, course_id, job_id, source_revision, knowledge_revision),
            ).fetchone()
            if audit is None or audit["status"] != "succeeded":
                raise ValueError("Semantic atom model-call audit is not a succeeded current job call")

    def get_current_semantic_atoms(
        self, course_id: str, source_revision: str
    ) -> list[SemanticAtom]:
        """Read only atoms paired with a succeeded current semantic job."""
        current_manifest = self.get_compilable_source_manifest(course_id)
        if current_manifest is None or current_manifest[0] != source_revision:
            return []
        rows = self._conn.execute(
            """
            SELECT atom.* FROM semantic_atoms AS atom
            INNER JOIN semantic_atom_compilations AS compilation
                ON compilation.course_id = atom.course_id
               AND compilation.knowledge_revision = atom.knowledge_revision
            INNER JOIN knowledge_jobs AS job
                ON job.job_id = compilation.job_id AND job.status = 'succeeded'
            WHERE atom.course_id = ? AND atom.source_revision = ?
            ORDER BY atom.section_id, atom.atom_id
            """,
            (course_id, source_revision),
        ).fetchall()
        return [self._row_to_semantic_atom(row) for row in rows]

    def get_current_semantic_atom_compilation(
        self, course_id: str, source_revision: str
    ) -> SemanticAtomCompilation | None:
        row = self._conn.execute(
            """
            SELECT compilation.* FROM semantic_atom_compilations AS compilation
            INNER JOIN knowledge_jobs AS job
                ON job.job_id = compilation.job_id
               AND job.course_id = compilation.course_id
               AND job.status = 'succeeded'
               AND job.target_source_revision = compilation.source_revision
               AND job.target_knowledge_revision = compilation.knowledge_revision
            WHERE compilation.course_id = ? AND compilation.source_revision = ?
            """,
            (course_id, source_revision),
        ).fetchone()
        return self._row_to_semantic_atom_compilation(row) if row is not None else None

    def get_semantic_atom_job_for_source(
        self, course_id: str, source_revision: str
    ) -> KnowledgeJob | None:
        row = self._conn.execute(
            """
            SELECT * FROM knowledge_jobs
            WHERE course_id = ? AND material_id IS NULL
              AND job_type = 'extract_semantic_atoms' AND target_source_revision = ?
            ORDER BY created_at DESC, job_id DESC LIMIT 1
            """,
            (course_id, source_revision),
        ).fetchone()
        return self._row_to_knowledge_job(row) if row is not None else None

    def get_latest_semantic_atom_compilation(
        self, course_id: str
    ) -> SemanticAtomCompilation | None:
        row = self._conn.execute(
            """
            SELECT * FROM semantic_atom_compilations
            WHERE course_id = ? ORDER BY created_at DESC, knowledge_revision DESC LIMIT 1
            """,
            (course_id,),
        ).fetchone()
        return self._row_to_semantic_atom_compilation(row) if row is not None else None

    def publish_terms_if_current(
        self,
        *,
        course_id: str,
        job_id: str,
        job_attempt: int,
        lease_owner: str,
        source_revision: str,
        knowledge_revision: str,
        terms: list[Term],
        rejected_atom_count: int,
    ) -> bool:
        """Atomically publish a full rule-derived term projection for current Atoms."""
        if job_attempt < 1 or not lease_owner.strip() or rejected_atom_count < 0:
            raise ValueError("Term publication requires a claimed lease and valid counts")
        if any(
            term.course_id != course_id
            or term.source_revision != source_revision
            or term.knowledge_revision != knowledge_revision
            for term in terms
        ):
            raise ValueError("Term identity does not match its publication target")
        with self._knowledge_job_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                job = self._conn.execute(
                    """
                    SELECT status, attempt, lease_owner, lease_expires_at,
                           target_source_revision, target_knowledge_revision
                    FROM knowledge_jobs
                    WHERE job_id = ? AND course_id = ? AND job_type = 'compile_terms'
                    """,
                    (job_id, course_id),
                ).fetchone()
                if (
                    job is None
                    or job["status"] != "running"
                    or job["attempt"] != job_attempt
                    or job["lease_owner"] != lease_owner
                    or job["lease_expires_at"] is None
                    or job["lease_expires_at"] <= self._conn.execute("SELECT datetime('now')").fetchone()[0]
                    or job["target_source_revision"] != source_revision
                    or job["target_knowledge_revision"] != knowledge_revision
                ):
                    self._conn.rollback()
                    return False
                current_manifest = self.get_compilable_source_manifest(course_id)
                if current_manifest is None or current_manifest[0] != source_revision:
                    self._conn.rollback()
                    return False
                semantic_header = self._conn.execute(
                    """
                    SELECT compilation.job_id FROM semantic_atom_compilations AS compilation
                    INNER JOIN knowledge_jobs AS semantic_job
                        ON semantic_job.job_id = compilation.job_id
                       AND semantic_job.course_id = compilation.course_id
                       AND semantic_job.job_type = 'extract_semantic_atoms'
                       AND semantic_job.status = 'succeeded'
                       AND semantic_job.target_source_revision = compilation.source_revision
                       AND semantic_job.target_knowledge_revision = compilation.knowledge_revision
                    WHERE compilation.course_id = ? AND compilation.source_revision = ?
                      AND compilation.knowledge_revision = ?
                    """,
                    (course_id, source_revision, knowledge_revision),
                ).fetchone()
                if semantic_header is None:
                    self._conn.rollback()
                    return False
                self._validate_terms_for_publication(
                    course_id=course_id,
                    source_revision=source_revision,
                    knowledge_revision=knowledge_revision,
                    terms=terms,
                )
                self._conn.execute(
                    """
                    INSERT INTO term_compilations (
                        course_id, source_revision, knowledge_revision, compiler_version, job_id,
                        term_count, rejected_atom_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(course_id, source_revision, compiler_version) DO NOTHING
                    """,
                    (
                        course_id,
                        source_revision,
                        knowledge_revision,
                        TERM_COMPILER_VERSION,
                        job_id,
                        len(terms),
                        rejected_atom_count,
                    ),
                )
                header = self._conn.execute(
                    """
                    SELECT knowledge_revision, job_id, term_count, rejected_atom_count
                    FROM term_compilations
                    WHERE course_id = ? AND source_revision = ? AND compiler_version = ?
                    """,
                    (course_id, source_revision, TERM_COMPILER_VERSION),
                ).fetchone()
                if (
                    header is None
                    or header["knowledge_revision"] != knowledge_revision
                    or header["job_id"] != job_id
                    or int(header["term_count"]) != len(terms)
                    or int(header["rejected_atom_count"]) != rejected_atom_count
                ):
                    raise RuntimeError("Term target is already bound to another projection")
                for term in terms:
                    self._conn.execute(
                        """
                        INSERT INTO terms (
                            term_id, course_id, source_revision, knowledge_revision, canonical_name,
                            canonical_key, term_kind, definition, definition_atom_id, evidence_json,
                            generation_method
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(term_id) DO NOTHING
                        """,
                        (
                            term.term_id,
                            term.course_id,
                            term.source_revision,
                            term.knowledge_revision,
                            term.canonical_name,
                            term.canonical_key,
                            term.term_kind,
                            term.definition,
                            term.definition_atom_id,
                            json.dumps(
                                [evidence.model_dump() for evidence in term.evidence],
                                ensure_ascii=False,
                                separators=(",", ":"),
                                sort_keys=True,
                            ),
                            term.generation_method,
                        ),
                    )
                    for atom_id in term.supporting_atom_ids:
                        self._conn.execute(
                            """
                            INSERT INTO term_atom_links (
                                term_id, atom_id, course_id, source_revision, knowledge_revision
                            ) VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(term_id, atom_id) DO NOTHING
                            """,
                            (term.term_id, atom_id, course_id, source_revision, knowledge_revision),
                        )
                self._enqueue_kc_job_if_absent(
                    course_id=course_id,
                    source_revision=source_revision,
                    knowledge_revision=knowledge_revision,
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return True

    def _enqueue_kc_job_if_absent(
        self,
        *,
        course_id: str,
        source_revision: str,
        knowledge_revision: str,
    ) -> None:
        """Create the zero-model KC child in its Term publication transaction."""
        existing = self._conn.execute(
            """
            SELECT job_id FROM knowledge_jobs
            WHERE course_id = ? AND job_type = 'compile_kcs'
              AND target_source_revision = ?
            """,
            (course_id, source_revision),
        ).fetchone()
        if existing is not None:
            return
        next_revision = self._conn.execute(
            """
            SELECT COALESCE(MAX(revision), -1) + 1 AS next_revision
            FROM knowledge_jobs
            WHERE course_id = ? AND material_id IS NULL AND job_type = 'compile_kcs'
            """,
            (course_id,),
        ).fetchone()
        if next_revision is None:
            raise RuntimeError("Could not allocate KC compilation job revision")
        self._conn.execute(
            """
            INSERT INTO knowledge_jobs (
                job_id, course_id, material_id, job_type, revision, scope, status,
                attempt, max_attempts, idempotency_key, token_budget,
                target_source_revision, target_knowledge_revision
            ) VALUES (?, ?, NULL, 'compile_kcs', ?, 'course', 'queued', 0, 3, ?, NULL, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                course_id,
                int(next_revision["next_revision"]),
                f"knowledge:compile_kcs:{course_id}:source:{source_revision}",
                source_revision,
                knowledge_revision,
            ),
        )

    def _validate_terms_for_publication(
        self,
        *,
        course_id: str,
        source_revision: str,
        knowledge_revision: str,
        terms: list[Term],
    ) -> None:
        if len({term.term_id for term in terms}) != len(terms):
            raise ValueError("Term projection contains duplicate term IDs")
        fragments = {
            fragment.fragment_id: fragment
            for fragment in self.list_current_ready_source_fragments(course_id)
        }
        rows = self._conn.execute(
            """
            SELECT atom.* FROM semantic_atoms AS atom
            INNER JOIN semantic_atom_compilations AS compilation
                ON compilation.course_id = atom.course_id
               AND compilation.knowledge_revision = atom.knowledge_revision
            INNER JOIN knowledge_jobs AS job
                ON job.job_id = compilation.job_id
               AND job.course_id = compilation.course_id
               AND job.job_type = 'extract_semantic_atoms'
               AND job.status = 'succeeded'
               AND job.target_source_revision = compilation.source_revision
               AND job.target_knowledge_revision = compilation.knowledge_revision
            WHERE atom.course_id = ? AND atom.source_revision = ? AND atom.knowledge_revision = ?
            """,
            (course_id, source_revision, knowledge_revision),
        ).fetchall()
        atoms = {row["atom_id"]: self._row_to_semantic_atom(row) for row in rows}
        for term in terms:
            if term.canonical_key != normalise_term_key(term.canonical_name):
                raise ValueError("Term canonical key is not derived from its literal name")
            expected_term_id = build_term_id(
                course_id=course_id,
                source_revision=source_revision,
                knowledge_revision=knowledge_revision,
                canonical_key=term.canonical_key,
            )
            if term.term_id != expected_term_id:
                raise ValueError("Term ID is not the stable scope-derived identity")
            atom_ids = term.supporting_atom_ids
            if len(set(atom_ids)) != len(atom_ids) or not atom_ids or term.definition_atom_id not in atom_ids:
                raise ValueError("Term Atom links are missing or duplicated")
            supporting_atoms = []
            for atom_id in atom_ids:
                atom = atoms.get(atom_id)
                if atom is None:
                    raise ValueError("Term links an Atom outside the current semantic projection")
                if atom.atom_type not in {"definition", "concept", "formula", "theorem", "procedure"}:
                    raise ValueError("Term links an unsupported Atom type")
                if term.canonical_name not in atom.statement:
                    raise ValueError("Term name is not a literal in its linked Atom statement")
                expected_evidence = []
                for evidence in atom.evidence:
                    fragment = fragments.get(evidence.fragment_id)
                    if fragment is None or term.canonical_name not in fragment.text:
                        raise ValueError("Term name is not a literal in linked current Atom evidence")
                    expected_evidence.append(EvidenceRef.from_source_fragment(fragment))
                if [value.model_dump() for value in atom.evidence] != [
                    value.model_dump() for value in expected_evidence
                ]:
                    raise ValueError("Semantic Atom evidence is not canonical current evidence")
                supporting_atoms.append(atom)
            definition_atom = atoms[term.definition_atom_id]
            if term.definition != definition_atom.statement or term.term_kind != definition_atom.atom_type:
                raise ValueError("Term definition must be copied from its selected Atom")
            expected_evidence_by_id = {
                evidence.fragment_id: evidence
                for atom in supporting_atoms
                for evidence in atom.evidence
            }
            expected_evidence = [
                expected_evidence_by_id[fragment_id]
                for fragment_id in sorted(expected_evidence_by_id)
            ]
            if [value.model_dump() for value in term.evidence] != [
                value.model_dump() for value in expected_evidence
            ]:
                raise ValueError("Term evidence must be the canonical union of its linked Atoms")

    def get_current_terms(self, course_id: str, source_revision: str) -> list[Term]:
        """Read only terms whose compilation and semantic parent both succeeded."""
        current_manifest = self.get_compilable_source_manifest(course_id)
        if current_manifest is None or current_manifest[0] != source_revision:
            return []
        rows = self._conn.execute(
            """
            SELECT term.* FROM terms AS term
            INNER JOIN term_compilations AS compilation
                ON compilation.course_id = term.course_id
               AND compilation.knowledge_revision = term.knowledge_revision
            INNER JOIN knowledge_jobs AS term_job
                ON term_job.job_id = compilation.job_id
               AND term_job.course_id = compilation.course_id
               AND term_job.job_type = 'compile_terms'
               AND term_job.status = 'succeeded'
               AND term_job.target_source_revision = compilation.source_revision
               AND term_job.target_knowledge_revision = compilation.knowledge_revision
            INNER JOIN semantic_atom_compilations AS semantic
                ON semantic.course_id = compilation.course_id
               AND semantic.source_revision = compilation.source_revision
               AND semantic.knowledge_revision = compilation.knowledge_revision
            INNER JOIN knowledge_jobs AS semantic_job
                ON semantic_job.job_id = semantic.job_id
               AND semantic_job.course_id = semantic.course_id
               AND semantic_job.job_type = 'extract_semantic_atoms'
               AND semantic_job.status = 'succeeded'
            WHERE term.course_id = ? AND term.source_revision = ?
            ORDER BY term.canonical_key, term.term_id
            """,
            (course_id, source_revision),
        ).fetchall()
        terms: list[Term] = []
        for row in rows:
            links = self._conn.execute(
                """
                SELECT atom_id FROM term_atom_links
                WHERE term_id = ? AND course_id = ? AND source_revision = ?
                  AND knowledge_revision = ?
                ORDER BY atom_id
                """,
                (row["term_id"], course_id, row["source_revision"], row["knowledge_revision"]),
            ).fetchall()
            terms.append(self._row_to_term(row, [link["atom_id"] for link in links]))
        return terms

    def get_current_term_compilation(
        self, course_id: str, source_revision: str
    ) -> TermCompilation | None:
        row = self._conn.execute(
            """
            SELECT compilation.* FROM term_compilations AS compilation
            INNER JOIN knowledge_jobs AS job
                ON job.job_id = compilation.job_id
               AND job.course_id = compilation.course_id
               AND job.job_type = 'compile_terms'
               AND job.status = 'succeeded'
               AND job.target_source_revision = compilation.source_revision
               AND job.target_knowledge_revision = compilation.knowledge_revision
            INNER JOIN semantic_atom_compilations AS semantic
                ON semantic.course_id = compilation.course_id
               AND semantic.source_revision = compilation.source_revision
               AND semantic.knowledge_revision = compilation.knowledge_revision
            INNER JOIN knowledge_jobs AS semantic_job
                ON semantic_job.job_id = semantic.job_id
               AND semantic_job.course_id = semantic.course_id
               AND semantic_job.job_type = 'extract_semantic_atoms'
               AND semantic_job.status = 'succeeded'
            WHERE compilation.course_id = ? AND compilation.source_revision = ?
            """,
            (course_id, source_revision),
        ).fetchone()
        return self._row_to_term_compilation(row) if row is not None else None

    def publish_knowledge_components_if_current(
        self,
        *,
        course_id: str,
        job_id: str,
        job_attempt: int,
        lease_owner: str,
        source_revision: str,
        knowledge_revision: str,
        components: list[KnowledgeComponent],
        rejected_term_count: int,
        enqueue_relations: bool = False,
        relation_token_budget: int | None = None,
        relation_max_attempts: int = 3,
    ) -> bool:
        """Atomically publish current, one-Term-per-KC learning projections."""
        if job_attempt < 1 or not lease_owner.strip() or rejected_term_count < 0 or relation_max_attempts < 1:
            raise ValueError("KC publication requires a claimed lease and valid counts")
        if enqueue_relations and (relation_token_budget is None or relation_token_budget <= 0):
            raise ValueError("Automatic KC-relation extraction requires a positive token budget")
        if any(
            value.course_id != course_id
            or value.source_revision != source_revision
            or value.knowledge_revision != knowledge_revision
            for value in components
        ):
            raise ValueError("KC identity does not match its publication target")
        with self._knowledge_job_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                job = self._conn.execute(
                    """
                    SELECT status, attempt, lease_owner, lease_expires_at,
                           target_source_revision, target_knowledge_revision
                    FROM knowledge_jobs
                    WHERE job_id = ? AND course_id = ? AND job_type = 'compile_kcs'
                    """,
                    (job_id, course_id),
                ).fetchone()
                if (
                    job is None or job["status"] != "running" or job["attempt"] != job_attempt
                    or job["lease_owner"] != lease_owner or job["lease_expires_at"] is None
                    or job["lease_expires_at"] <= self._conn.execute("SELECT datetime('now')").fetchone()[0]
                    or job["target_source_revision"] != source_revision
                    or job["target_knowledge_revision"] != knowledge_revision
                ):
                    self._conn.rollback()
                    return False
                current_manifest = self.get_compilable_source_manifest(course_id)
                if current_manifest is None or current_manifest[0] != source_revision:
                    self._conn.rollback()
                    return False
                parent = self._conn.execute(
                    """
                    SELECT compilation.job_id FROM term_compilations AS compilation
                    INNER JOIN knowledge_jobs AS term_job
                        ON term_job.job_id = compilation.job_id
                       AND term_job.course_id = compilation.course_id
                       AND term_job.job_type = 'compile_terms'
                       AND term_job.status = 'succeeded'
                       AND term_job.target_source_revision = compilation.source_revision
                       AND term_job.target_knowledge_revision = compilation.knowledge_revision
                    WHERE compilation.course_id = ? AND compilation.source_revision = ?
                      AND compilation.knowledge_revision = ?
                    """,
                    (course_id, source_revision, knowledge_revision),
                ).fetchone()
                if parent is None:
                    self._conn.rollback()
                    return False
                self._validate_knowledge_components_for_publication(
                    course_id=course_id,
                    source_revision=source_revision,
                    knowledge_revision=knowledge_revision,
                    components=components,
                )
                self._conn.execute(
                    """
                    INSERT INTO knowledge_component_compilations (
                        course_id, source_revision, knowledge_revision, compiler_version, job_id,
                        kc_count, rejected_term_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(course_id, source_revision, compiler_version) DO NOTHING
                    """,
                    (course_id, source_revision, knowledge_revision, KC_COMPILER_VERSION, job_id,
                     len(components), rejected_term_count),
                )
                header = self._conn.execute(
                    """
                    SELECT knowledge_revision, job_id, kc_count, rejected_term_count
                    FROM knowledge_component_compilations
                    WHERE course_id = ? AND source_revision = ? AND compiler_version = ?
                    """,
                    (course_id, source_revision, KC_COMPILER_VERSION),
                ).fetchone()
                if (
                    header is None or header["knowledge_revision"] != knowledge_revision
                    or header["job_id"] != job_id or int(header["kc_count"]) != len(components)
                    or int(header["rejected_term_count"]) != rejected_term_count
                ):
                    raise RuntimeError("KC target is already bound to another projection")
                for component in components:
                    self._conn.execute(
                        """
                        INSERT INTO knowledge_components (
                            kc_id, course_id, source_revision, knowledge_revision, term_id, name,
                            kind, definition, section_id, evidence_json, generation_method
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(kc_id) DO NOTHING
                        """,
                        (
                            component.kc_id, component.course_id, component.source_revision,
                            component.knowledge_revision, component.term_id, component.name,
                            component.kind, component.definition, component.section_id,
                            json.dumps([item.model_dump() for item in component.evidence], ensure_ascii=False,
                                       separators=(",", ":"), sort_keys=True),
                            component.generation_method,
                        ),
                    )
                if enqueue_relations:
                    self._enqueue_kc_relation_job_if_absent(
                        course_id=course_id, source_revision=source_revision,
                        knowledge_revision=knowledge_revision,
                        token_budget=relation_token_budget,
                        max_attempts=relation_max_attempts,
                    )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return True

    def _enqueue_kc_relation_job_if_absent(
        self, *, course_id: str, source_revision: str, knowledge_revision: str,
        token_budget: int | None, max_attempts: int,
    ) -> None:
        """Create D3b's paid child inside the successful KC publication transaction."""
        existing = self._conn.execute(
            "SELECT job_id FROM knowledge_jobs WHERE course_id = ? AND job_type = 'extract_kc_relations' AND target_source_revision = ?",
            (course_id, source_revision),
        ).fetchone()
        if existing is not None:
            return
        row = self._conn.execute(
            "SELECT COALESCE(MAX(revision), -1) + 1 AS next_revision FROM knowledge_jobs WHERE course_id = ? AND material_id IS NULL AND job_type = 'extract_kc_relations'",
            (course_id,),
        ).fetchone()
        if row is None or token_budget is None:
            raise RuntimeError("Could not allocate KC relation extraction job")
        self._conn.execute(
            """INSERT INTO knowledge_jobs (job_id, course_id, material_id, job_type, revision, scope, status,
               attempt, max_attempts, idempotency_key, token_budget, target_source_revision, target_knowledge_revision)
               VALUES (?, ?, NULL, 'extract_kc_relations', ?, 'course', 'queued', 0, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), course_id, int(row["next_revision"]), max_attempts,
             f"knowledge:extract_kc_relations:{course_id}:source:{source_revision}", token_budget,
             source_revision, knowledge_revision),
        )

    def _validate_knowledge_components_for_publication(
        self,
        *,
        course_id: str,
        source_revision: str,
        knowledge_revision: str,
        components: list[KnowledgeComponent],
    ) -> None:
        if len({value.kc_id for value in components}) != len(components) or len({value.term_id for value in components}) != len(components):
            raise ValueError("KC projection contains duplicate component or Term IDs")
        terms = {term.term_id: term for term in self.get_current_terms(course_id, source_revision)}
        atoms = {atom.atom_id: atom for atom in self.get_current_semantic_atoms(course_id, source_revision)}
        fragments = {value.fragment_id: value for value in self.list_current_ready_source_fragments(course_id)}
        for component in components:
            expected_id = build_knowledge_component_id(
                course_id=course_id, source_revision=source_revision,
                knowledge_revision=knowledge_revision, term_id=component.term_id,
            )
            if component.kc_id != expected_id:
                raise ValueError("KC ID is not the stable Term-scoped identity")
            term = terms.get(component.term_id)
            if term is None or term.knowledge_revision != knowledge_revision:
                raise ValueError("KC links a Term outside the current projection")
            atom = atoms.get(term.definition_atom_id)
            if atom is None or atom.knowledge_revision != knowledge_revision:
                raise ValueError("KC definition Atom is absent from the current semantic projection")
            if (
                component.name != term.canonical_name or component.kind != term.term_kind
                or component.definition != term.definition or component.definition != atom.statement
                or component.section_id != atom.section_id
            ):
                raise ValueError("KC must reuse its Term and definition Atom fields")
            expected_evidence = []
            for evidence in term.evidence:
                fragment = fragments.get(evidence.fragment_id)
                if fragment is None:
                    raise ValueError("KC Term evidence is not current canonical evidence")
                expected_evidence.append(EvidenceRef.from_source_fragment(fragment))
            if [item.model_dump() for item in component.evidence] != [item.model_dump() for item in expected_evidence]:
                raise ValueError("KC evidence must exactly reuse canonical Term evidence")

    def get_current_knowledge_components(
        self, course_id: str, source_revision: str
    ) -> list[KnowledgeComponent]:
        """Read only KCs whose Term and semantic ancestry are still current."""
        if (manifest := self.get_compilable_source_manifest(course_id)) is None or manifest[0] != source_revision:
            return []
        rows = self._conn.execute(
            """
            SELECT component.* FROM knowledge_components AS component
            INNER JOIN knowledge_component_compilations AS compilation
                ON compilation.course_id = component.course_id
               AND compilation.knowledge_revision = component.knowledge_revision
            INNER JOIN knowledge_jobs AS kc_job
                ON kc_job.job_id = compilation.job_id
               AND kc_job.course_id = compilation.course_id
               AND kc_job.job_type = 'compile_kcs' AND kc_job.status = 'succeeded'
               AND kc_job.target_source_revision = compilation.source_revision
               AND kc_job.target_knowledge_revision = compilation.knowledge_revision
            INNER JOIN term_compilations AS term_compilation
                ON term_compilation.course_id = compilation.course_id
               AND term_compilation.source_revision = compilation.source_revision
               AND term_compilation.knowledge_revision = compilation.knowledge_revision
            INNER JOIN knowledge_jobs AS term_job
                ON term_job.job_id = term_compilation.job_id
               AND term_job.course_id = term_compilation.course_id
               AND term_job.job_type = 'compile_terms' AND term_job.status = 'succeeded'
            WHERE component.course_id = ? AND component.source_revision = ?
            ORDER BY component.name, component.kc_id
            """,
            (course_id, source_revision),
        ).fetchall()
        return [self._row_to_knowledge_component(row) for row in rows]

    def publish_kc_relations_if_current(
        self, *, course_id: str, job_id: str, job_attempt: int, lease_owner: str,
        source_revision: str, knowledge_revision: str, relations: list[KCRelation],
        rejected_candidate_count: int,
    ) -> bool:
        """Atomically publish one audited relation projection only for current KCs."""
        if job_attempt < 1 or not lease_owner.strip() or rejected_candidate_count < 0:
            raise ValueError("KC relation publication requires a claimed lease and valid counts")
        if any(r.course_id != course_id or r.source_revision != source_revision or r.knowledge_revision != knowledge_revision for r in relations):
            raise ValueError("KC relation identity does not match publication target")
        with self._knowledge_job_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                job = self._conn.execute(
                    """SELECT status, attempt, lease_owner, lease_expires_at, target_source_revision, target_knowledge_revision
                       FROM knowledge_jobs WHERE job_id = ? AND course_id = ? AND job_type = 'extract_kc_relations'""",
                    (job_id, course_id),
                ).fetchone()
                now = self._conn.execute("SELECT datetime('now')").fetchone()[0]
                if (job is None or job["status"] != "running" or job["attempt"] != job_attempt
                    or job["lease_owner"] != lease_owner or job["lease_expires_at"] is None
                    or job["lease_expires_at"] <= now or job["target_source_revision"] != source_revision
                    or job["target_knowledge_revision"] != knowledge_revision):
                    self._conn.rollback()
                    return False
                manifest = self.get_compilable_source_manifest(course_id)
                if manifest is None or manifest[0] != source_revision or not self._kc_parent_is_current(
                    course_id, source_revision, knowledge_revision
                ):
                    self._conn.rollback()
                    return False
                self._validate_kc_relations_for_publication(
                    course_id=course_id, job_id=job_id, source_revision=source_revision,
                    knowledge_revision=knowledge_revision, relations=relations,
                )
                self._conn.execute(
                    """INSERT INTO kc_relation_compilations (course_id, source_revision, knowledge_revision,
                       compiler_version, job_id, relation_count, rejected_candidate_count, model_call_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                       ON CONFLICT(course_id, source_revision, compiler_version) DO NOTHING""",
                    (course_id, source_revision, knowledge_revision, KC_RELATION_COMPILER_VERSION,
                     job_id, len(relations), rejected_candidate_count),
                )
                header = self._conn.execute(
                    "SELECT knowledge_revision, job_id, relation_count, rejected_candidate_count FROM kc_relation_compilations WHERE course_id = ? AND source_revision = ? AND compiler_version = ?",
                    (course_id, source_revision, KC_RELATION_COMPILER_VERSION),
                ).fetchone()
                if (header is None or header["knowledge_revision"] != knowledge_revision
                    or header["job_id"] != job_id or int(header["relation_count"]) != len(relations)
                    or int(header["rejected_candidate_count"]) != rejected_candidate_count):
                    raise RuntimeError("KC relation target is already bound to another projection")
                for relation in relations:
                    self._conn.execute(
                        """INSERT INTO kc_relations (relation_id, course_id, source_revision, knowledge_revision,
                           source_kc_id, target_kc_id, relation_type, evidence_json, model_call_id, generation_method)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(relation_id) DO NOTHING""",
                        (relation.relation_id, relation.course_id, relation.source_revision,
                         relation.knowledge_revision, relation.source_kc_id, relation.target_kc_id,
                         relation.relation_type, json.dumps(relation.evidence.model_dump(), ensure_ascii=False,
                         separators=(",", ":"), sort_keys=True), relation.model_call_id, relation.generation_method),
                    )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return True

    def _kc_parent_is_current(self, course_id: str, source_revision: str, knowledge_revision: str) -> bool:
        return self._conn.execute(
            """SELECT 1 FROM knowledge_component_compilations AS compilation
               INNER JOIN knowledge_jobs AS job ON job.job_id = compilation.job_id
                AND job.course_id = compilation.course_id AND job.job_type = 'compile_kcs'
                AND job.status = 'succeeded' AND job.target_source_revision = compilation.source_revision
                AND job.target_knowledge_revision = compilation.knowledge_revision
               WHERE compilation.course_id = ? AND compilation.source_revision = ?
                 AND compilation.knowledge_revision = ?""",
            (course_id, source_revision, knowledge_revision),
        ).fetchone() is not None

    def _validate_kc_relations_for_publication(
        self, *, course_id: str, job_id: str, source_revision: str,
        knowledge_revision: str, relations: list[KCRelation],
    ) -> None:
        if len({relation.relation_id for relation in relations}) != len(relations):
            raise ValueError("KC relation projection contains duplicate relation IDs")
        components = {value.kc_id: value for value in self.get_current_knowledge_components(course_id, source_revision)}
        fragments = {value.fragment_id: value for value in self.list_current_ready_source_fragments(course_id)}
        audits = {
            row["call_id"] for row in self._conn.execute(
                """SELECT call_id FROM model_call_audits WHERE course_id = ? AND job_id = ?
                   AND source_revision = ? AND knowledge_revision = ? AND status = 'succeeded'
                   ORDER BY started_at DESC""",
                (course_id, job_id, source_revision, knowledge_revision),
            ).fetchall()
        }
        if len(audits) == 0:
            raise ValueError("KC relation projection requires at least one succeeded model audit")
        for relation in relations:
            expected_id = build_kc_relation_id(course_id=course_id, source_revision=source_revision,
                knowledge_revision=knowledge_revision, source_kc_id=relation.source_kc_id,
                target_kc_id=relation.target_kc_id, relation_type=relation.relation_type,
                evidence_fragment_id=relation.evidence.fragment_id)
            if relation.relation_id != expected_id or relation.model_call_id not in audits:
                raise ValueError("KC relation has an untrusted identity or model audit")
            source, target = components.get(relation.source_kc_id), components.get(relation.target_kc_id)
            fragment = fragments.get(relation.evidence.fragment_id)
            if source is None or target is None or fragment is None or source.kc_id == target.kc_id:
                raise ValueError("KC relation does not point to current course evidence")
            if source.name not in fragment.text or target.name not in fragment.text:
                raise ValueError("KC relation names must literally co-occur in canonical evidence")
            if relation.evidence.model_dump() != EvidenceRef.from_source_fragment(fragment).model_dump():
                raise ValueError("KC relation evidence must be canonical current evidence")

    def get_current_kc_relations(self, course_id: str, source_revision: str) -> list[KCRelation]:
        if (manifest := self.get_compilable_source_manifest(course_id)) is None or manifest[0] != source_revision:
            return []
        rows = self._conn.execute(
            """SELECT relation.* FROM kc_relations AS relation
               INNER JOIN kc_relation_compilations AS compilation ON compilation.course_id = relation.course_id
                AND compilation.knowledge_revision = relation.knowledge_revision
               INNER JOIN knowledge_jobs AS job ON job.job_id = compilation.job_id AND job.course_id = compilation.course_id
                AND job.job_type = 'extract_kc_relations' AND job.status = 'succeeded'
                AND job.target_source_revision = compilation.source_revision AND job.target_knowledge_revision = compilation.knowledge_revision
               WHERE relation.course_id = ? AND relation.source_revision = ? ORDER BY relation.relation_id""",
            (course_id, source_revision),
        ).fetchall()
        return [self._row_to_kc_relation(row) for row in rows]

    def publish_course_compilation_if_current(
        self,
        *,
        course_id: str,
        job_id: str,
        job_attempt: int,
        lease_owner: str,
        target_source_revision: str,
        target_knowledge_revision: str,
        outline: CourseOutline,
        source_manifest_json: str,
        compiler_version: str,
        enqueue_semantic: bool = False,
        semantic_token_budget: int | None = None,
        semantic_max_attempts: int = 3,
    ) -> bool:
        """Atomically publish an immutable outline only for the current source set."""
        if outline.course_id != course_id:
            raise ValueError("Course outline course_id does not match compilation scope")
        if job_attempt < 1 or not lease_owner.strip():
            raise ValueError("Course compilation publication requires the claimed job attempt and lease owner")
        if semantic_max_attempts < 1:
            raise ValueError("semantic_max_attempts must be positive")
        if outline.source_revision != target_source_revision:
            raise ValueError("Course outline source revision does not match compilation target")
        if outline.knowledge_revision != target_knowledge_revision:
            raise ValueError("Course outline knowledge revision does not match compilation target")
        if outline.compiler_version != compiler_version:
            raise ValueError("Course outline compiler version does not match compilation target")

        with self._knowledge_job_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                job = self._conn.execute(
                    """
                    SELECT status, attempt, lease_owner, lease_expires_at,
                           target_source_revision, target_knowledge_revision
                    FROM knowledge_jobs
                    WHERE job_id = ? AND course_id = ? AND job_type = 'compile_course'
                    """,
                    (job_id, course_id),
                ).fetchone()
                if (
                    job is None
                    or job["status"] != "running"
                    or job["attempt"] != job_attempt
                    or job["lease_owner"] != lease_owner
                    or job["lease_expires_at"] is None
                    or job["lease_expires_at"] <= self._conn.execute("SELECT datetime('now')").fetchone()[0]
                    or job["target_source_revision"] != target_source_revision
                    or job["target_knowledge_revision"] != target_knowledge_revision
                ):
                    self._conn.rollback()
                    return False
                current_manifest = self.get_compilable_source_manifest(course_id)
                if current_manifest != (target_source_revision, source_manifest_json):
                    self._conn.rollback()
                    return False

                self._conn.execute(
                    """
                    INSERT INTO course_compilations (
                        course_id, source_revision, knowledge_revision, compiler_version, job_id,
                        source_manifest_json, source_fragment_count, outline_section_count, warning_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(course_id, source_revision, compiler_version) DO NOTHING
                    """,
                    (
                        course_id,
                        target_source_revision,
                        target_knowledge_revision,
                        compiler_version,
                        job_id,
                        source_manifest_json,
                        outline.fragment_count,
                        len(outline.sections),
                    ),
                )
                header = self._conn.execute(
                    """
                    SELECT knowledge_revision, job_id FROM course_compilations
                    WHERE course_id = ? AND source_revision = ? AND compiler_version = ?
                    """,
                    (course_id, target_source_revision, compiler_version),
                ).fetchone()
                if (
                    header is None
                    or header["knowledge_revision"] != target_knowledge_revision
                    or header["job_id"] != job_id
                ):
                    raise RuntimeError("Course compilation target is already bound to another snapshot")
                self._conn.execute(
                    """
                    INSERT INTO course_projection_snapshots (
                        course_id, knowledge_revision, projection_kind, payload_json
                    ) VALUES (?, ?, 'course_outline', ?)
                    ON CONFLICT(course_id, knowledge_revision, projection_kind) DO NOTHING
                    """,
                    (course_id, target_knowledge_revision, outline.model_dump_json()),
                )
                if enqueue_semantic:
                    existing_semantic = self._conn.execute(
                        """
                        SELECT job_id FROM knowledge_jobs
                        WHERE course_id = ? AND job_type = 'extract_semantic_atoms'
                          AND target_source_revision = ?
                        """,
                        (course_id, target_source_revision),
                    ).fetchone()
                    if existing_semantic is None:
                        next_revision = self._conn.execute(
                            """
                            SELECT COALESCE(MAX(revision), -1) + 1 AS next_revision
                            FROM knowledge_jobs
                            WHERE course_id = ? AND material_id IS NULL
                              AND job_type = 'extract_semantic_atoms'
                            """,
                            (course_id,),
                        ).fetchone()
                        if next_revision is None:
                            raise RuntimeError("Could not allocate semantic extraction job revision")
                        self._conn.execute(
                            """
                            INSERT INTO knowledge_jobs (
                                job_id, course_id, material_id, job_type, revision, scope, status,
                                attempt, max_attempts, idempotency_key, token_budget,
                                target_source_revision, target_knowledge_revision
                            ) VALUES (?, ?, NULL, 'extract_semantic_atoms', ?, 'course', 'queued',
                                      0, ?, ?, ?, ?, ?)
                            """,
                            (
                                str(uuid.uuid4()),
                                course_id,
                                int(next_revision["next_revision"]),
                                semantic_max_attempts,
                                f"knowledge:extract_semantic_atoms:{course_id}:source:{target_source_revision}",
                                semantic_token_budget,
                                target_source_revision,
                                target_knowledge_revision,
                            ),
                        )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return True

    def update_material(self, course_id: str, material_id: str, material: Material) -> Material | None:
        existing = self.get_material(course_id, material_id)
        if existing is None:
            return None
        if material.revision != existing.revision or material.content_hash != existing.content_hash:
            raise ValueError(
                "Material revision and content_hash are immutable in update_material; "
                "use advance_material_revision for new source content"
            )
        self._conn.execute(
            "UPDATE materials SET filename=?, kind=?, status=?, degraded=? WHERE id=? AND course_id=?",
            (
                material.filename,
                material.kind,
                material.status,
                int(material.degraded),
                material_id,
                course_id,
            ),
        )
        self._conn.commit()
        return self.get_material(course_id, material_id)

    def update_material_status(self, course_id: str, material_id: str, status: str, degraded: bool = False) -> None:
        self._conn.execute(
            "UPDATE materials SET status=?, degraded=? WHERE id=? AND course_id=?",
            (status, int(degraded), material_id, course_id),
        )
        self._conn.commit()

    def update_material_status_if_revision(
        self,
        course_id: str,
        material_id: str,
        revision: int,
        status: str,
        degraded: bool = False,
    ) -> bool:
        """Update status only when a worker still owns the current revision."""
        self._validate_material_revision(revision)
        cursor = self._conn.execute(
            """
            UPDATE materials
            SET status = ?, degraded = ?
            WHERE id = ? AND course_id = ? AND revision = ?
            """,
            (status, int(degraded), material_id, course_id, revision),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def is_material_degraded(self, course_id: str, material_id: str) -> bool:
        row = self._conn.execute(
            "SELECT degraded FROM materials WHERE id=? AND course_id=?", (material_id, course_id)
        ).fetchone()
        return bool(row["degraded"]) if row else False

    def get_material_file_path(self, course_id: str, material_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT file_path FROM materials WHERE id=? AND course_id=?", (material_id, course_id)
        ).fetchone()
        return row["file_path"] if row else None

    def save_parsed_text(self, course_id: str, material_id: str, text: str) -> None:
        """持久化材料解析文本,替代 pipeline.py 的进程内 dict 缓存。

        解决进程重启导致 course-level wiki/skeleton 永不生成的隐患。
        """
        self._conn.execute(
            "UPDATE materials SET parsed_text = ? WHERE id = ? AND course_id = ?",
            (text, material_id, course_id),
        )
        self._conn.commit()

    def save_parsed_text_if_revision(
        self,
        course_id: str,
        material_id: str,
        revision: int,
        text: str,
    ) -> bool:
        """Persist parsed text only if ``revision`` is still current.

        ``False`` is a normal stale-job signal: no row was changed, so an old
        worker cannot overwrite a newer material input.
        """
        self._validate_material_revision(revision)
        cursor = self._conn.execute(
            """
            UPDATE materials
            SET parsed_text = ?
            WHERE id = ? AND course_id = ? AND revision = ?
            """,
            (text, material_id, course_id, revision),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def get_parsed_text(self, course_id: str, material_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT parsed_text FROM materials WHERE id = ? AND course_id = ?",
            (material_id, course_id),
        ).fetchone()
        return row["parsed_text"] if row else None

    def get_all_parsed_texts(self, course_id: str) -> dict[str, str]:
        """返回 {material_id: parsed_text},供 course-level wiki build 使用。"""
        rows = self._conn.execute(
            "SELECT id, parsed_text FROM materials WHERE course_id = ? AND parsed_text IS NOT NULL",
            (course_id,),
        ).fetchall()
        return {r["id"]: r["parsed_text"] for r in rows if r["parsed_text"]}

    def advance_material_revision(
        self,
        course_id: str,
        material_id: str,
        content_hash: str,
        *,
        status: str = "processing",
    ) -> Material | None:
        """Record replacement source content and invalidate material-local output.

        This is the only material-store method that changes the current hash
        or revision. It clears parsed text and resets degraded state before
        newer jobs begin, so older revision-guarded writes are rejected.
        """
        if not content_hash:
            raise ValueError("content_hash must be non-empty when advancing a material revision")
        with self._material_index_publish_lock:
            cursor = self._conn.execute(
                """
                UPDATE materials
                SET revision = revision + 1,
                    content_hash = ?,
                    parsed_text = NULL,
                    status = ?,
                    degraded = 0
                WHERE id = ? AND course_id = ?
                """,
                (content_hash, status, material_id, course_id),
            )
            if cursor.rowcount == 1:
                # Assets have no historical revision column in the MVP.  Once
                # the material source changes, their parser-derived metadata
                # must disappear with the old parsed text rather than be
                # accidentally reused by the next revision.
                self._conn.execute(
                    "DELETE FROM extracted_assets WHERE course_id = ? AND material_id = ?",
                    (course_id, material_id),
                )
            self._conn.commit()
        if cursor.rowcount != 1:
            return None
        return self.get_material(course_id, material_id)

    @staticmethod
    def _validate_material_revision(revision: int) -> None:
        if revision < 0:
            raise ValueError("material revision must be non-negative")

    @staticmethod
    def _material_from_row(row: sqlite3.Row) -> Material:
        """Build a Material while preserving migration-safe legacy defaults."""
        keys = row.keys()
        return Material(
            id=row["id"],
            course_id=row["course_id"],
            filename=row["filename"],
            kind=row["kind"],
            status=row["status"],
            degraded=bool(row["degraded"]) if "degraded" in keys else False,
            revision=row["revision"] if "revision" in keys else 0,
            content_hash=row["content_hash"] if "content_hash" in keys else "",
        )

    # --- Source fragments (V2 evidence fact layer) ---

    def publish_material_index_if_current(
        self,
        course_id: str,
        material_id: str,
        material_revision: int,
        fragments: Sequence[SourceFragment],
        publish_vectors: Callable[[], None],
        publish_assets: Callable[[], None] | None = None,
    ) -> bool:
        """Publish one material's evidence only while its revision is current.

        The asset and vector callbacks perform their respective replacement
        writes in the same material-level critical section as
        ``advance_material_revision``:
        SQLite cannot atomically commit alongside Qdrant, but the documented
        single-process SQLite MVP can still give replacement and publication a
        single order.  A replacement that wins before this fence makes the
        method return ``False`` without touching fragments or vectors; a
        replacement that arrives while publishing waits until this revision has
        finished, then advances and invalidates it.
        """
        self._assert_source_fragment_scope(course_id, material_id, material_revision)
        with self._material_index_publish_lock:
            material = self.get_material(course_id, material_id)
            if material is None or material.revision != material_revision:
                return False

            if publish_assets is not None:
                publish_assets()

            self.replace_source_fragments(
                course_id,
                material_id,
                material_revision,
                fragments,
            )
            publish_vectors()
            return self.update_material_status_if_revision(
                course_id,
                material_id,
                material_revision,
                "ready",
            )

    def replace_source_fragments(
        self,
        course_id: str,
        material_id: str,
        material_revision: int,
        fragments: Sequence[SourceFragment],
    ) -> list[SourceFragment]:
        """Atomically replace one material revision's evidence fragments.

        The caller must provide the full fragment set for exactly one explicit
        course/material/revision scope.  Repeating the same replacement is
        idempotent: stable fragment IDs are updated in place and stale rows in
        that exact revision are removed.  A fragment can never be used to
        write another course's material scope.
        """
        self._assert_source_fragment_scope(course_id, material_id, material_revision)
        fragment_list = list(fragments)
        self._validate_source_fragment_replacement(
            course_id,
            material_id,
            material_revision,
            fragment_list,
        )

        with self._source_fragment_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                fragment_ids = [fragment.fragment_id for fragment in fragment_list]
                if fragment_ids:
                    placeholders = ", ".join("?" for _ in fragment_ids)
                    self._conn.execute(
                        f"""
                        DELETE FROM source_fragments
                        WHERE course_id = ? AND material_id = ? AND material_revision = ?
                          AND fragment_id NOT IN ({placeholders})
                        """,
                        (course_id, material_id, material_revision, *fragment_ids),
                    )
                else:
                    self._conn.execute(
                        """
                        DELETE FROM source_fragments
                        WHERE course_id = ? AND material_id = ? AND material_revision = ?
                        """,
                        (course_id, material_id, material_revision),
                    )

                for fragment in fragment_list:
                    written = self._conn.execute(
                        """
                        INSERT INTO source_fragments (
                            fragment_id, course_id, material_id, material_revision, ordinal,
                            text, heading_path_json, page_start, page_end, slide_start,
                            slide_end, char_start, char_end, kind, asset_id, parser_name,
                            content_hash, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(fragment_id) DO UPDATE SET
                            ordinal = excluded.ordinal,
                            text = excluded.text,
                            heading_path_json = excluded.heading_path_json,
                            page_start = excluded.page_start,
                            page_end = excluded.page_end,
                            slide_start = excluded.slide_start,
                            slide_end = excluded.slide_end,
                            char_start = excluded.char_start,
                            char_end = excluded.char_end,
                            kind = excluded.kind,
                            asset_id = excluded.asset_id,
                            parser_name = excluded.parser_name,
                            content_hash = excluded.content_hash
                        WHERE source_fragments.course_id = excluded.course_id
                          AND source_fragments.material_id = excluded.material_id
                          AND source_fragments.material_revision = excluded.material_revision
                        """,
                        self._source_fragment_values(fragment),
                    )
                    if written.rowcount != 1:
                        raise ValueError(
                            "Source fragment ID is already bound to another source scope"
                        )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

        return self.list_source_fragments(
            course_id,
            material_id=material_id,
            material_revision=material_revision,
        )

    def get_source_fragment(
        self,
        course_id: str,
        fragment_id: str,
        *,
        material_id: str | None = None,
        material_revision: int | None = None,
    ) -> SourceFragment | None:
        """Load one fragment only when it belongs to the requested course."""
        where, params = self._source_fragment_scope_query(
            course_id,
            material_id=material_id,
            material_revision=material_revision,
        )
        row = self._conn.execute(
            f"SELECT * FROM source_fragments WHERE fragment_id = ? AND {where}",
            (fragment_id, *params),
        ).fetchone()
        return self._row_to_source_fragment(row) if row is not None else None

    def list_source_fragments(
        self,
        course_id: str,
        *,
        material_id: str | None = None,
        material_revision: int | None = None,
    ) -> list[SourceFragment]:
        """List fragments in source order, always constrained by ``course_id``."""
        where, params = self._source_fragment_scope_query(
            course_id,
            material_id=material_id,
            material_revision=material_revision,
        )
        rows = self._conn.execute(
            f"""
            SELECT * FROM source_fragments
            WHERE {where}
            ORDER BY material_id, material_revision, ordinal, fragment_id
            """,
            params,
        ).fetchall()
        return [self._row_to_source_fragment(row) for row in rows]

    def get_current_ready_source_fragment_preview(
        self,
        course_id: str,
        fragment_id: str,
    ) -> tuple[SourceFragment, str] | None:
        """Load one previewable fragment and its display filename in one join.

        A V2 citation may only open evidence that belongs to the requested
        course, still matches its material's current revision, and whose
        material index is ready.  Old revision rows remain available for
        future audited-history APIs, but never leak through this current
        evidence boundary.
        """
        if not course_id.strip():
            raise ValueError("course_id is required for source fragment queries")
        if not fragment_id.strip():
            raise ValueError("fragment_id is required for source fragment queries")
        row = self._conn.execute(
            """
            SELECT sf.*, m.filename AS material_filename
            FROM source_fragments AS sf
            INNER JOIN materials AS m
                ON m.id = sf.material_id
               AND m.course_id = sf.course_id
               AND m.revision = sf.material_revision
            INNER JOIN knowledge_jobs AS job
                ON job.course_id = sf.course_id
               AND job.material_id = sf.material_id
               AND job.revision = sf.material_revision
               AND job.job_type = 'index_material'
               AND job.status = 'succeeded'
            WHERE sf.course_id = ?
              AND sf.fragment_id = ?
              AND m.status = 'ready'
              AND m.content_hash <> ''
            """,
            (course_id, fragment_id),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_source_fragment(row), row["material_filename"]

    def list_current_ready_source_fragments(
        self,
        course_id: str,
        *,
        fragment_ids: Sequence[str] | None = None,
        material_ids: Sequence[str] | None = None,
    ) -> list[SourceFragment]:
        """Return only current, ready evidence for future V2 retrieval.

        This is the canonical store boundary for fragment-first retrieval.
        It intentionally excludes historical revisions and fragments from
        failed/processing materials even if they are still physically stored.
        Optional IDs are explicit filters, not values parsed from display
        locators or filenames.
        """
        if not course_id.strip():
            raise ValueError("course_id is required for source fragment queries")
        clauses = ["sf.course_id = ?", "m.status = 'ready'", "m.content_hash <> ''"]
        params: list[Any] = [course_id]

        if fragment_ids is not None:
            resolved_fragment_ids = list(dict.fromkeys(fragment_ids))
            if not resolved_fragment_ids:
                return []
            if any(not fragment_id.strip() for fragment_id in resolved_fragment_ids):
                raise ValueError("fragment_ids must not contain blank values")
            placeholders = ", ".join("?" for _ in resolved_fragment_ids)
            clauses.append(f"sf.fragment_id IN ({placeholders})")
            params.extend(resolved_fragment_ids)

        if material_ids is not None:
            resolved_material_ids = list(dict.fromkeys(material_ids))
            if not resolved_material_ids:
                return []
            if any(not material_id.strip() for material_id in resolved_material_ids):
                raise ValueError("material_ids must not contain blank values")
            placeholders = ", ".join("?" for _ in resolved_material_ids)
            clauses.append(f"sf.material_id IN ({placeholders})")
            params.extend(resolved_material_ids)

        where = " AND ".join(clauses)
        rows = self._conn.execute(
            f"""
            SELECT sf.*
            FROM source_fragments AS sf
            INNER JOIN materials AS m
                ON m.id = sf.material_id
               AND m.course_id = sf.course_id
               AND m.revision = sf.material_revision
            INNER JOIN knowledge_jobs AS job
                ON job.course_id = sf.course_id
               AND job.material_id = sf.material_id
               AND job.revision = sf.material_revision
               AND job.job_type = 'index_material'
               AND job.status = 'succeeded'
            WHERE {where}
            ORDER BY sf.material_id, sf.ordinal, sf.fragment_id
            """,
            params,
        ).fetchall()
        return [self._row_to_source_fragment(row) for row in rows]

    def _assert_source_fragment_scope(
        self, course_id: str, material_id: str, material_revision: int
    ) -> None:
        if not course_id.strip():
            raise ValueError("course_id is required for source fragments")
        if not material_id.strip():
            raise ValueError("material_id is required for source fragments")
        if material_revision < 0:
            raise ValueError("material_revision must be non-negative")
        if self.get_course(course_id) is None:
            raise ValueError(f"Cannot write source fragments: course {course_id!r} not found")
        if self.get_material(course_id, material_id) is None:
            raise ValueError("Cannot write source fragments: material does not belong to course")

    @staticmethod
    def _validate_source_fragment_replacement(
        course_id: str,
        material_id: str,
        material_revision: int,
        fragments: Sequence[SourceFragment],
    ) -> None:
        fragment_ids: set[str] = set()
        ordinals: set[int] = set()
        for fragment in fragments:
            identity = (
                fragment.course_id,
                fragment.material_id,
                fragment.material_revision,
            )
            expected = (course_id, material_id, material_revision)
            if identity != expected:
                raise ValueError(
                    "All source fragments must match the requested course/material/revision"
                )
            if fragment.fragment_id in fragment_ids:
                raise ValueError("Source fragment replacement contains duplicate fragment_id")
            if fragment.ordinal in ordinals:
                raise ValueError("Source fragment replacement contains duplicate ordinal")
            fragment_ids.add(fragment.fragment_id)
            ordinals.add(fragment.ordinal)

    @staticmethod
    def _source_fragment_values(fragment: SourceFragment) -> tuple[Any, ...]:
        return (
            fragment.fragment_id,
            fragment.course_id,
            fragment.material_id,
            fragment.material_revision,
            fragment.ordinal,
            fragment.text,
            json.dumps(fragment.heading_path, ensure_ascii=False, separators=(",", ":")),
            fragment.page_start,
            fragment.page_end,
            fragment.slide_start,
            fragment.slide_end,
            fragment.char_start,
            fragment.char_end,
            fragment.kind,
            fragment.asset_id,
            fragment.parser_name,
            fragment.content_hash,
            fragment.created_at,
        )

    @staticmethod
    def _source_fragment_scope_query(
        course_id: str,
        *,
        material_id: str | None,
        material_revision: int | None,
    ) -> tuple[str, tuple[Any, ...]]:
        if not course_id.strip():
            raise ValueError("course_id is required for source fragment queries")
        if material_id is not None and not material_id.strip():
            raise ValueError("material_id must not be blank when provided")
        if material_revision is not None and material_revision < 0:
            raise ValueError("material_revision must be non-negative")

        clauses = ["course_id = ?"]
        params: list[Any] = [course_id]
        if material_id is not None:
            clauses.append("material_id = ?")
            params.append(material_id)
        if material_revision is not None:
            clauses.append("material_revision = ?")
            params.append(material_revision)
        return " AND ".join(clauses), tuple(params)

    @staticmethod
    def _row_to_source_fragment(row: sqlite3.Row) -> SourceFragment:
        return SourceFragment(
            fragment_id=row["fragment_id"],
            course_id=row["course_id"],
            material_id=row["material_id"],
            material_revision=row["material_revision"],
            ordinal=row["ordinal"],
            text=row["text"],
            heading_path=json.loads(row["heading_path_json"]),
            page_start=row["page_start"],
            page_end=row["page_end"],
            slide_start=row["slide_start"],
            slide_end=row["slide_end"],
            char_start=row["char_start"],
            char_end=row["char_end"],
            kind=row["kind"],
            asset_id=row["asset_id"],
            parser_name=row["parser_name"],
            content_hash=row["content_hash"],
            created_at=row["created_at"],
        )

    # --- Skeletons ---

    def create_skeleton(self, skeleton: CourseSkeleton) -> CourseSkeleton:
        data_json = skeleton.model_dump_json()
        self._conn.execute(
            "INSERT OR REPLACE INTO skeletons (course_id, data_json) VALUES (?, ?)",
            (skeleton.course_id, data_json),
        )
        self._conn.commit()
        return skeleton

    def get_skeleton(self, course_id: str) -> CourseSkeleton | None:
        row = self._conn.execute("SELECT * FROM skeletons WHERE course_id = ?", (course_id,)).fetchone()
        if row is None:
            return None
        return CourseSkeleton.model_validate_json(row["data_json"])

    # --- Review Plans ---

    def create_review_plan(self, plan: ReviewPlan) -> ReviewPlan:
        data_json = plan.model_dump_json()
        self._conn.execute(
            "INSERT OR REPLACE INTO review_plans (course_id, data_json) VALUES (?, ?)",
            (plan.course_id, data_json),
        )
        self._conn.commit()
        return plan

    def get_review_plan(self, course_id: str) -> ReviewPlan | None:
        row = self._conn.execute("SELECT * FROM review_plans WHERE course_id = ?", (course_id,)).fetchone()
        if row is None:
            return None
        return ReviewPlan.model_validate_json(row["data_json"])

    # --- Tasks (pipeline progress tracking) ---

    def create_task(self, task_id: str, course_id: str, material_id: str, step: str, status: str = "pending", detail: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO tasks (id, course_id, material_id, step, status, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, course_id, material_id, step, status, detail),
        )
        self._conn.commit()

    def update_task(self, task_id: str, status: str, detail: str | None = None) -> None:
        if detail is not None:
            self._conn.execute(
                "UPDATE tasks SET status=?, detail=?, updated_at=datetime('now') WHERE id=?",
                (status, detail, task_id),
            )
        else:
            self._conn.execute(
                "UPDATE tasks SET status=?, updated_at=datetime('now') WHERE id=?",
                (status, task_id),
            )
        self._conn.commit()

    def get_tasks_for_material(self, course_id: str, material_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE course_id=? AND material_id=? ORDER BY created_at",
            (course_id, material_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_tasks_for_material(self, course_id: str, material_id: str) -> None:
        self._conn.execute(
            "DELETE FROM tasks WHERE course_id=? AND material_id=?",
            (course_id, material_id),
        )
        self._conn.commit()

    # --- Knowledge jobs (V2 persistent queue; no worker loop here) ---

    def enqueue_visual_analysis_job(
        self,
        *,
        course_id: str,
        asset_requests: Sequence[dict[str, str]],
        token_budget: int,
        max_attempts: int = 3,
    ) -> KnowledgeJob:
        """Persist one explicit, current-asset V2-E visual-analysis job.

        This is intentionally not called by material indexing. The caller must
        name each parser asset and why text extraction is insufficient; stale,
        cross-course, or non-current assets are rejected before a queue row is
        created.
        """
        if not course_id.strip() or token_budget <= 0 or max_attempts <= 0:
            raise ValueError("course_id, token_budget, and max_attempts are required")
        if not asset_requests:
            raise ValueError("visual analysis requires at least one explicit asset")
        allowed_reasons = {"missing_alt_text", "unreadable_formula", "unreadable_diagram"}
        normalized: dict[str, str] = {}
        for item in asset_requests:
            asset_id = str(item.get("asset_id", "")).strip()
            reason_code = str(item.get("reason_code", "")).strip()
            if not asset_id or reason_code not in allowed_reasons:
                raise ValueError("Each visual asset needs an asset_id and supported reason_code")
            if asset_id in normalized and normalized[asset_id] != reason_code:
                raise ValueError("An asset cannot carry conflicting visual-analysis reasons")
            normalized[asset_id] = reason_code

        manifest = self.get_compilable_source_manifest(course_id)
        if manifest is None:
            raise ValueError("Visual analysis requires a current, indexed course source")
        source_revision = manifest[0]
        asset_ids = sorted(normalized)
        placeholders = ", ".join("?" for _ in asset_ids)
        rows = self._conn.execute(
            f"""
            SELECT asset.asset_id, asset.material_id, asset.storage_path
            FROM extracted_assets AS asset
            INNER JOIN materials AS material
                ON material.id = asset.material_id AND material.course_id = asset.course_id
            INNER JOIN knowledge_jobs AS index_job
                ON index_job.course_id = material.course_id
               AND index_job.material_id = material.id
               AND index_job.revision = material.revision
               AND index_job.job_type = 'index_material' AND index_job.status = 'succeeded'
            WHERE asset.course_id = ? AND asset.asset_id IN ({placeholders})
              AND material.status = 'ready' AND material.content_hash <> ''
            """,
            [course_id, *asset_ids],
        ).fetchall()
        by_asset = {row["asset_id"]: row for row in rows}
        if set(by_asset) != set(asset_ids) or any(not str(row["storage_path"]).strip() for row in rows):
            raise ValueError("Visual analysis assets must be current, course-owned parsed assets with a storage path")

        knowledge_revision = build_knowledge_revision(
            source_revision=source_revision, compiler_version="visual-analysis-e1"
        )
        idempotency_key = f"knowledge:visual_analysis:{course_id}:source:{source_revision}"
        with self._knowledge_job_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._conn.execute(
                    """SELECT * FROM knowledge_jobs WHERE course_id = ? AND job_type = 'visual_analysis'
                       AND target_source_revision = ?""",
                    (course_id, source_revision),
                ).fetchone()
                if existing is not None:
                    stored = self._conn.execute(
                        "SELECT asset_id, reason_code FROM visual_analysis_requests WHERE job_id = ? ORDER BY asset_id",
                        (existing["job_id"],),
                    ).fetchall()
                    if [(row["asset_id"], row["reason_code"]) for row in stored] != [
                        (asset_id, normalized[asset_id]) for asset_id in asset_ids
                    ]:
                        raise ValueError("Current visual-analysis job is already bound to a different asset selection")
                    self._conn.commit()
                    return self._row_to_knowledge_job(existing)
                next_revision = self._conn.execute(
                    """SELECT COALESCE(MAX(revision), -1) + 1 AS next_revision FROM knowledge_jobs
                       WHERE course_id = ? AND material_id IS NULL AND job_type = 'visual_analysis'""",
                    (course_id,),
                ).fetchone()
                if next_revision is None:
                    raise RuntimeError("Could not allocate visual analysis job revision")
                job_id = str(uuid.uuid4())
                self._conn.execute(
                    """INSERT INTO knowledge_jobs (
                        job_id, course_id, material_id, job_type, revision, scope, status, attempt,
                        max_attempts, idempotency_key, token_budget, target_source_revision,
                        target_knowledge_revision
                    ) VALUES (?, ?, NULL, 'visual_analysis', ?, 'course', 'queued', 0, ?, ?, ?, ?, ?)""",
                    (job_id, course_id, int(next_revision["next_revision"]), max_attempts,
                     idempotency_key, token_budget, source_revision, knowledge_revision),
                )
                self._conn.executemany(
                    """INSERT INTO visual_analysis_requests (
                        job_id, course_id, source_revision, knowledge_revision, asset_id, material_id,
                        storage_path, reason_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (job_id, course_id, source_revision, knowledge_revision, asset_id,
                         by_asset[asset_id]["material_id"], by_asset[asset_id]["storage_path"],
                         normalized[asset_id])
                        for asset_id in asset_ids
                    ],
                )
                row = self._conn.execute("SELECT * FROM knowledge_jobs WHERE job_id = ?", (job_id,)).fetchone()
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        if row is None:
            raise RuntimeError("Visual analysis job was not persisted")
        return self._row_to_knowledge_job(row)

    def get_visual_analysis_requests(self, course_id: str, job_id: str) -> list[dict[str, str]]:
        rows = self._conn.execute(
            """SELECT asset_id, material_id, storage_path, reason_code FROM visual_analysis_requests
               WHERE course_id = ? AND job_id = ? ORDER BY asset_id""",
            (course_id, job_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def publish_visual_analysis_results_if_current(
        self,
        *,
        course_id: str,
        job_id: str,
        job_attempt: int,
        lease_owner: str,
        source_revision: str,
        knowledge_revision: str,
        results: Sequence[dict[str, str]],
    ) -> bool:
        """Atomically publish only results matching the immutable asset request."""
        if not results or any(not item.get("analysis_text", "").strip() for item in results):
            raise ValueError("Visual analysis publication requires non-empty results")
        with self._knowledge_job_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                job = self._conn.execute(
                    """SELECT * FROM knowledge_jobs WHERE job_id = ? AND course_id = ?
                       AND job_type = 'visual_analysis'""",
                    (job_id, course_id),
                ).fetchone()
                if (
                    job is None or job["status"] != "running" or job["attempt"] != job_attempt
                    or job["lease_owner"] != lease_owner or job["lease_expires_at"] is None
                    or job["lease_expires_at"] <= self._conn.execute("SELECT datetime('now')").fetchone()[0]
                    or job["target_source_revision"] != source_revision
                    or job["target_knowledge_revision"] != knowledge_revision
                    or self.get_compilable_source_manifest(course_id) is None
                    or self.get_compilable_source_manifest(course_id)[0] != source_revision
                ):
                    self._conn.rollback()
                    return False
                requested = self._conn.execute(
                    "SELECT asset_id FROM visual_analysis_requests WHERE job_id = ? AND course_id = ?",
                    (job_id, course_id),
                ).fetchall()
                requested_ids = {row["asset_id"] for row in requested}
                result_ids = [str(item.get("asset_id", "")) for item in results]
                if set(result_ids) != requested_ids or len(result_ids) != len(set(result_ids)):
                    self._conn.rollback()
                    return False
                self._conn.executemany(
                    """INSERT INTO visual_analysis_results (
                        job_id, course_id, source_revision, knowledge_revision, asset_id, model_call_id, analysis_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(job_id, asset_id) DO NOTHING""",
                    [
                        (job_id, course_id, source_revision, knowledge_revision, item["asset_id"],
                         item["model_call_id"], item["analysis_text"])
                        for item in results
                    ],
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return True

    def get_visual_analysis_results(self, course_id: str, job_id: str) -> list[dict[str, str]]:
        rows = self._conn.execute(
            """SELECT asset_id, model_call_id, analysis_text FROM visual_analysis_results
               WHERE course_id = ? AND job_id = ? ORDER BY asset_id""",
            (course_id, job_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def enqueue_knowledge_job(self, job: KnowledgeJobCreate) -> KnowledgeJob:
        """Insert a job once per stable logical identity and idempotency key.

        A reused key is valid only for the exact same course-scoped immutable
        identity.  A different key cannot create a second job for the same
        explicit course/material/revision scope either; duplicate job rows
        would make status and evidence publication nondeterministic.
        """
        if self.get_course(job.course_id) is None:
            raise ValueError(f"Cannot enqueue knowledge job: course {job.course_id!r} not found")
        if job.material_id is not None and self.get_material(job.course_id, job.material_id) is None:
            raise ValueError(
                "Cannot enqueue material knowledge job: material does not belong to course"
            )

        with self._knowledge_job_lock:
            existing_logical = self._get_knowledge_job_by_logical_identity(job)
            if existing_logical is not None:
                if existing_logical.idempotency_key == job.idempotency_key:
                    requested_identity = (
                        job.course_id,
                        job.material_id,
                        job.job_type,
                        job.scope,
                        job.token_budget,
                        job.max_attempts,
                        job.target_source_revision,
                        job.target_knowledge_revision,
                    )
                    existing_identity = (
                        existing_logical.course_id,
                        existing_logical.material_id,
                        existing_logical.job_type,
                        existing_logical.scope,
                        existing_logical.token_budget,
                        existing_logical.max_attempts,
                        existing_logical.target_source_revision,
                        existing_logical.target_knowledge_revision,
                    )
                    if existing_identity == requested_identity:
                        return existing_logical
                    raise ValueError("Knowledge job idempotency key is already bound to another job identity")
                raise ValueError(
                    "Knowledge job logical identity is already bound to another idempotency key"
                )
            persisted_job = job
            if job.scope == "course":
                next_revision_row = self._conn.execute(
                    """
                    SELECT COALESCE(MAX(revision), -1) + 1 AS next_revision
                    FROM knowledge_jobs
                    WHERE course_id = ? AND material_id IS NULL AND job_type = ?
                    """,
                    (job.course_id, job.job_type),
                ).fetchone()
                if next_revision_row is None:
                    raise RuntimeError("Could not allocate course compile revision")
                persisted_job = job.model_copy(
                    update={"revision": int(next_revision_row["next_revision"])}
                )
            if persisted_job.revision is None:
                raise RuntimeError("Knowledge job revision was not assigned")
            try:
                self._conn.execute(
                    """
                    INSERT INTO knowledge_jobs
                        (job_id, course_id, material_id, job_type, revision, scope,
                         status, attempt, max_attempts, idempotency_key, token_budget,
                         target_source_revision, target_knowledge_revision)
                    VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?, ?, ?, ?)
                    ON CONFLICT(idempotency_key) DO NOTHING
                    """,
                    (
                        persisted_job.job_id,
                        persisted_job.course_id,
                        persisted_job.material_id,
                        persisted_job.job_type,
                        persisted_job.revision,
                        persisted_job.scope,
                        persisted_job.max_attempts,
                        persisted_job.idempotency_key,
                        persisted_job.token_budget,
                        persisted_job.target_source_revision,
                        persisted_job.target_knowledge_revision,
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                existing_logical = self._get_knowledge_job_by_logical_identity(job)
                if existing_logical is not None:
                    raise ValueError(
                        "Knowledge job logical identity is already bound to another idempotency key"
                    ) from exc
                raise
            row = self._conn.execute(
                "SELECT * FROM knowledge_jobs WHERE idempotency_key = ?",
                (job.idempotency_key,),
            ).fetchone()

        if row is None:  # Defensive: the UNIQUE conflict target must always return a row.
            raise RuntimeError("Knowledge job enqueue did not persist a job")
        persisted = self._row_to_knowledge_job(row)
        immutable_identity = (
            persisted.course_id,
            persisted.material_id,
            persisted.job_type,
            persisted.revision,
            persisted.scope,
            persisted.max_attempts,
            persisted.target_source_revision,
            persisted.target_knowledge_revision,
        )
        requested_identity = (
            persisted_job.course_id,
            persisted_job.material_id,
            persisted_job.job_type,
            persisted_job.revision,
            persisted_job.scope,
            persisted_job.max_attempts,
            persisted_job.target_source_revision,
            persisted_job.target_knowledge_revision,
        )
        if immutable_identity != requested_identity:
            raise ValueError("Knowledge job idempotency key is already bound to another job identity")
        return persisted

    def _get_knowledge_job_by_logical_identity(
        self,
        job: KnowledgeJobCreate,
    ) -> KnowledgeJob | None:
        if job.material_id is None:
            if job.target_source_revision is None:
                raise ValueError("course knowledge job requires target_source_revision")
            row = self._conn.execute(
                """
                SELECT * FROM knowledge_jobs
                WHERE course_id = ?
                  AND material_id IS NULL
                  AND job_type = ?
                  AND target_source_revision = ?
                """,
                (job.course_id, job.job_type, job.target_source_revision),
            ).fetchone()
        else:
            if job.revision is None:
                raise ValueError("material knowledge job requires revision")
            row = self._conn.execute(
                """
                SELECT * FROM knowledge_jobs
                WHERE course_id = ? AND material_id = ? AND job_type = ? AND revision = ?
                """,
                (job.course_id, job.material_id, job.job_type, job.revision),
            ).fetchone()
        return self._row_to_knowledge_job(row) if row is not None else None

    def get_knowledge_job(self, course_id: str, job_id: str) -> KnowledgeJob | None:
        row = self._conn.execute(
            "SELECT * FROM knowledge_jobs WHERE job_id = ? AND course_id = ?",
            (job_id, course_id),
        ).fetchone()
        return self._row_to_knowledge_job(row) if row is not None else None

    def list_knowledge_jobs(
        self,
        course_id: str,
        status: str | None = None,
        *,
        material_id: str | None = None,
    ) -> list[KnowledgeJob]:
        """List durable job facts, optionally within one material scope."""
        clauses = ["course_id = ?"]
        params: list[Any] = [course_id]
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if material_id is not None:
            clauses.append("material_id = ?")
            params.append(material_id)
        where = " AND ".join(clauses)
        rows = self._conn.execute(
            f"SELECT * FROM knowledge_jobs WHERE {where} ORDER BY created_at, job_id",
            params,
        ).fetchall()
        return [self._row_to_knowledge_job(row) for row in rows]

    # --- V2 model-call audit and course/job budget reservations ---

    def reserve_model_call(self, request: ModelCallReservationRequest) -> ModelCallAudit:
        """Atomically reserve a conservative provider-call budget.

        A reservation is recorded *before* the wrapper may make a network
        request. Both budget scopes aggregate every previous attempt for this
        job/source revision, including unresolved or unknown-billing calls.

        This is the knowledge_job-owner path: it validates a current knowledge-
        job lease and revision.  agent_run-owned calls must use
        :meth:`reserve_agent_run_model_call` instead.
        """
        if request.owner_type != "knowledge_job":
            raise ValueError(
                "reserve_model_call only handles knowledge_job owners; "
                "use reserve_agent_run_model_call for agent runs"
            )
        if not request.job_id or request.job_attempt is None:
            raise ValueError("knowledge_job model calls require job_id and job_attempt")
        with self._knowledge_job_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                job = self._conn.execute(
                    """
                    SELECT * FROM knowledge_jobs
                    WHERE job_id = ? AND course_id = ?
                    """,
                    (request.job_id, request.course_id),
                ).fetchone()
                if job is None:
                    raise ValueError("Cannot reserve model call for an unknown course job")
                if (
                    job["scope"] != "course"
                    or job["status"] != "running"
                    or job["attempt"] != request.job_attempt
                    or job["lease_owner"] != request.lease_owner
                    or job["lease_expires_at"] is None
                    or job["lease_expires_at"] <= self._conn.execute("SELECT datetime('now')").fetchone()[0]
                    or job["target_source_revision"] != request.source_revision
                    or job["target_knowledge_revision"] != request.knowledge_revision
                ):
                    raise ValueError(
                        "Cannot reserve model call without the current course job lease and revision"
                    )

                self._conn.execute(
                    """
                    INSERT INTO course_model_budgets (course_id, source_revision, token_budget)
                    VALUES (?, ?, ?)
                    ON CONFLICT(course_id, source_revision) DO NOTHING
                    """,
                    (
                        request.course_id,
                        request.source_revision,
                        request.course_budget_tokens,
                    ),
                )
                budget_row = self._conn.execute(
                    """
                    SELECT token_budget FROM course_model_budgets
                    WHERE course_id = ? AND source_revision = ?
                    """,
                    (request.course_id, request.source_revision),
                ).fetchone()
                if budget_row is None:
                    raise RuntimeError("Course model budget was not persisted")
                persisted_course_budget = int(budget_row["token_budget"])

                current_manifest = self.get_compilable_source_manifest(request.course_id)
                rejection_code: str | None = None
                rejection_detail: str | None = None
                if current_manifest is None or current_manifest[0] != request.source_revision:
                    rejection_code = "stale_course_source_revision"
                    rejection_detail = "Current course material no longer matches this model-call source revision"
                elif persisted_course_budget != request.course_budget_tokens:
                    rejection_code = "course_budget_configuration_conflict"
                    rejection_detail = (
                        "The source revision already has a different persisted course token budget"
                    )

                course_used = int(
                    self._conn.execute(
                        """
                        SELECT COALESCE(SUM(accounted_tokens), 0) AS used_tokens
                        FROM model_call_audits
                        WHERE course_id = ? AND source_revision = ?
                        """,
                        (request.course_id, request.source_revision),
                    ).fetchone()["used_tokens"]
                )
                job_used = int(
                    self._conn.execute(
                        """
                        SELECT COALESCE(SUM(accounted_tokens), 0) AS used_tokens
                        FROM model_call_audits
                        WHERE course_id = ? AND job_id = ?
                        """,
                        (request.course_id, request.job_id),
                    ).fetchone()["used_tokens"]
                )
                if rejection_code is None and course_used + request.reserved_tokens > persisted_course_budget:
                    rejection_code = "token_budget_exhausted"
                    rejection_detail = "Course model token budget would be exceeded before this request"
                job_budget = job["token_budget"]
                if (
                    rejection_code is None
                    and job_budget is not None
                    and job_used + request.reserved_tokens > int(job_budget)
                ):
                    rejection_code = "token_budget_exhausted"
                    rejection_detail = "Knowledge job token budget would be exceeded before this request"

                if rejection_code is None:
                    self._insert_model_call_audit(
                        request,
                        status="reserved",
                        accounted_tokens=request.reserved_tokens,
                        job_budget_tokens=job_budget,
                    )
                else:
                    self._insert_model_call_audit(
                        request,
                        status="rejected",
                        accounted_tokens=0,
                        job_budget_tokens=job_budget,
                        error_code=rejection_code,
                        error_detail=rejection_detail,
                        finished=True,
                    )
                self._conn.execute(
                    """
                    UPDATE course_model_budgets SET updated_at = datetime('now')
                    WHERE course_id = ? AND source_revision = ?
                    """,
                    (request.course_id, request.source_revision),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

        audit = self.get_model_call_audit(request.course_id, request.call_id)
        if audit is None:
            raise RuntimeError("Model-call reservation could not be reloaded")
        return audit

    def _insert_model_call_audit(
        self,
        request: ModelCallReservationRequest,
        *,
        status: str,
        accounted_tokens: int,
        job_budget_tokens: int | None,
        error_code: str | None = None,
        error_detail: str | None = None,
        finished: bool = False,
    ) -> None:
        # Resolve owner_id: explicit > job_id (knowledge_job) > run_id (agent_run).
        owner_id = request.owner_id
        if owner_id is None:
            owner_id = request.job_id if request.owner_type == "knowledge_job" else request.run_id
        self._conn.execute(
            """
            INSERT INTO model_call_audits (
                call_id, course_id, job_id, job_attempt, source_revision, knowledge_revision,
                call_kind, purpose, provider, model, request_fingerprint, status,
                input_token_upper_bound, max_output_tokens, reserved_tokens, usage_source,
                accounted_tokens, course_budget_tokens, job_budget_tokens, error_code,
                error_detail, finished_at, owner_type, owner_id, budget_scope, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unavailable', ?, ?, ?, ?, ?,
                      CASE WHEN ? THEN datetime('now') ELSE NULL END, ?, ?, ?, ?)
            """,
            (
                request.call_id,
                request.course_id,
                request.job_id,
                request.job_attempt,
                request.source_revision,
                request.knowledge_revision,
                request.call_kind,
                request.purpose,
                request.provider,
                request.model,
                request.request_fingerprint,
                status,
                request.input_token_upper_bound,
                request.max_output_tokens,
                request.reserved_tokens,
                accounted_tokens,
                request.course_budget_tokens,
                job_budget_tokens,
                error_code,
                error_detail,
                finished,
                request.owner_type,
                owner_id,
                request.budget_scope,
                request.run_id,
            ),
        )

    def complete_model_call(
        self,
        course_id: str,
        call_id: str,
        *,
        usage: ModelCallUsage,
        elapsed_ms: int,
        warning_code: str | None = None,
        warning_detail: str | None = None,
    ) -> ModelCallAudit:
        """Settle one completed provider response without losing unknown usage."""
        if elapsed_ms < 0:
            raise ValueError("elapsed_ms cannot be negative")
        with self._knowledge_job_lock:
            audit = self.get_model_call_audit(course_id, call_id)
            if audit is None or audit.status != "reserved":
                raise ValueError("Only a reserved model call can be completed")
            accounted_tokens = (
                usage.total_tokens if usage.usage_source == "provider" else audit.reserved_tokens
            )
            error_code = warning_code
            error_detail = warning_detail
            if usage.usage_source == "unavailable" and error_code is None:
                error_code = "model_usage_unavailable"
                error_detail = "Provider returned content without token usage; reservation remains charged"
            elif usage.total_tokens is not None and usage.total_tokens > audit.reserved_tokens:
                error_code = "model_usage_exceeded_reservation"
                error_detail = (
                    "Provider-reported usage exceeded the conservative reservation; "
                    "the audited actual usage remains charged"
                )
            updated = self._conn.execute(
                """
                UPDATE model_call_audits
                SET status = 'succeeded', input_tokens = ?, output_tokens = ?, reasoning_tokens = ?,
                    total_tokens = ?, usage_source = ?, accounted_tokens = ?, elapsed_ms = ?,
                    error_code = ?, error_detail = ?, finished_at = datetime('now')
                WHERE call_id = ? AND course_id = ? AND status = 'reserved'
                """,
                (
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.reasoning_tokens,
                    usage.total_tokens,
                    usage.usage_source,
                    accounted_tokens,
                    elapsed_ms,
                    error_code,
                    error_detail,
                    call_id,
                    course_id,
                ),
            )
            self._conn.execute(
                """
                UPDATE course_model_budgets SET updated_at = datetime('now')
                WHERE course_id = ? AND source_revision = ?
                """,
                (course_id, audit.source_revision),
            )
            self._conn.commit()
        if updated.rowcount != 1:
            raise ValueError("Reserved model call could not be completed")
        completed = self.get_model_call_audit(course_id, call_id)
        if completed is None:
            raise RuntimeError("Completed model call could not be reloaded")
        return completed

    def fail_model_call(
        self,
        course_id: str,
        call_id: str,
        *,
        error_code: str,
        error_detail: str,
        elapsed_ms: int,
    ) -> ModelCallAudit:
        """Persist a provider failure while retaining its unknown-billing reservation."""
        if not error_code.strip() or not error_detail.strip() or elapsed_ms < 0:
            raise ValueError("Model-call failure requires code, detail, and non-negative elapsed")
        with self._knowledge_job_lock:
            audit = self.get_model_call_audit(course_id, call_id)
            if audit is None or audit.status != "reserved":
                raise ValueError("Only a reserved model call can be failed")
            updated = self._conn.execute(
                """
                UPDATE model_call_audits
                SET status = 'failed', usage_source = 'unavailable', elapsed_ms = ?,
                    error_code = ?, error_detail = ?, finished_at = datetime('now')
                WHERE call_id = ? AND course_id = ? AND status = 'reserved'
                """,
                (elapsed_ms, error_code, error_detail, call_id, course_id),
            )
            self._conn.execute(
                """
                UPDATE course_model_budgets SET updated_at = datetime('now')
                WHERE course_id = ? AND source_revision = ?
                """,
                (course_id, audit.source_revision),
            )
            self._conn.commit()
        if updated.rowcount != 1:
            raise ValueError("Only a reserved model call can be failed")
        failed = self.get_model_call_audit(course_id, call_id)
        if failed is None:
            raise RuntimeError("Failed model call could not be reloaded")
        return failed

    def get_model_call_audit(self, course_id: str, call_id: str) -> ModelCallAudit | None:
        row = self._conn.execute(
            "SELECT * FROM model_call_audits WHERE course_id = ? AND call_id = ?",
            (course_id, call_id),
        ).fetchone()
        return self._row_to_model_call_audit(row) if row is not None else None

    def list_model_call_audits(
        self, course_id: str, *, job_id: str | None = None
    ) -> list[ModelCallAudit]:
        clauses = ["course_id = ?"]
        params: list[Any] = [course_id]
        if job_id is not None:
            clauses.append("job_id = ?")
            params.append(job_id)
        rows = self._conn.execute(
            f"SELECT * FROM model_call_audits WHERE {' AND '.join(clauses)} "
            "ORDER BY started_at, call_id",
            params,
        ).fetchall()
        return [self._row_to_model_call_audit(row) for row in rows]

    def get_course_model_budget(
        self, course_id: str, source_revision: str
    ) -> CourseModelBudget | None:
        row = self._conn.execute(
            """
            SELECT token_budget, updated_at FROM course_model_budgets
            WHERE course_id = ? AND source_revision = ?
            """,
            (course_id, source_revision),
        ).fetchone()
        if row is None:
            return None
        accounted_tokens = int(
            self._conn.execute(
                """
                SELECT COALESCE(SUM(accounted_tokens), 0) AS used_tokens
                FROM model_call_audits
                WHERE course_id = ? AND source_revision = ?
                """,
                (course_id, source_revision),
            ).fetchone()["used_tokens"]
        )
        last_error = self._conn.execute(
            """
            SELECT error_code, error_detail FROM model_call_audits
            WHERE course_id = ? AND source_revision = ? AND error_code IS NOT NULL
            ORDER BY started_at DESC, call_id DESC LIMIT 1
            """,
            (course_id, source_revision),
        ).fetchone()
        token_budget = int(row["token_budget"])
        return CourseModelBudget(
            course_id=course_id,
            source_revision=source_revision,
            token_budget=token_budget,
            accounted_tokens=accounted_tokens,
            available_tokens=max(0, token_budget - accounted_tokens),
            status="exhausted" if accounted_tokens >= token_budget else "available",
            last_error_code=last_error["error_code"] if last_error is not None else None,
            last_error_detail=last_error["error_detail"] if last_error is not None else None,
            updated_at=row["updated_at"],
        )

    def has_current_knowledge_job_lease(
        self,
        *,
        course_id: str,
        job_id: str,
        attempt: int,
        lease_owner: str,
        source_revision: str,
        knowledge_revision: str,
    ) -> bool:
        """Check the lease after I/O before a caller may publish derived data."""
        row = self._conn.execute(
            """
            SELECT 1 FROM knowledge_jobs
            WHERE job_id = ? AND course_id = ? AND status = 'running' AND attempt = ?
              AND lease_owner = ? AND lease_expires_at > datetime('now')
              AND target_source_revision = ? AND target_knowledge_revision = ?
            """,
            (
                job_id,
                course_id,
                attempt,
                lease_owner,
                source_revision,
                knowledge_revision,
            ),
        ).fetchone()
        return row is not None

    def claim_next_knowledge_job(
        self, lease_owner: str, lease_seconds: int
    ) -> KnowledgeJob | None:
        """Atomically claim one queued or expired-running job.

        The queue currently supports one SQLite database and guarded
        in-process concurrency.  `BEGIN IMMEDIATE` also serializes claims from
        separate SQLite connections sharing that database file.
        """
        if not lease_owner.strip():
            raise ValueError("lease_owner is required to claim a knowledge job")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")

        lease_modifier = f"+{lease_seconds} seconds"
        with self._knowledge_job_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                # A retry ceiling is durable queue state, not a worker-local
                # convention. Clean up exhausted queued/abandoned work before
                # choosing the next claim so it never remains a dead queue row.
                self._conn.execute(
                    """
                    UPDATE knowledge_jobs
                    SET status = 'failed',
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        error_code = 'retry_limit_exhausted',
                        error_detail = 'Knowledge job reached its configured retry limit',
                        error_at = datetime('now'),
                        finished_at = datetime('now'),
                        updated_at = datetime('now')
                    WHERE attempt >= max_attempts
                      AND status IN ('queued', 'running')
                      AND (status = 'queued' OR lease_expires_at <= datetime('now'))
                    """
                )
                row = self._conn.execute(
                    """
                    SELECT job_id FROM knowledge_jobs
                    WHERE attempt < max_attempts
                       AND (
                            job_type NOT IN ('extract_semantic_atoms', 'compile_terms', 'compile_kcs', 'extract_kc_relations')
                            OR (
                                job_type = 'extract_semantic_atoms'
                                AND EXISTS (
                                SELECT 1 FROM knowledge_jobs AS parent
                                WHERE parent.course_id = knowledge_jobs.course_id
                                  AND parent.job_type = 'compile_course'
                                  AND parent.status = 'succeeded'
                                  AND parent.target_source_revision = knowledge_jobs.target_source_revision
                                  AND parent.target_knowledge_revision = knowledge_jobs.target_knowledge_revision
                                )
                            )
                            OR (
                                job_type = 'compile_terms'
                                AND EXISTS (
                                    SELECT 1 FROM semantic_atom_compilations AS compilation
                                    INNER JOIN knowledge_jobs AS parent
                                        ON parent.job_id = compilation.job_id
                                       AND parent.course_id = compilation.course_id
                                       AND parent.job_type = 'extract_semantic_atoms'
                                       AND parent.status = 'succeeded'
                                       AND parent.target_source_revision = compilation.source_revision
                                       AND parent.target_knowledge_revision = compilation.knowledge_revision
                                    WHERE compilation.course_id = knowledge_jobs.course_id
                                      AND compilation.source_revision = knowledge_jobs.target_source_revision
                                      AND compilation.knowledge_revision = knowledge_jobs.target_knowledge_revision
                                )
                            )
                            OR (
                                job_type = 'compile_kcs'
                                AND EXISTS (
                                    SELECT 1 FROM term_compilations AS compilation
                                    INNER JOIN knowledge_jobs AS parent
                                        ON parent.job_id = compilation.job_id
                                       AND parent.course_id = compilation.course_id
                                       AND parent.job_type = 'compile_terms'
                                       AND parent.status = 'succeeded'
                                       AND parent.target_source_revision = compilation.source_revision
                                       AND parent.target_knowledge_revision = compilation.knowledge_revision
                                    WHERE compilation.course_id = knowledge_jobs.course_id
                                      AND compilation.source_revision = knowledge_jobs.target_source_revision
                                      AND compilation.knowledge_revision = knowledge_jobs.target_knowledge_revision
                                )
                            )
                            OR (
                                job_type = 'extract_kc_relations'
                                AND EXISTS (
                                    SELECT 1 FROM knowledge_component_compilations AS compilation
                                    INNER JOIN knowledge_jobs AS parent
                                        ON parent.job_id = compilation.job_id
                                       AND parent.course_id = compilation.course_id
                                       AND parent.job_type = 'compile_kcs'
                                       AND parent.status = 'succeeded'
                                       AND parent.target_source_revision = compilation.source_revision
                                       AND parent.target_knowledge_revision = compilation.knowledge_revision
                                    WHERE compilation.course_id = knowledge_jobs.course_id
                                      AND compilation.source_revision = knowledge_jobs.target_source_revision
                                      AND compilation.knowledge_revision = knowledge_jobs.target_knowledge_revision
                                )
                            )
                       )
                      AND (
                           status = 'queued'
                       OR (status = 'running'
                           AND lease_expires_at IS NOT NULL
                           AND lease_expires_at <= datetime('now'))
                      )
                    ORDER BY CASE status WHEN 'queued' THEN 0 ELSE 1 END, created_at, job_id
                    LIMIT 1
                    """
                ).fetchone()
                if row is None:
                    self._conn.commit()
                    return None

                job_id = row["job_id"]
                updated = self._conn.execute(
                    """
                    UPDATE knowledge_jobs
                    SET status = 'running',
                        attempt = attempt + 1,
                        lease_owner = ?,
                        lease_expires_at = datetime('now', ?),
                        started_at = COALESCE(started_at, datetime('now')),
                        finished_at = NULL,
                        updated_at = datetime('now')
                    WHERE job_id = ?
                    """,
                    (lease_owner, lease_modifier, job_id),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("Knowledge job claim lost its selected row")
                claimed = self._conn.execute(
                    "SELECT * FROM knowledge_jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

        if claimed is None:
            raise RuntimeError("Knowledge job claim did not return the claimed job")
        return self._row_to_knowledge_job(claimed)

    def complete_knowledge_job(
        self, course_id: str, job_id: str, lease_owner: str
    ) -> KnowledgeJob:
        """Mark a currently leased job successful; stale workers cannot complete it."""
        with self._knowledge_job_lock:
            updated = self._conn.execute(
                """
                UPDATE knowledge_jobs
                SET status = 'succeeded',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_code = NULL,
                    error_detail = NULL,
                    error_at = NULL,
                    finished_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE job_id = ? AND course_id = ? AND status = 'running' AND lease_owner = ?
                """,
                (job_id, course_id, lease_owner),
            )
            self._conn.commit()
        if updated.rowcount != 1:
            raise ValueError("Knowledge job cannot be completed by this lease owner")
        completed = self.get_knowledge_job(course_id, job_id)
        if completed is None:
            raise RuntimeError("Completed knowledge job could not be reloaded")
        return completed

    def renew_knowledge_job_lease(
        self,
        course_id: str,
        job_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> bool:
        """Extend a running lease only for its current owner.

        A false return is an explicit lost-lease signal.  Workers must stop
        writing derived knowledge when it occurs; a recovered worker may have
        already claimed the job.
        """
        if not lease_owner.strip():
            raise ValueError("lease_owner is required to renew a knowledge job lease")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        lease_modifier = f"+{lease_seconds} seconds"
        with self._knowledge_job_lock:
            updated = self._conn.execute(
                """
                UPDATE knowledge_jobs
                SET lease_expires_at = datetime('now', ?),
                    updated_at = datetime('now')
                WHERE job_id = ?
                  AND course_id = ?
                  AND status = 'running'
                  AND lease_owner = ?
                """,
                (
                    lease_modifier,
                    job_id,
                    course_id,
                    lease_owner,
                ),
            )
            self._conn.commit()
        return updated.rowcount == 1

    def fail_knowledge_job(
        self,
        course_id: str,
        job_id: str,
        lease_owner: str,
        error_detail: str,
        *,
        retryable: bool,
        error_code: str | None = None,
    ) -> KnowledgeJob:
        """Persist a visible failure and release the worker lease."""
        if not error_detail.strip():
            raise ValueError("error_detail is required when failing a knowledge job")
        with self._knowledge_job_lock:
            updated = self._conn.execute(
                """
                UPDATE knowledge_jobs
                SET status = CASE WHEN ? AND attempt < max_attempts THEN 'retryable' ELSE 'failed' END,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_code = CASE WHEN ? AND attempt >= max_attempts
                        THEN 'retry_limit_exhausted' ELSE ? END,
                    error_detail = ?,
                    error_at = datetime('now'),
                    finished_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE job_id = ? AND course_id = ? AND status = 'running' AND lease_owner = ?
                """,
                (retryable, retryable, error_code, error_detail, job_id, course_id, lease_owner),
            )
            self._conn.commit()
        if updated.rowcount != 1:
            raise ValueError("Knowledge job cannot be failed by this lease owner")
        failed = self.get_knowledge_job(course_id, job_id)
        if failed is None:
            raise RuntimeError("Failed knowledge job could not be reloaded")
        return failed

    def retry_knowledge_job(self, course_id: str, job_id: str) -> KnowledgeJob:
        """Requeue a terminal or retryable job without erasing its prior error."""
        with self._knowledge_job_lock:
            updated = self._conn.execute(
                """
                UPDATE knowledge_jobs
                SET status = 'queued',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    started_at = NULL,
                    finished_at = NULL,
                    updated_at = datetime('now')
                WHERE job_id = ? AND course_id = ? AND status IN ('retryable', 'failed')
                  AND attempt < max_attempts
                """,
                (job_id, course_id),
            )
            self._conn.commit()
        if updated.rowcount != 1:
            raise ValueError("Only failed or retryable knowledge jobs can be retried")
        retried = self.get_knowledge_job(course_id, job_id)
        if retried is None:
            raise RuntimeError("Retried knowledge job could not be reloaded")
        return retried

    @staticmethod
    def _row_to_knowledge_job(row: sqlite3.Row) -> KnowledgeJob:
        return KnowledgeJob(
            job_id=row["job_id"],
            course_id=row["course_id"],
            material_id=row["material_id"],
            job_type=row["job_type"],
            revision=row["revision"],
            scope=row["scope"],
            status=row["status"],
            attempt=row["attempt"],
            idempotency_key=row["idempotency_key"],
            token_budget=row["token_budget"],
            max_attempts=row["max_attempts"],
            target_source_revision=row["target_source_revision"],
            target_knowledge_revision=row["target_knowledge_revision"],
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            error_code=row["error_code"],
            error_detail=row["error_detail"],
            error_at=row["error_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    @staticmethod
    def _row_to_model_call_audit(row: sqlite3.Row) -> ModelCallAudit:
        keys = row.keys()
        return ModelCallAudit(
            call_id=row["call_id"],
            course_id=row["course_id"],
            job_id=row["job_id"],
            job_attempt=row["job_attempt"],
            source_revision=row["source_revision"],
            knowledge_revision=row["knowledge_revision"],
            call_kind=row["call_kind"],
            purpose=row["purpose"],
            provider=row["provider"],
            model=row["model"],
            request_fingerprint=row["request_fingerprint"],
            status=row["status"],
            input_token_upper_bound=row["input_token_upper_bound"],
            max_output_tokens=row["max_output_tokens"],
            reserved_tokens=row["reserved_tokens"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            reasoning_tokens=row["reasoning_tokens"],
            total_tokens=row["total_tokens"],
            usage_source=row["usage_source"],
            accounted_tokens=row["accounted_tokens"],
            course_budget_tokens=row["course_budget_tokens"],
            job_budget_tokens=row["job_budget_tokens"],
            elapsed_ms=row["elapsed_ms"],
            error_code=row["error_code"],
            error_detail=row["error_detail"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            owner_type=row["owner_type"] if "owner_type" in keys else "knowledge_job",
            owner_id=row["owner_id"] if "owner_id" in keys else None,
            budget_scope=row["budget_scope"] if "budget_scope" in keys else "knowledge_build",
            run_id=row["run_id"] if "run_id" in keys else None,
        )

    @staticmethod
    def _row_to_semantic_atom(row: sqlite3.Row) -> SemanticAtom:
        return SemanticAtom(
            atom_id=row["atom_id"],
            course_id=row["course_id"],
            source_revision=row["source_revision"],
            knowledge_revision=row["knowledge_revision"],
            section_id=row["section_id"],
            atom_type=row["atom_type"],
            statement=row["statement"],
            evidence=[EvidenceRef.model_validate(item) for item in json.loads(row["evidence_json"])],
            model_call_id=row["model_call_id"],
            generation_method=row["generation_method"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_semantic_atom_compilation(row: sqlite3.Row) -> SemanticAtomCompilation:
        return SemanticAtomCompilation(
            course_id=row["course_id"],
            source_revision=row["source_revision"],
            knowledge_revision=row["knowledge_revision"],
            compiler_version=row["compiler_version"],
            job_id=row["job_id"],
            atom_count=row["atom_count"],
            rejected_candidate_count=row["rejected_candidate_count"],
            model_call_count=row["model_call_count"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_term(row: sqlite3.Row, supporting_atom_ids: list[str]) -> Term:
        return Term(
            term_id=row["term_id"],
            course_id=row["course_id"],
            source_revision=row["source_revision"],
            knowledge_revision=row["knowledge_revision"],
            canonical_name=row["canonical_name"],
            canonical_key=row["canonical_key"],
            term_kind=row["term_kind"],
            definition=row["definition"],
            definition_atom_id=row["definition_atom_id"],
            supporting_atom_ids=supporting_atom_ids,
            evidence=[EvidenceRef.model_validate(value) for value in json.loads(row["evidence_json"])],
            generation_method=row["generation_method"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_term_compilation(row: sqlite3.Row) -> TermCompilation:
        return TermCompilation(
            course_id=row["course_id"],
            source_revision=row["source_revision"],
            knowledge_revision=row["knowledge_revision"],
            compiler_version=row["compiler_version"],
            job_id=row["job_id"],
            term_count=row["term_count"],
            rejected_atom_count=row["rejected_atom_count"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_knowledge_component(row: sqlite3.Row) -> KnowledgeComponent:
        return KnowledgeComponent(
            kc_id=row["kc_id"],
            course_id=row["course_id"],
            source_revision=row["source_revision"],
            knowledge_revision=row["knowledge_revision"],
            term_id=row["term_id"],
            name=row["name"],
            kind=row["kind"],
            definition=row["definition"],
            section_id=row["section_id"],
            evidence=[EvidenceRef.model_validate(value) for value in json.loads(row["evidence_json"])],
            generation_method=row["generation_method"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_kc_relation(row: sqlite3.Row) -> KCRelation:
        return KCRelation(
            relation_id=row["relation_id"], course_id=row["course_id"],
            source_revision=row["source_revision"], knowledge_revision=row["knowledge_revision"],
            source_kc_id=row["source_kc_id"], target_kc_id=row["target_kc_id"],
            relation_type=row["relation_type"],
            evidence=EvidenceRef.model_validate(json.loads(row["evidence_json"])),
            model_call_id=row["model_call_id"], generation_method=row["generation_method"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_course_compilation(row: sqlite3.Row) -> CourseCompilation:
        return CourseCompilation(
            course_id=row["course_id"],
            source_revision=row["source_revision"],
            knowledge_revision=row["knowledge_revision"],
            compiler_version=row["compiler_version"],
            job_id=row["job_id"],
            source_manifest_json=row["source_manifest_json"],
            source_fragment_count=row["source_fragment_count"],
            outline_section_count=row["outline_section_count"],
            warning_count=row["warning_count"],
            created_at=row["created_at"],
        )

    # --- Chat Sessions ---

    def create_chat_session(self, session_id: str, course_id: str, title: str = "新对话") -> None:
        self._conn.execute(
            "INSERT INTO chat_sessions (id, course_id, title) VALUES (?, ?, ?)",
            (session_id, course_id, title),
        )
        self._conn.commit()

    def get_chat_sessions(self, course_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM chat_sessions WHERE course_id = ? ORDER BY updated_at DESC",
            (course_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_chat_session_title(self, session_id: str, title: str) -> None:
        self._conn.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (title, session_id),
        )
        self._conn.commit()

    def touch_chat_session(self, session_id: str, course_id: str = "") -> None:
        # When course_id is provided, the update is fenced so a cross-course
        # caller cannot bump another course's session timestamp.  Empty
        # course_id preserves the legacy unfenced behaviour.
        if course_id:
            self._conn.execute(
                "UPDATE chat_sessions SET updated_at = datetime('now') WHERE id = ? AND course_id = ?",
                (session_id, course_id),
            )
        else:
            self._conn.execute(
                "UPDATE chat_sessions SET updated_at = datetime('now') WHERE id = ?",
                (session_id,),
            )
        self._conn.commit()

    def delete_chat_session(self, session_id: str, course_id: str = "") -> None:
        # Fence session deletion by course_id when provided, so a wrong
        # course_id leaves both messages and session untouched.
        if course_id:
            self._conn.execute(
                "DELETE FROM chat_messages WHERE session_id = ? AND course_id = ?",
                (session_id, course_id),
            )
            self._conn.execute(
                "DELETE FROM chat_sessions WHERE id = ? AND course_id = ?",
                (session_id, course_id),
            )
        else:
            self._conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        self._conn.commit()

    # --- Chat Messages ---

    def save_chat_message(
        self,
        msg_id: str,
        course_id: str,
        role: str,
        content: str,
        session_id: str = "",
        citations_json: str | None = None,
        confidence_status: str | None = None,
        refusal_reason: str | None = None,
        *,
        run_id: str | None = None,
        source_revision: str | None = None,
        knowledge_revision: str | None = None,
        answer_source: str | None = None,
        envelope_json: str | None = None,
    ) -> None:
        # When a session_id is supplied, verify it belongs to the same course
        # before persisting, so a swapped session_id cannot file a message under
        # the wrong course.  Legacy callers that omit session_id are unfenced.
        if session_id:
            owner = self._conn.execute(
                "SELECT course_id FROM chat_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if owner is None:
                raise ValueError("Cannot save a chat message for an unknown chat session")
            if owner["course_id"] != course_id:
                raise ValueError("Chat session does not belong to this course")
        self._conn.execute(
            "INSERT INTO chat_messages (id, course_id, session_id, role, content, "
            "citations_json, confidence_status, refusal_reason, run_id, "
            "source_revision, knowledge_revision, answer_source, envelope_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (msg_id, course_id, session_id, role, content, citations_json,
             confidence_status, refusal_reason, run_id, source_revision,
             knowledge_revision, answer_source, envelope_json),
        )
        self._conn.commit()

    def get_chat_messages(self, course_id: str, session_id: str = "", limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        if session_id:
            rows = self._conn.execute(
                "SELECT * FROM chat_messages WHERE course_id = ? AND session_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?",
                (course_id, session_id, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM chat_messages WHERE course_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?",
                (course_id, limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_chat_messages(self, course_id: str, session_id: str = "") -> int:
        if session_id:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM chat_messages WHERE course_id = ? AND session_id = ?",
                (course_id, session_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM chat_messages WHERE course_id = ?",
                (course_id,),
            ).fetchone()
        return row["cnt"] if row else 0

    # --- Agent Runs ---

    def create_agent_run(self, run: AgentRun) -> None:
        """Create a new agent run with course/session isolation.

        The chat session must already exist and belong to the same course, so
        an agent run can never be filed under a session that crosses the
        course fence.
        """
        session = self._conn.execute(
            "SELECT course_id FROM chat_sessions WHERE id = ?",
            (run.session_id,),
        ).fetchone()
        if session is None:
            raise ValueError("Cannot create agent run for an unknown chat session")
        if session["course_id"] != run.course_id:
            raise ValueError("Chat session does not belong to this course")
        self._conn.execute(
            """
            INSERT INTO agent_runs (
                run_id, turn_id, course_id, session_id, workflow_kind,
                source_revision, knowledge_revision, status, scope_mode,
                selected_material_ids_json, selected_note_ids_json,
                review_context_json, token_budget, error_code, error_detail
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.turn_id,
                run.course_id,
                run.session_id,
                run.workflow_kind,
                run.source_revision,
                run.knowledge_revision,
                run.status,
                run.scope_mode,
                json.dumps(run.selected_material_ids) if run.selected_material_ids else None,
                json.dumps(run.selected_note_ids) if run.selected_note_ids else None,
                json.dumps(run.review_context) if run.review_context is not None else None,
                run.token_budget,
                run.error_code,
                run.error_detail,
            ),
        )
        self._conn.commit()

    def get_agent_run(self, course_id: str, run_id: str) -> AgentRun | None:
        """Load a single agent run, verifying course ownership."""
        row = self._conn.execute(
            "SELECT * FROM agent_runs WHERE run_id = ? AND course_id = ?",
            (run_id, course_id),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_agent_run(row)

    def update_agent_run_status(
        self,
        course_id: str,
        run_id: str,
        status: str,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        """Update run status with a course fence.

        A wrong ``course_id`` is a silent no-op so callers can stay idempotent
        without leaking whether a run exists in another course.
        """
        with self._knowledge_job_lock:
            self._conn.execute(
                """
                UPDATE agent_runs
                SET status = ?, error_code = ?, error_detail = ?, updated_at = datetime('now')
                WHERE run_id = ? AND course_id = ?
                """,
                (status, error_code, error_detail, run_id, course_id),
            )
            self._conn.commit()

    def create_agent_step(self, step: AgentStep) -> None:
        """Record one step in an agent run."""
        self._conn.execute(
            """
            INSERT INTO agent_steps (
                step_id, run_id, agent_role, step_type, status,
                model_call_id, output_type, input_fingerprint, elapsed_ms,
                error, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step.step_id,
                step.run_id,
                step.agent_role,
                step.step_type,
                step.status,
                step.model_call_id,
                step.output_type,
                step.input_fingerprint,
                step.elapsed_ms,
                step.error,
                step.completed_at,
            ),
        )
        self._conn.commit()

    def update_agent_step(self, step_id: str, status: str, **kwargs: Any) -> None:
        """Update a step's status and optional fields (elapsed_ms, error, ...).

        Unknown kwargs are ignored to keep the call site resilient; only the
        whitelisted columns below are written.
        """
        allowed = {
            "model_call_id",
            "output_type",
            "input_fingerprint",
            "elapsed_ms",
            "error",
        }
        columns: list[str] = ["status = ?"]
        params: list[Any] = [status]
        for key, value in kwargs.items():
            if key in allowed:
                columns.append(f"{key} = ?")
                params.append(value)
        if status in ("completed", "failed", "skipped"):
            columns.append("completed_at = datetime('now')")
        params.append(step_id)
        with self._knowledge_job_lock:
            self._conn.execute(
                f"UPDATE agent_steps SET {', '.join(columns)} WHERE step_id = ?",
                params,
            )
            self._conn.commit()

    def get_agent_steps(self, run_id: str) -> list[AgentStep]:
        """Load all steps for a run, ordered by creation time."""
        rows = self._conn.execute(
            "SELECT * FROM agent_steps WHERE run_id = ? ORDER BY created_at, step_id",
            (run_id,),
        ).fetchall()
        return [self._row_to_agent_step(row) for row in rows]

    @staticmethod
    def _row_to_agent_run(row: sqlite3.Row) -> AgentRun:
        review_context: dict[str, Any] | None = None
        if row["review_context_json"] is not None:
            review_context = json.loads(row["review_context_json"])
        selected_material_ids: list[str] = []
        if row["selected_material_ids_json"]:
            selected_material_ids = list(json.loads(row["selected_material_ids_json"]))
        selected_note_ids: list[str] = []
        if row["selected_note_ids_json"]:
            selected_note_ids = list(json.loads(row["selected_note_ids_json"]))
        return AgentRun(
            run_id=row["run_id"],
            turn_id=row["turn_id"],
            course_id=row["course_id"],
            session_id=row["session_id"],
            workflow_kind=row["workflow_kind"],
            source_revision=row["source_revision"],
            knowledge_revision=row["knowledge_revision"],
            status=row["status"],
            scope_mode=row["scope_mode"],
            selected_material_ids=selected_material_ids,
            selected_note_ids=selected_note_ids,
            review_context=review_context,
            token_budget=row["token_budget"],
            error_code=row["error_code"],
            error_detail=row["error_detail"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_agent_step(row: sqlite3.Row) -> AgentStep:
        return AgentStep(
            step_id=row["step_id"],
            run_id=row["run_id"],
            agent_role=row["agent_role"],
            step_type=row["step_type"],
            status=row["status"],
            model_call_id=row["model_call_id"],
            output_type=row["output_type"],
            input_fingerprint=row["input_fingerprint"],
            elapsed_ms=row["elapsed_ms"],
            error=row["error"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    # --- Agent-run model-call reservations ---

    def reserve_agent_run_model_call(self, request: ModelCallReservationRequest) -> ModelCallAudit:
        """Reserve budget for an agent-run-owned model call.

        Unlike :meth:`reserve_model_call`, this does NOT require a knowledge-job
        lease.  It validates that the agent run exists, belongs to the request's
        course, is in a non-terminal status, and that both the per-run token
        budget and the course-level interactive budget still have room.

        The reservation is recorded before any provider call, so a rejected
        reservation makes zero provider requests.  SDK retries must remain 0.
        """
        if request.owner_type != "agent_run":
            raise ValueError(
                "reserve_agent_run_model_call only handles agent_run owners; "
                "use reserve_model_call for knowledge jobs"
            )
        if not request.run_id:
            raise ValueError("agent_run model calls require run_id")

        with self._knowledge_job_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                run_row = self._conn.execute(
                    """
                    SELECT run_id, course_id, status, token_budget
                    FROM agent_runs WHERE run_id = ? AND course_id = ?
                    """,
                    (request.run_id, request.course_id),
                ).fetchone()
                if run_row is None:
                    raise ValueError("Cannot reserve model call for an unknown agent run")
                run_status = str(run_row["status"])
                if run_status not in AGENT_RUN_ACTIVE_STATUSES:
                    raise ValueError(
                        f"Cannot reserve model call for an agent run in terminal status {run_status!r}"
                    )
                run_budget = int(run_row["token_budget"])

                # Per-run budget: sum accounted_tokens for this owner_id.
                run_used = int(
                    self._conn.execute(
                        """
                        SELECT COALESCE(SUM(accounted_tokens), 0) AS used_tokens
                        FROM model_call_audits
                        WHERE owner_type = 'agent_run' AND owner_id = ?
                        """,
                        (request.run_id,),
                    ).fetchone()["used_tokens"]
                )

                # Course-level interactive budget: reuse course_model_budgets
                # with source_revision = '__interactive__' as the budget key.
                # This keeps a single, audited course budget table without
                # adding a parallel interactive budget table for the MVP.
                interactive_budget_key = "__interactive__"
                self._conn.execute(
                    """
                    INSERT INTO course_model_budgets (course_id, source_revision, token_budget)
                    VALUES (?, ?, ?)
                    ON CONFLICT(course_id, source_revision) DO NOTHING
                    """,
                    (request.course_id, interactive_budget_key, request.course_budget_tokens),
                )
                interactive_budget_row = self._conn.execute(
                    """
                    SELECT token_budget FROM course_model_budgets
                    WHERE course_id = ? AND source_revision = ?
                    """,
                    (request.course_id, interactive_budget_key),
                ).fetchone()
                if interactive_budget_row is None:
                    raise RuntimeError("Interactive course budget was not persisted")
                interactive_budget = int(interactive_budget_row["token_budget"])
                interactive_used = int(
                    self._conn.execute(
                        """
                        SELECT COALESCE(SUM(accounted_tokens), 0) AS used_tokens
                        FROM model_call_audits
                        WHERE course_id = ? AND budget_scope = 'interactive'
                        """,
                        (request.course_id,),
                    ).fetchone()["used_tokens"]
                )

                rejection_code: str | None = None
                rejection_detail: str | None = None
                if run_used + request.reserved_tokens > run_budget:
                    rejection_code = "token_budget_exhausted"
                    rejection_detail = "Agent run token budget would be exceeded before this request"
                elif interactive_used + request.reserved_tokens > interactive_budget:
                    rejection_code = "token_budget_exhausted"
                    rejection_detail = (
                        "Course interactive token budget would be exceeded before this request"
                    )
                elif interactive_budget != request.course_budget_tokens:
                    rejection_code = "course_budget_configuration_conflict"
                    rejection_detail = (
                        "The interactive budget already has a different persisted course token budget"
                    )

                if rejection_code is None:
                    self._insert_model_call_audit(
                        request,
                        status="reserved",
                        accounted_tokens=request.reserved_tokens,
                        job_budget_tokens=None,
                    )
                else:
                    self._insert_model_call_audit(
                        request,
                        status="rejected",
                        accounted_tokens=0,
                        job_budget_tokens=None,
                        error_code=rejection_code,
                        error_detail=rejection_detail,
                        finished=True,
                    )
                self._conn.execute(
                    """
                    UPDATE course_model_budgets SET updated_at = datetime('now')
                    WHERE course_id = ? AND source_revision = ?
                    """,
                    (request.course_id, interactive_budget_key),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

        audit = self.get_model_call_audit(request.course_id, request.call_id)
        if audit is None:
            raise RuntimeError("Agent-run model-call reservation could not be reloaded")
        return audit

    # --- Review Sessions ---

    def create_review_session(self, session_id: str, course_id: str, current_day: int = 1) -> None:
        self._conn.execute(
            "INSERT INTO review_sessions (id, course_id, current_day) VALUES (?, ?, ?)",
            (session_id, course_id, current_day),
        )
        self._conn.commit()

    def get_review_session(self, course_id: str) -> dict[str, Any] | None:
        import json
        row = self._conn.execute(
            "SELECT * FROM review_sessions WHERE course_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
            (course_id,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["completed_steps"] = json.loads(d.get("completed_steps", "[]"))
        return d

    def update_review_session(
        self,
        session_id: str,
        current_day: int | None = None,
        current_step: str | None = None,
        completed_steps_json: list[str] | None = None,
    ) -> None:
        import json
        if current_day is not None:
            self._conn.execute(
                "UPDATE review_sessions SET current_day = ?, updated_at = datetime('now') WHERE id = ?",
                (current_day, session_id),
            )
        if current_step is not None:
            self._conn.execute(
                "UPDATE review_sessions SET current_step = ?, updated_at = datetime('now') WHERE id = ?",
                (current_step, session_id),
            )
        if completed_steps_json is not None:
            self._conn.execute(
                "UPDATE review_sessions SET completed_steps = ?, updated_at = datetime('now') WHERE id = ?",
                (json.dumps(completed_steps_json, ensure_ascii=False), session_id),
            )
        self._conn.commit()

    def complete_review_session(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE review_sessions SET status = 'completed', updated_at = datetime('now') WHERE id = ?",
            (session_id,),
        )
        self._conn.commit()

    # --- User Settings ---

    def get_user_setting(self, key: str, default: str = "") -> str:
        row = self._conn.execute(
            "SELECT value FROM user_settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_user_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO user_settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, value),
        )
        self._conn.commit()

    # ===== Wiki-First Pipeline (阶段 2 新增) =====

    # --- DMAP ---

    def save_dmap(self, course_id: str, data_json: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO dmaps (course_id, data_json) VALUES (?, ?)",
            (course_id, data_json),
        )
        self._conn.commit()

    def get_dmap(self, course_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT data_json FROM dmaps WHERE course_id = ?", (course_id,)
        ).fetchone()
        return row["data_json"] if row else None

    def get_dmap_obj(self, course_id: str) -> DMAP | None:
        raw = self.get_dmap(course_id)
        if raw is None:
            return None
        return DMAP.model_validate_json(raw)

    # --- Merkle Trees ---

    def save_merkle_tree(self, course_id: str, data_json: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO merkle_trees (course_id, data_json) VALUES (?, ?)",
            (course_id, data_json),
        )
        self._conn.commit()

    def get_merkle_tree(self, course_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT data_json FROM merkle_trees WHERE course_id = ?", (course_id,)
        ).fetchone()
        return row["data_json"] if row else None

    def get_merkle_tree_obj(self, course_id: str) -> MerkleTree | None:
        raw = self.get_merkle_tree(course_id)
        if raw is None:
            return None
        return MerkleTree.model_validate_json(raw)

    # --- KC (Knowledge Components) ---

    def save_kc(self, kc: KC) -> None:
        """保存一条 KC。KC.id 必须是 uuid5 确定的。"""
        data_json = kc.model_dump_json()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO wiki_kcs
                (kc_id, course_id, chapter_id, name, layer, bloom_level,
                 data_json, valid_at, invalid_at, version, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                kc.id,
                kc.course_id,
                kc.chapter_id,
                kc.name,
                kc.layer,
                kc.bloom_level,
                data_json,
                kc.valid_at,
                kc.invalid_at,
                kc.version,
                kc.content_hash,
            ),
        )
        self._conn.commit()

    def get_kc(self, kc_id: str) -> KC | None:
        row = self._conn.execute(
            "SELECT data_json FROM wiki_kcs WHERE kc_id = ?", (kc_id,)
        ).fetchone()
        if row is None:
            return None
        return KC.model_validate_json(row["data_json"])

    def get_kcs_by_course(
        self, course_id: str, include_invalid: bool = False
    ) -> list[KC]:
        if include_invalid:
            rows = self._conn.execute(
                "SELECT data_json FROM wiki_kcs WHERE course_id = ? ORDER BY kc_id",
                (course_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT data_json FROM wiki_kcs WHERE course_id = ? AND invalid_at IS NULL ORDER BY kc_id",
                (course_id,),
            ).fetchall()
        return [KC.model_validate_json(r["data_json"]) for r in rows]

    def get_kcs_by_chapter(
        self,
        course_id: str,
        chapter_id: str,
        include_invalid: bool = False,
    ) -> list[KC]:
        if include_invalid:
            rows = self._conn.execute(
                "SELECT data_json FROM wiki_kcs WHERE course_id = ? AND chapter_id = ? ORDER BY kc_id",
                (course_id, chapter_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT data_json FROM wiki_kcs WHERE course_id = ? AND chapter_id = ? AND invalid_at IS NULL ORDER BY kc_id",
                (course_id, chapter_id),
            ).fetchall()
        return [KC.model_validate_json(r["data_json"]) for r in rows]

    def invalidate_kc(self, kc_id: str) -> None:
        """把一条 KC 标为 invalid,设 invalid_at = now(UTC ISO 字符串)。"""
        self._conn.execute(
            "UPDATE wiki_kcs SET invalid_at = datetime('now') WHERE kc_id = ? AND invalid_at IS NULL",
            (kc_id,),
        )
        self._conn.commit()

    def search_kcs_by_name(
        self,
        course_id: str,
        query: str,
        include_invalid: bool = False,
    ) -> list[KC]:
        like = f"%{query}%"
        if include_invalid:
            rows = self._conn.execute(
                "SELECT data_json FROM wiki_kcs WHERE course_id = ? AND name LIKE ? ORDER BY kc_id",
                (course_id, like),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT data_json FROM wiki_kcs WHERE course_id = ? AND name LIKE ? AND invalid_at IS NULL ORDER BY kc_id",
                (course_id, like),
            ).fetchall()
        return [KC.model_validate_json(r["data_json"]) for r in rows]

    # --- Chapter Wiki ---

    def save_chapter_wiki(self, cw: ChapterWiki) -> None:
        data_json = cw.model_dump_json()
        self._conn.execute(
            "INSERT OR REPLACE INTO wiki_chapters (chapter_id, course_id, data_json) VALUES (?, ?, ?)",
            (cw.chapter_id, cw.course_id, data_json),
        )
        self._conn.commit()

    def get_chapter_wiki(self, chapter_id: str) -> ChapterWiki | None:
        row = self._conn.execute(
            "SELECT data_json FROM wiki_chapters WHERE chapter_id = ?", (chapter_id,)
        ).fetchone()
        if row is None:
            return None
        return ChapterWiki.model_validate_json(row["data_json"])

    def get_chapter_wikis_by_course(self, course_id: str) -> list[ChapterWiki]:
        rows = self._conn.execute(
            "SELECT data_json FROM wiki_chapters WHERE course_id = ? ORDER BY chapter_id",
            (course_id,),
        ).fetchall()
        return [ChapterWiki.model_validate_json(r["data_json"]) for r in rows]

    # --- Course Index ---

    def save_course_index(self, course_id: str, content: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO course_indices (course_id, content) VALUES (?, ?)",
            (course_id, content),
        )
        self._conn.commit()

    def get_course_index(self, course_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT content FROM course_indices WHERE course_id = ?", (course_id,)
        ).fetchone()
        return row["content"] if row else None

    # --- Notes ---

    def create_note(self, note: Note) -> Note:
        import json
        citations_json = json.dumps([c.model_dump() for c in note.source_citations], ensure_ascii=False)
        self._conn.execute(
            """INSERT INTO notes (id, course_id, title, content, source_citations_json)
               VALUES (?, ?, ?, ?, ?)""",
            (note.id, note.course_id, note.title, note.content, citations_json),
        )
        self._conn.commit()
        row = self._conn.execute("SELECT * FROM notes WHERE id = ?", (note.id,)).fetchone()
        return self._row_to_note(row)

    def get_note(self, course_id: str, note_id: str) -> Note | None:
        row = self._conn.execute(
            "SELECT * FROM notes WHERE id = ? AND course_id = ?", (note_id, course_id)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_note(row)

    def get_notes_by_course(self, course_id: str) -> list[Note]:
        rows = self._conn.execute(
            "SELECT * FROM notes WHERE course_id = ? ORDER BY created_at DESC", (course_id,)
        ).fetchall()
        return [self._row_to_note(r) for r in rows]

    def update_note(self, course_id: str, note_id: str, **kwargs) -> Note | None:
        existing = self.get_note(course_id, note_id)
        if existing is None:
            return None
        import json
        sets = []
        values = []
        if "title" in kwargs and kwargs["title"] is not None:
            sets.append("title = ?")
            values.append(kwargs["title"])
        if "content" in kwargs and kwargs["content"] is not None:
            sets.append("content = ?")
            values.append(kwargs["content"])
        if "source_citations" in kwargs and kwargs["source_citations"] is not None:
            citations = kwargs["source_citations"]
            citations_json = json.dumps([c.model_dump() for c in citations], ensure_ascii=False) if citations else "[]"
            sets.append("source_citations_json = ?")
            values.append(citations_json)
        if not sets:
            return existing
        sets.append("updated_at = datetime('now')")
        values.extend([note_id, course_id])
        self._conn.execute(
            f"UPDATE notes SET {', '.join(sets)} WHERE id = ? AND course_id = ?",
            values,
        )
        self._conn.commit()
        row = self._conn.execute("SELECT * FROM notes WHERE id = ? AND course_id = ?", (note_id, course_id)).fetchone()
        return self._row_to_note(row) if row else None

    def delete_note(self, course_id: str, note_id: str) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM notes WHERE id = ? AND course_id = ?", (note_id, course_id)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_note(self, row: sqlite3.Row) -> Note:
        import json
        citations_data = json.loads(row["source_citations_json"] or "[]")
        citations = [Citation(**c) for c in citations_data]
        return Note(
            id=row["id"],
            course_id=row["course_id"],
            title=row["title"],
            content=row["content"],
            source_citations=citations,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ---- extracted_assets ----

    @staticmethod
    def _asset_bbox_value(asset: dict, field: str) -> float | None:
        """Read a bounding-box coordinate from a Pydantic model dump or object."""
        bbox = asset.get("bounding_box")
        if bbox is None:
            return None
        if isinstance(bbox, dict):
            return bbox.get(field)
        return getattr(bbox, field, None)

    def _insert_extracted_assets(
        self,
        assets: Sequence[dict],
        course_id: str,
        material_id: str,
        document_id: str,
    ) -> None:
        for asset in assets:
            self._conn.execute(
                """INSERT OR REPLACE INTO extracted_assets
                   (asset_id, document_id, course_id, material_id, element_type,
                    sequential_label, page_number, closest_heading, storage_path,
                    alt_text, x0, y0, x1, y1)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    asset.get("element_id", ""),
                    document_id,
                    course_id,
                    material_id,
                    asset.get("element_type", ""),
                    asset.get("sequential_label", ""),
                    asset.get("page_number", 1),
                    asset.get("source_chapter", ""),
                    asset.get("storage_path") or "",
                    asset.get("alt_text") or "",
                    self._asset_bbox_value(asset, "x0"),
                    self._asset_bbox_value(asset, "y0"),
                    self._asset_bbox_value(asset, "x1"),
                    self._asset_bbox_value(asset, "y1"),
                ),
            )

    def save_extracted_assets(
        self,
        assets: list[dict],
        course_id: str,
        material_id: str,
        document_id: str,
    ) -> None:
        self._insert_extracted_assets(assets, course_id, material_id, document_id)
        self._conn.commit()

    def replace_extracted_assets(
        self,
        assets: Sequence[dict],
        course_id: str,
        material_id: str,
        document_id: str,
    ) -> None:
        """Replace all parser assets for one current material input.

        V2 treats assets as material-revision-local derived data.  This method
        intentionally removes prior rows even when the fresh parser produced
        no assets, so a retry or reparsed revision cannot retain stale figures.
        Callers that publish V2 evidence invoke it inside the material revision
        fence.
        """
        self._conn.execute(
            "DELETE FROM extracted_assets WHERE course_id = ? AND material_id = ?",
            (course_id, material_id),
        )
        self._insert_extracted_assets(assets, course_id, material_id, document_id)
        self._conn.commit()

    def get_extracted_assets(self, course_id: str, material_id: str | None = None) -> list[dict]:
        if material_id:
            rows = self._conn.execute(
                "SELECT * FROM extracted_assets WHERE course_id = ? AND material_id = ? ORDER BY page_number, sequential_label",
                (course_id, material_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM extracted_assets WHERE course_id = ? ORDER BY page_number, sequential_label",
                (course_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_extracted_assets(self, material_id: str) -> None:
        self._conn.execute("DELETE FROM extracted_assets WHERE material_id = ?", (material_id,))
        self._conn.commit()
