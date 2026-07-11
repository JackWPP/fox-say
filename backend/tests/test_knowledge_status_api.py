"""V2-C1 evidence status and current fragment preview API tests."""

from __future__ import annotations

from httpx import AsyncClient

from app.main import app
from app.schemas.foxsay import Material
from app.services.knowledge_jobs import enqueue_material_index_job
from app.services.source_fragments import build_source_fragments


async def _create_course(client: AsyncClient, title: str) -> str:
    response = await client.post("/courses", json={"title": title})
    assert response.status_code == 200
    return response.json()["id"]


async def _upload_markdown(client: AsyncClient, course_id: str, filename: str) -> dict:
    response = await client.post(
        f"/courses/{course_id}/materials",
        files={
            "file": (
                filename,
                b"# Vector space\n\nA vector space is closed under addition.",
                "text/markdown",
            )
        },
        data={"kind": "text_note"},
    )
    assert response.status_code == 200
    return response.json()


def _complete_current_index(course_id: str, material: dict, *, markdown: str) -> list:
    store = app.state.store
    jobs = store.list_knowledge_jobs(course_id, material_id=material["id"])
    assert len(jobs) == 1
    job = jobs[0]
    claimed = store.claim_next_knowledge_job("status-test-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == job.job_id
    fragments = build_source_fragments(
        markdown,
        course_id=course_id,
        material_id=material["id"],
        material_revision=material["revision"],
        parser_name="status-test-parser",
    )
    store.replace_source_fragments(
        course_id,
        material["id"],
        material["revision"],
        fragments,
    )
    assert store.update_material_status_if_revision(
        course_id,
        material["id"],
        material["revision"],
        "ready",
    )
    store.complete_knowledge_job(course_id, job.job_id, "status-test-worker")
    return fragments


def _fail_current_index(course_id: str, material: dict, *, retryable: bool) -> None:
    store = app.state.store
    job = store.list_knowledge_jobs(course_id, material_id=material["id"])[0]
    claimed = store.claim_next_knowledge_job("status-test-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == job.job_id
    store.fail_knowledge_job(
        course_id,
        job.job_id,
        "status-test-worker",
        "synthetic index failure",
        retryable=retryable,
        error_code="synthetic_index_failure",
    )
    assert store.update_material_status_if_revision(
        course_id,
        material["id"],
        material["revision"],
        "failed",
    )


async def test_knowledge_status_distinguishes_source_ready_from_course_ready(
    client: AsyncClient,
) -> None:
    course_id = await _create_course(client, "线性代数状态")

    empty = await client.get(f"/courses/{course_id}/knowledge-status")
    assert empty.status_code == 200
    assert empty.json() == {
        "course_id": course_id,
        "status": "empty",
        "source_status": "empty",
        "projection_status": "not_started",
        "source_revision": None,
        "knowledge_revision": None,
        "compiled_from_source_revision": None,
        "coverage": {
            "total_materials": 0,
            "ready_materials": 0,
            "processing_materials": 0,
            "retryable_materials": 0,
            "failed_materials": 0,
            "fragment_count": 0,
        },
        "materials": [],
    }

    material = await _upload_markdown(client, course_id, "vectors.md")
    processing = await client.get(f"/courses/{course_id}/knowledge-status")
    assert processing.status_code == 200
    assert processing.json()["status"] == "processing"
    assert processing.json()["materials"][0]["job_status"] == "queued"

    _complete_current_index(
        course_id,
        material,
        markdown="<!-- PAGE_START 2 -->\n# 向量空间\n\n向量空间对加法和数乘封闭。\n<!-- PAGE_END 2 -->",
    )
    source_ready = await client.get(f"/courses/{course_id}/knowledge-status")
    repeated = await client.get(f"/courses/{course_id}/knowledge-status")
    assert source_ready.status_code == 200
    payload = source_ready.json()
    assert payload["status"] == "partial"
    assert payload["source_status"] == "ready"
    assert payload["projection_status"] == "not_started"
    assert payload["coverage"] == {
        "total_materials": 1,
        "ready_materials": 1,
        "processing_materials": 0,
        "retryable_materials": 0,
        "failed_materials": 0,
        "fragment_count": 1,
    }
    assert payload["materials"][0]["status"] == "ready"
    assert payload["source_revision"].startswith("src_")
    assert repeated.json()["source_revision"] == payload["source_revision"]


async def test_knowledge_status_uses_only_current_revision_and_exposes_retryable_failure(
    client: AsyncClient,
) -> None:
    course_id = await _create_course(client, "线性代数增量")
    ready_material = await _upload_markdown(client, course_id, "basis.md")
    _complete_current_index(
        course_id,
        ready_material,
        markdown="# 基\n\n基是线性无关的生成集。",
    )
    retryable_material = await _upload_markdown(client, course_id, "eigenvalue.md")
    _fail_current_index(course_id, retryable_material, retryable=True)

    partial = await client.get(f"/courses/{course_id}/knowledge-status")
    assert partial.status_code == 200
    payload = partial.json()
    assert payload["status"] == "partial"
    assert payload["source_status"] == "partial"
    assert payload["coverage"]["ready_materials"] == 1
    assert payload["coverage"]["retryable_materials"] == 1
    retryable = next(
        item for item in payload["materials"] if item["material_id"] == retryable_material["id"]
    )
    assert retryable["status"] == "retryable"
    assert retryable["error_code"] == "synthetic_index_failure"

    old_revision = payload["source_revision"]
    advanced = app.state.store.advance_material_revision(
        course_id,
        ready_material["id"],
        "replacement-content-hash",
    )
    assert advanced is not None and advanced.revision == ready_material["revision"] + 1
    stale_source = await client.get(f"/courses/{course_id}/knowledge-status")
    assert stale_source.status_code == 200
    updated = stale_source.json()
    assert updated["source_revision"] != old_revision
    assert updated["coverage"]["ready_materials"] == 0
    assert updated["coverage"]["fragment_count"] == 0


async def test_knowledge_status_exposes_terminal_current_job_failure(
    client: AsyncClient,
) -> None:
    course_id = await _create_course(client, "线性代数终态失败")
    ready_material = await _upload_markdown(client, course_id, "vectors.md")
    _complete_current_index(
        course_id,
        ready_material,
        markdown="# 向量空间\n\n向量空间对加法封闭。",
    )
    failed_material = await _upload_markdown(client, course_id, "bad-source.md")
    _fail_current_index(course_id, failed_material, retryable=False)

    response = await client.get(f"/courses/{course_id}/knowledge-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["source_status"] == "partial"
    assert payload["coverage"]["ready_materials"] == 1
    assert payload["coverage"]["failed_materials"] == 1
    failed = next(
        item for item in payload["materials"] if item["material_id"] == failed_material["id"]
    )
    assert failed["status"] == "failed"
    assert failed["error_code"] == "synthetic_index_failure"


async def test_knowledge_status_does_not_trust_legacy_course_or_orphan_evidence(
    client: AsyncClient,
) -> None:
    course_id = await _create_course(client, "旧课程")
    material = await _upload_markdown(client, course_id, "legacy.md")
    store = app.state.store
    fragments = build_source_fragments(
        "# 旧材料\n\n旧材料看起来像证据。",
        course_id=course_id,
        material_id=material["id"],
        material_revision=material["revision"],
        parser_name="status-test-parser",
    )
    store.replace_source_fragments(
        course_id,
        material["id"],
        material["revision"],
        fragments,
    )
    assert store.update_material_status_if_revision(
        course_id,
        material["id"],
        material["revision"],
        "ready",
    )

    # The durable index job is still queued, so source fragments alone cannot
    # make the course look ready.
    response = await client.get(f"/courses/{course_id}/knowledge-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processing"
    assert payload["coverage"]["ready_materials"] == 0
    assert payload["materials"][0]["status"] == "processing"
    preview = await client.get(
        f"/courses/{course_id}/source-fragments/{fragments[0].fragment_id}"
    )
    assert preview.status_code == 404


async def test_knowledge_status_requires_legacy_material_reindex(client: AsyncClient) -> None:
    course_id = await _create_course(client, "legacy material")
    app.state.store.create_material(
        Material(
            id="legacy-material",
            course_id=course_id,
            filename="legacy.txt",
            kind="text_note",
            status="ready",
            revision=0,
            content_hash="",
        )
    )
    enqueue_material_index_job(
        app.state.store,
        course_id=course_id,
        material_id="legacy-material",
        revision=0,
    )
    fragments = _complete_current_index(
        course_id,
        {"id": "legacy-material", "revision": 0},
        markdown="# 旧材料\n\n即使索引任务成功，缺 content hash 的材料也不能成为 V2 证据。",
    )

    response = await client.get(f"/courses/{course_id}/knowledge-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["source_revision"] is None
    assert payload["materials"][0]["status"] == "missing_evidence"
    assert payload["materials"][0]["error_code"] == "legacy_material_requires_reindex"
    preview = await client.get(
        f"/courses/{course_id}/source-fragments/{fragments[0].fragment_id}"
    )
    assert preview.status_code == 404
    assert app.state.store.list_current_ready_source_fragments(course_id) == []


async def test_current_source_fragment_preview_is_scoped_and_revision_safe(
    client: AsyncClient,
) -> None:
    course_a = await _create_course(client, "线性代数 A")
    material_a = await _upload_markdown(client, course_a, "eigenvalue.md")
    fragments_a = _complete_current_index(
        course_a,
        material_a,
        markdown="<!-- PAGE_START 7 -->\n# 特征值\n\n若 Av = λv，则 λ 是特征值。\n<!-- PAGE_END 7 -->",
    )
    fragment = fragments_a[0]

    canonical = app.state.store.list_current_ready_source_fragments(
        course_a,
        fragment_ids=[fragment.fragment_id, "sf_unknown"],
        material_ids=[material_a["id"]],
    )
    assert [item.fragment_id for item in canonical] == [fragment.fragment_id]

    preview = await client.get(f"/courses/{course_a}/source-fragments/{fragment.fragment_id}")
    assert preview.status_code == 200
    assert preview.json() == {
        "course_id": course_a,
        "material_id": material_a["id"],
        "material_revision": material_a["revision"],
        "fragment_id": fragment.fragment_id,
        "file_name": "eigenvalue.md",
        "text": fragment.text,
        "locator": fragment.locator(),
        "heading_path": ["特征值"],
        "page_start": 7,
        "page_end": 7,
        "slide_start": None,
        "slide_end": None,
        "char_start": fragment.char_start,
        "char_end": fragment.char_end,
        "kind": "paragraph",
    }

    course_b = await _create_course(client, "线性代数 B")
    cross_course = await client.get(
        f"/courses/{course_b}/source-fragments/{fragment.fragment_id}"
    )
    assert cross_course.status_code == 404

    advanced = app.state.store.advance_material_revision(
        course_a,
        material_a["id"],
        "new-eigenvalue-content-hash",
    )
    assert advanced is not None
    assert app.state.store.list_current_ready_source_fragments(
        course_a,
        fragment_ids=[fragment.fragment_id],
    ) == []
    old_revision = await client.get(
        f"/courses/{course_a}/source-fragments/{fragment.fragment_id}",
        params={"dmap_id": "legacy", "chunk_index": 0},
    )
    assert old_revision.status_code == 404


async def test_knowledge_status_returns_404_for_unknown_course(client: AsyncClient) -> None:
    response = await client.get("/courses/not-a-course/knowledge-status")
    assert response.status_code == 404
