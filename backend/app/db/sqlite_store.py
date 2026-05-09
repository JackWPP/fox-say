import sqlite3
from pathlib import Path
from typing import Any

from app.schemas.foxsay import (
    Course,
    CourseSkeleton,
    Material,
    ReviewPlan,
)

_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "foxsay.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'empty',
    teacher TEXT,
    exam_date TEXT,
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

CREATE TABLE IF NOT EXISTS knowledge_graphs (
    course_id TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT,
    confidence_status TEXT,
    refusal_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
"""


class SqliteStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- Courses ---

    def create_course(self, course: Course) -> Course:
        self._conn.execute(
            "INSERT INTO courses (id, title, status, teacher, exam_date) VALUES (?, ?, ?, ?, ?)",
            (course.id, course.title, course.status, course.teacher, course.exam_date),
        )
        self._conn.commit()
        return course

    def get_course(self, course_id: str) -> Course | None:
        row = self._conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if row is None:
            return None
        return Course(id=row["id"], title=row["title"], status=row["status"], teacher=row["teacher"], exam_date=row["exam_date"])

    def get_all_courses(self) -> list[Course]:
        rows = self._conn.execute("SELECT * FROM courses ORDER BY created_at DESC").fetchall()
        return [Course(id=r["id"], title=r["title"], status=r["status"], teacher=r["teacher"], exam_date=r["exam_date"]) for r in rows]

    def update_course(self, course_id: str, course: Course) -> Course | None:
        existing = self.get_course(course_id)
        if existing is None:
            return None
        self._conn.execute(
            "UPDATE courses SET title=?, status=?, teacher=?, exam_date=? WHERE id=?",
            (course.title, course.status, course.teacher, course.exam_date, course_id),
        )
        self._conn.commit()
        return course

    # --- Materials ---

    def create_material(self, material: Material, file_path: str | None = None, degraded: bool = False) -> Material:
        self._conn.execute(
            "INSERT INTO materials (id, course_id, filename, kind, status, file_path, degraded) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (material.id, material.course_id, material.filename, material.kind, material.status, file_path, int(degraded)),
        )
        self._conn.commit()
        return material

    def get_material(self, course_id: str, material_id: str) -> Material | None:
        row = self._conn.execute(
            "SELECT * FROM materials WHERE id = ? AND course_id = ?", (material_id, course_id)
        ).fetchone()
        if row is None:
            return None
        return Material(id=row["id"], course_id=row["course_id"], filename=row["filename"], kind=row["kind"], status=row["status"])

    def get_all_materials(self, course_id: str) -> list[Material]:
        rows = self._conn.execute(
            "SELECT * FROM materials WHERE course_id = ? ORDER BY created_at DESC", (course_id,)
        ).fetchall()
        return [Material(id=r["id"], course_id=r["course_id"], filename=r["filename"], kind=r["kind"], status=r["status"]) for r in rows]

    def update_material(self, course_id: str, material_id: str, material: Material) -> Material | None:
        existing = self.get_material(course_id, material_id)
        if existing is None:
            return None
        self._conn.execute(
            "UPDATE materials SET filename=?, kind=?, status=? WHERE id=? AND course_id=?",
            (material.filename, material.kind, material.status, material_id, course_id),
        )
        self._conn.commit()
        return material

    def update_material_status(self, course_id: str, material_id: str, status: str, degraded: bool = False) -> None:
        self._conn.execute(
            "UPDATE materials SET status=?, degraded=? WHERE id=? AND course_id=?",
            (status, int(degraded), material_id, course_id),
        )
        self._conn.commit()

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

    # --- Knowledge Graphs ---

    def save_knowledge_graph(self, course_id: str, data_json: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO knowledge_graphs (course_id, data_json, updated_at) VALUES (?, ?, datetime('now'))",
            (course_id, data_json),
        )
        self._conn.commit()

    def load_knowledge_graph(self, course_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT data_json FROM knowledge_graphs WHERE course_id = ?", (course_id,)
        ).fetchone()
        return row["data_json"] if row else None

    # --- Chat Messages ---

    def save_chat_message(
        self,
        msg_id: str,
        course_id: str,
        role: str,
        content: str,
        citations_json: str | None = None,
        confidence_status: str | None = None,
        refusal_reason: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO chat_messages (id, course_id, role, content, citations_json, confidence_status, refusal_reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (msg_id, course_id, role, content, citations_json, confidence_status, refusal_reason),
        )
        self._conn.commit()

    def get_chat_messages(self, course_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM chat_messages WHERE course_id = ? ORDER BY created_at ASC LIMIT ?",
            (course_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
