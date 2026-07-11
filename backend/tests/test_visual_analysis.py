"""Narrow V2-E queue/guard regression: no external VLM calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.evidence import SourceFragment
from app.schemas.foxsay import Course, Material
from app.services.knowledge_jobs import enqueue_material_index_job
from app.services.knowledge_worker import KnowledgeJobWorker
from app.services.visual_analysis import VisualAnalysis


@pytest.mark.asyncio
async def test_visual_job_requires_explicit_current_asset_and_disabled_guard(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "visual.db")
    try:
        store.create_course(Course(id="linear", title="线性代数", status="empty"))
        store.create_material(Material(
            id="m1", course_id="linear", filename="notes.md", kind="text_note",
            status="ready", revision=1, content_hash="h1",
        ))
        store.replace_source_fragments("linear", "m1", 1, [SourceFragment(
            fragment_id="f1", course_id="linear", material_id="m1", material_revision=1,
            ordinal=0, text="矩阵 A 的秩。", heading_path=["矩阵"], char_start=0, char_end=7,
            kind="paragraph", parser_name="test", content_hash="h1",
        )])
        index = enqueue_material_index_job(store, course_id="linear", material_id="m1", revision=1)
        claimed_index = store.claim_next_knowledge_job("index", lease_seconds=60)
        assert claimed_index is not None and claimed_index.job_id == index.job_id
        store.complete_knowledge_job("linear", index.job_id, "index")
        store.replace_extracted_assets([
            {"element_id": "figure-1", "element_type": "Figure", "sequential_label": "图1",
             "page_number": 1, "source_chapter": "矩阵", "storage_path": "images/figure-1.png",
             "alt_text": ""},
        ], "linear", "m1", "doc1")

        job = store.enqueue_visual_analysis_job(
            course_id="linear",
            asset_requests=[{"asset_id": "figure-1", "reason_code": "unreadable_diagram"}],
            token_budget=12000,
        )
        assert job.job_type == "visual_analysis"
        assert len(store.get_visual_analysis_requests("linear", job.job_id)) == 1

        worker = KnowledgeJobWorker(
            store, worker_id="visual", handlers={"visual_analysis": VisualAnalysis(store, enabled=False)}
        )
        completed = await worker.run_once()
        assert completed is not None and completed.job_id == job.job_id
        failed = store.get_knowledge_job("linear", job.job_id)
        assert failed is not None and failed.status == "failed"
        assert failed.error_code == "visual_analysis_disabled"
        assert store.list_model_call_audits("linear", job_id=job.job_id) == []
    finally:
        store.close()
