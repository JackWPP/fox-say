"""HTTP material uploads enqueue durable V2 jobs instead of in-memory work."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.main import app
from app.services.source_fragments import build_source_fragments


async def _create_course(client: AsyncClient, title: str) -> str:
    response = await client.post("/courses", json={"title": title})
    assert response.status_code == 200
    return response.json()["id"]


@pytest.mark.asyncio
async def test_upload_persists_index_job_and_progress_snapshot(client: AsyncClient) -> None:
    course_id = await _create_course(client, "线性代数 V2")

    response = await client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("vector-space.md", b"# Vector space\n\nClosed under addition.", "text/markdown")},
        data={"kind": "text_note"},
    )
    assert response.status_code == 200
    material = response.json()

    store = app.state.store
    jobs = store.list_knowledge_jobs(course_id, material_id=material["id"])
    assert len(jobs) == 1
    assert jobs[0].job_type == "index_material"
    assert jobs[0].status == "queued"
    assert jobs[0].revision == material["revision"] == 1
    assert material["content_hash"]

    progress = await client.get(f"/courses/{course_id}/materials/{material['id']}/progress")
    assert progress.status_code == 200
    assert progress.json()["current_step"] == "index_material"
    assert progress.json()["steps"][0]["job_id"] == jobs[0].job_id


@pytest.mark.asyncio
async def test_retry_requeues_failed_current_revision_job(client: AsyncClient) -> None:
    course_id = await _create_course(client, "线性代数重试")
    response = await client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("eigenvalue.md", b"# Eigenvalue", "text/markdown")},
        data={"kind": "text_note"},
    )
    assert response.status_code == 200
    material = response.json()
    store = app.state.store
    job = store.list_knowledge_jobs(course_id, material_id=material["id"])[0]
    claimed = store.claim_next_knowledge_job("test-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == job.job_id
    store.fail_knowledge_job(
        course_id,
        job.job_id,
        "test-worker",
        "synthetic parser error",
        retryable=False,
        error_code="synthetic_error",
    )
    store.update_material_status_if_revision(
        course_id, material["id"], material["revision"], "failed"
    )

    retried = await client.post(f"/courses/{course_id}/materials/{material['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "processing"
    requeued = store.get_knowledge_job(course_id, job.job_id)
    assert requeued is not None and requeued.status == "queued"


@pytest.mark.asyncio
async def test_retry_limit_is_a_visible_conflict_not_an_internal_error(client: AsyncClient) -> None:
    course_id = await _create_course(client, "线性代数重试上限")
    response = await client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("rank.md", b"# Rank", "text/markdown")},
        data={"kind": "text_note"},
    )
    assert response.status_code == 200
    material = response.json()
    store = app.state.store
    job = store.list_knowledge_jobs(course_id, material_id=material["id"])[0]
    claimed = store.claim_next_knowledge_job("test-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == job.job_id
    store.fail_knowledge_job(
        course_id,
        job.job_id,
        "test-worker",
        "synthetic parser error",
        retryable=False,
        error_code="synthetic_error",
    )
    store._conn.execute(
        "UPDATE knowledge_jobs SET max_attempts = 1 WHERE job_id = ?", (job.job_id,)
    )
    store._conn.commit()
    store.update_material_status_if_revision(
        course_id, material["id"], material["revision"], "failed"
    )

    retried = await client.post(f"/courses/{course_id}/materials/{material['id']}/retry")

    assert retried.status_code == 409
    assert "retry limit" in retried.json()["detail"]


@pytest.mark.asyncio
async def test_source_preview_uses_current_fragment_id_not_legacy_locator(
    client: AsyncClient,
) -> None:
    course_id = await _create_course(client, "线性代数引用预览")
    response = await client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("basis.md", b"# Basis", "text/markdown")},
        data={"kind": "text_note"},
    )
    assert response.status_code == 200
    material = response.json()
    fragments = build_source_fragments(
        "<!-- PAGE_START 1 -->\n# 基\n\n基是向量空间的一组线性无关生成元。\n<!-- PAGE_END 1 -->",
        course_id=course_id,
        material_id=material["id"],
        material_revision=material["revision"],
        parser_name="test-parser",
    )
    app.state.store.replace_source_fragments(
        course_id, material["id"], material["revision"], fragments
    )

    preview = await client.get(
        f"/courses/{course_id}/materials/{material['id']}/source-preview",
        params={"fragment_id": fragments[0].fragment_id},
    )
    assert preview.status_code == 200
    assert preview.json()["text"] == fragments[0].text
    assert preview.json()["locator"] == fragments[0].locator()


@pytest.mark.asyncio
async def test_source_preview_does_not_fall_back_when_fragment_is_invalid(
    client: AsyncClient,
) -> None:
    course_id = await _create_course(client, "线性代数无效引用")
    response = await client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("matrix.md", b"# Matrix", "text/markdown")},
        data={"kind": "text_note"},
    )
    assert response.status_code == 200
    material = response.json()

    preview = await client.get(
        f"/courses/{course_id}/materials/{material['id']}/source-preview",
        params={"fragment_id": "sf_does_not_exist", "dmap_id": "legacy-fallback"},
    )

    assert preview.status_code == 404
    assert "current revision" in preview.json()["detail"]
