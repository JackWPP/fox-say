"""Material revision persistence and stale-write guards."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import Course, Material


def _create_course(store: SqliteStore, course_id: str) -> None:
    store.create_course(Course(id=course_id, title=course_id, status="empty"))


def test_legacy_materials_migrate_to_revision_zero(tmp_path: Path) -> None:
    """A pre-revision row must remain visibly legacy after migration."""
    db_path = tmp_path / "legacy-materials.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE courses (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'empty',
            teacher TEXT,
            exam_date TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE materials (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'processing',
            file_path TEXT,
            degraded INTEGER NOT NULL DEFAULT 0,
            parsed_text TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (course_id) REFERENCES courses(id)
        );
        INSERT INTO courses (id, title, status) VALUES ('legacy-course', 'Legacy course', 'empty');
        INSERT INTO materials (id, course_id, filename, kind, status)
        VALUES ('legacy-material', 'legacy-course', 'legacy.txt', 'text_note', 'ready');
        """
    )
    connection.commit()
    connection.close()

    store = SqliteStore(db_path)
    try:
        material = store.get_material("legacy-course", "legacy-material")

        assert material is not None
        assert material.revision == 0
        assert material.content_hash == ""
    finally:
        store.close()


def test_material_revision_mapping_and_stale_write_guards(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "material-revisions.db")
    try:
        _create_course(store, "course-a")
        _create_course(store, "course-b")
        created = store.create_material(
            Material(
                id="material-a",
                course_id="course-a",
                filename="linear-algebra.md",
                kind="text_note",
                status="processing",
                content_hash="source-v1",
            )
        )

        # New Material defaults to revision 1, and every read path retains its
        # explicit revision/hash rather than falling back to a filename.
        assert created.revision == 1
        assert store.get_material("course-a", "material-a") == created
        assert store.get_all_materials("course-a") == [created]

        updated = store.update_material(
            "course-a",
            "material-a",
            created.model_copy(update={"filename": "chapter-1.md", "degraded": True}),
        )
        assert updated is not None
        assert updated.filename == "chapter-1.md"
        assert updated.degraded is True
        assert updated.revision == 1
        assert updated.content_hash == "source-v1"

        assert store.save_parsed_text_if_revision(
            "course-a", "material-a", 1, "version one parsed text"
        )
        assert store.update_material_status_if_revision(
            "course-a", "material-a", 1, "ready", degraded=False
        )

        advanced = store.advance_material_revision(
            "course-a", "material-a", "source-v2"
        )
        assert advanced is not None
        assert advanced.revision == 2
        assert advanced.content_hash == "source-v2"
        assert advanced.status == "processing"
        assert advanced.degraded is False
        assert store.get_parsed_text("course-a", "material-a") is None

        # A late result from revision 1 cannot overwrite the current source.
        assert not store.save_parsed_text_if_revision(
            "course-a", "material-a", 1, "stale parsed text"
        )
        assert not store.update_material_status_if_revision(
            "course-a", "material-a", 1, "failed", degraded=True
        )
        assert store.get_material("course-a", "material-a").status == "processing"
        assert store.get_parsed_text("course-a", "material-a") is None

        # The current revision succeeds, while the same material ID cannot be
        # written through a different course scope.
        assert store.save_parsed_text_if_revision(
            "course-a", "material-a", 2, "version two parsed text"
        )
        assert not store.save_parsed_text_if_revision(
            "course-b", "material-a", 2, "cross-course text"
        )
        assert not store.update_material_status_if_revision(
            "course-b", "material-a", 2, "failed", degraded=True
        )
        assert store.get_parsed_text("course-a", "material-a") == "version two parsed text"
        assert store.get_material("course-a", "material-a").status == "processing"
    finally:
        store.close()
