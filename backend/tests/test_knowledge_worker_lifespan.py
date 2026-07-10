"""FastAPI owns exactly one managed durable worker during its lifespan."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.schemas.foxsay import Course, Material
from app.services.knowledge_jobs import enqueue_material_index_job


async def test_lifespan_drains_persisted_job_with_controlled_worker(
    monkeypatch, tmp_path: Path
) -> None:
    import app.main as main_module

    handled = asyncio.Event()

    async def handle(_job) -> None:
        handled.set()

    monkeypatch.setattr(
        main_module,
        "build_material_index_handlers",
        lambda _store: {"index_material": handle},
    )
    monkeypatch.setattr(main_module.settings, "sqlite_path", str(tmp_path / "lifespan.db"))
    monkeypatch.setattr(main_module.settings, "knowledge_worker_lease_seconds", 5)
    monkeypatch.setattr(main_module.settings, "knowledge_worker_poll_interval_seconds", 0.01)

    async with main_module.lifespan(main_module.app):
        store = main_module.app.state.store
        store.create_course(Course(id="course-a", title="线性代数", status="empty"))
        store.create_material(
            Material(
                id="material-a",
                course_id="course-a",
                filename="vectors.md",
                kind="text_note",
                status="processing",
            ),
            file_path="vectors.md",
        )
        job = enqueue_material_index_job(
            store, course_id="course-a", material_id="material-a", revision=1
        )

        await asyncio.wait_for(handled.wait(), timeout=1)
        for _ in range(100):
            persisted = store.get_knowledge_job("course-a", job.job_id)
            if persisted is not None and persisted.status == "succeeded":
                break
            await asyncio.sleep(0.01)
        else:  # pragma: no cover - timeout diagnostic
            raise AssertionError("lifespan worker did not complete the durable job")
