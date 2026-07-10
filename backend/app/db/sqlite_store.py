import json
import sqlite3
import threading
from collections.abc import Sequence
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
from app.schemas.evidence import SourceFragment

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
    finished_at TEXT,
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (material_id) REFERENCES materials(id),
    CHECK (job_type IN ('index_material', 'compile_course')),
    CHECK (scope IN ('material', 'course')),
    CHECK (status IN ('queued', 'running', 'succeeded', 'retryable', 'failed')),
    CHECK (revision >= 0),
    CHECK (attempt >= 0),
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
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._migrate()

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
        ]
        for sql in migrations:
            try:
                self._conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists
        self._conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE title = ?",
            ("新对话", "New Chat"),
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

    def enqueue_knowledge_job(self, job: KnowledgeJobCreate) -> KnowledgeJob:
        """Insert a job once per stable idempotency key.

        A reused key is valid only for the exact same course-scoped immutable
        identity.  This prevents an accidental caller-side key collision from
        returning another course's job.
        """
        if self.get_course(job.course_id) is None:
            raise ValueError(f"Cannot enqueue knowledge job: course {job.course_id!r} not found")
        if job.material_id is not None and self.get_material(job.course_id, job.material_id) is None:
            raise ValueError(
                "Cannot enqueue material knowledge job: material does not belong to course"
            )

        with self._knowledge_job_lock:
            self._conn.execute(
                """
                INSERT INTO knowledge_jobs
                    (job_id, course_id, material_id, job_type, revision, scope,
                     status, attempt, idempotency_key, token_budget)
                VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?)
                ON CONFLICT(idempotency_key) DO NOTHING
                """,
                (
                    job.job_id,
                    job.course_id,
                    job.material_id,
                    job.job_type,
                    job.revision,
                    job.scope,
                    job.idempotency_key,
                    job.token_budget,
                ),
            )
            self._conn.commit()
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
        )
        requested_identity = (
            job.course_id,
            job.material_id,
            job.job_type,
            job.revision,
            job.scope,
        )
        if immutable_identity != requested_identity:
            raise ValueError("Knowledge job idempotency key is already bound to another job identity")
        return persisted

    def get_knowledge_job(self, course_id: str, job_id: str) -> KnowledgeJob | None:
        row = self._conn.execute(
            "SELECT * FROM knowledge_jobs WHERE job_id = ? AND course_id = ?",
            (job_id, course_id),
        ).fetchone()
        return self._row_to_knowledge_job(row) if row is not None else None

    def list_knowledge_jobs(
        self, course_id: str, status: str | None = None
    ) -> list[KnowledgeJob]:
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM knowledge_jobs WHERE course_id = ? ORDER BY created_at, job_id",
                (course_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM knowledge_jobs WHERE course_id = ? AND status = ? ORDER BY created_at, job_id",
                (course_id, status),
            ).fetchall()
        return [self._row_to_knowledge_job(row) for row in rows]

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
                row = self._conn.execute(
                    """
                    SELECT job_id FROM knowledge_jobs
                    WHERE status = 'queued'
                       OR (status = 'running'
                           AND lease_expires_at IS NOT NULL
                           AND lease_expires_at <= datetime('now'))
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
        next_status = "retryable" if retryable else "failed"
        with self._knowledge_job_lock:
            updated = self._conn.execute(
                """
                UPDATE knowledge_jobs
                SET status = ?,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_code = ?,
                    error_detail = ?,
                    error_at = datetime('now'),
                    finished_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE job_id = ? AND course_id = ? AND status = 'running' AND lease_owner = ?
                """,
                (next_status, error_code, error_detail, job_id, course_id, lease_owner),
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

    def touch_chat_session(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE chat_sessions SET updated_at = datetime('now') WHERE id = ?",
            (session_id,),
        )
        self._conn.commit()

    def delete_chat_session(self, session_id: str) -> None:
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
    ) -> None:
        self._conn.execute(
            "INSERT INTO chat_messages (id, course_id, session_id, role, content, citations_json, confidence_status, refusal_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (msg_id, course_id, session_id, role, content, citations_json, confidence_status, refusal_reason),
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

    def save_extracted_assets(
        self,
        assets: list[dict],
        course_id: str,
        material_id: str,
        document_id: str,
    ) -> None:
        for asset in assets:
            bbox = asset.get("bounding_box")
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
                    asset.get("storage_path", ""),
                    asset.get("alt_text", ""),
                    bbox.x0 if bbox else None,
                    bbox.y0 if bbox else None,
                    bbox.x1 if bbox else None,
                    bbox.y1 if bbox else None,
                ),
            )
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
