import hashlib
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.core.config import settings
from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import DMAP, Material, MaterialKind, SourcePreviewResponse
from app.services.dmap import get_dmap_element_by_id, get_dmap_node_by_id
from app.services.knowledge_jobs import enqueue_material_index_job
from app.services.vectorstore import QdrantStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses/{course_id}/materials")

_KIND_MAP: dict[str, MaterialKind] = {
    ".pdf": "pdf",
    ".ppt": "ppt",
    ".pptx": "ppt",
    ".txt": "text_note",
    ".md": "text_note",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".docx": "text_note",
    ".doc": "text_note",
    ".html": "text_note",
}

_VALID_KINDS = {"pdf", "ppt", "text_note", "image"}


def _infer_kind(filename: str) -> MaterialKind:
    _, ext = os.path.splitext(filename)
    return _KIND_MAP.get(ext.lower(), "text_note")


@router.post("", response_model=Material)
async def upload_material(
    course_id: str,
    file: UploadFile,
    kind: str = Form(default=""),
    store: SqliteStore = Depends(get_store),
):
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    material_id = str(uuid.uuid4())
    upload_dir = os.path.join(settings.upload_root, course_id)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{material_id}_{file.filename}")
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    content_hash = hashlib.sha256(content).hexdigest()

    resolved_kind: MaterialKind = kind if kind in _VALID_KINDS else _infer_kind(file.filename or "")

    if resolved_kind not in _VALID_KINDS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Accepted: PDF, TXT, MD. Got kind: {resolved_kind}",
        )

    material = Material(
        id=material_id,
        course_id=course_id,
        filename=file.filename or "unknown",
        kind=resolved_kind,
        status="processing",
        revision=1,
        content_hash=content_hash,
    )
    store.create_material(material, file_path=file_path)
    enqueue_material_index_job(
        store,
        course_id=course_id,
        material_id=material_id,
        revision=material.revision,
    )

    return material


@router.post("/batch", response_model=list[Material])
async def upload_materials_batch(
    course_id: str,
    files: list[UploadFile] = File(...),
    store: SqliteStore = Depends(get_store),
):
    """批量上传材料,单次最多 max_batch_upload 个文件(默认 15)。

    请求只持久化材料和 V2 `index_material` job；受控 worker 会按队列顺序执行。
    不支持的文件类型会被跳过并记录日志(HEC-1),不阻塞其他文件。
    """
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if len(files) > settings.max_batch_upload:
        raise HTTPException(
            status_code=413,
            detail=f"Too many files: {len(files)} > max {settings.max_batch_upload}",
        )

    upload_dir = os.path.join(settings.upload_root, course_id)
    os.makedirs(upload_dir, exist_ok=True)

    created: list[Material] = []
    for file in files:
        material_id = str(uuid.uuid4())
        file_path = os.path.join(upload_dir, f"{material_id}_{file.filename}")
        try:
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as e:
            # 写文件失败:记录日志并跳过(HEC-1,不静默吞错)
            logger.warning("Failed to save uploaded file %s: %s", file.filename, e)
            continue

        content_hash = hashlib.sha256(content).hexdigest()

        resolved_kind = _infer_kind(file.filename or "")
        if resolved_kind not in _VALID_KINDS:
            logger.warning("Skipping unsupported file type: %s (kind=%s)", file.filename, resolved_kind)
            # 删除已写入的文件避免残留
            try:
                os.remove(file_path)
            except OSError:
                pass
            continue

        material = Material(
            id=material_id,
            course_id=course_id,
            filename=file.filename or "unknown",
            kind=resolved_kind,
            status="processing",
            revision=1,
            content_hash=content_hash,
        )
        store.create_material(material, file_path=file_path)
        enqueue_material_index_job(
            store,
            course_id=course_id,
            material_id=material_id,
            revision=material.revision,
        )
        created.append(material)

    if not created:
        raise HTTPException(
            status_code=415,
            detail="No files were accepted (all unsupported or failed to save)",
        )
    return created


@router.get("/{material_id}/status", response_model=Material)
async def get_material_status(course_id: str, material_id: str, store: SqliteStore = Depends(get_store)):
    material = store.get_material(course_id, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    degraded = store.is_material_degraded(course_id, material_id)
    return material.model_copy(update={"degraded": degraded})


@router.get("", response_model=list[Material])
async def list_materials(course_id: str, store: SqliteStore = Depends(get_store)):
    return store.get_all_materials(course_id)


@router.post("/{material_id}/retry", response_model=Material)
async def retry_material(course_id: str, material_id: str, store: SqliteStore = Depends(get_store)):
    material = store.get_material(course_id, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    if material.status != "failed":
        raise HTTPException(status_code=400, detail="Only failed materials can be retried")

    file_path = store.get_material_file_path(course_id, material_id)
    if file_path is None:
        raise HTTPException(status_code=400, detail="Original file not found, cannot retry")

    job = enqueue_material_index_job(
        store,
        course_id=course_id,
        material_id=material_id,
        revision=material.revision,
    )
    if job.status in ("failed", "retryable"):
        try:
            store.retry_knowledge_job(course_id, job.job_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail="The current material retry limit has been reached; upload a replacement or adjust the job budget",
            ) from exc
    elif job.status == "succeeded":
        raise HTTPException(
            status_code=409,
            detail="The current material revision is already indexed; upload a replacement to rebuild it",
        )
    store.update_material_status_if_revision(
        course_id, material_id, material.revision, "processing", degraded=False
    )

    return store.get_material(course_id, material_id)


@router.get("/{material_id}/progress")
async def get_material_progress(course_id: str, material_id: str, store: SqliteStore = Depends(get_store)):
    material = store.get_material(course_id, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")

    jobs = [
        job
        for job in store.list_knowledge_jobs(course_id, material_id=material_id)
        if job.revision == material.revision
    ]
    if jobs:
        running = next((job for job in jobs if job.status in ("queued", "running")), None)
        latest = jobs[-1]
        if running is not None:
            current_step = running.job_type
        elif latest.status == "succeeded":
            current_step = "completed"
        else:
            current_step = "failed"
        return {
            "material_id": material_id,
            "current_step": current_step,
            "steps": [
                {
                    "step": job.job_type,
                    "status": job.status,
                    "detail": job.error_detail,
                    "job_id": job.job_id,
                    "revision": job.revision,
                }
                for job in jobs
            ],
        }

    tasks = store.get_tasks_for_material(course_id, material_id)
    if not tasks:
        raise HTTPException(status_code=404, detail="No progress data for this material")
    current_step = None
    for t in tasks:
        if t["status"] in ("pending", "running"):
            current_step = t["step"]
            break
    if current_step is None and tasks:
        last = tasks[-1]
        if last["status"] == "done":
            current_step = "completed"
        elif last["status"] == "failed":
            current_step = "failed"
    return {"material_id": material_id, "current_step": current_step, "steps": tasks}


@router.get("/{material_id}/source-preview", response_model=SourcePreviewResponse)
async def get_source_preview(
    course_id: str,
    material_id: str,
    fragment_id: str | None = Query(default=None),
    dmap_id: str | None = Query(default=None),
    chunk_index: int | None = Query(default=None),
    store: SqliteStore = Depends(get_store),
):
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    material = store.get_material(course_id, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")

    file_name = material.filename

    if fragment_id is not None:
        fragment = store.get_source_fragment(
            course_id,
            fragment_id,
            material_id=material_id,
            material_revision=material.revision,
        )
        if fragment is not None:
            page_ref = ""
            if fragment.page_start is not None:
                page_ref = str(fragment.page_start)
            elif fragment.slide_start is not None:
                page_ref = f"slide {fragment.slide_start}"
            return SourcePreviewResponse(
                text=fragment.text,
                page_ref=page_ref,
                file_name=file_name,
                locator=fragment.locator(),
            )
        raise HTTPException(
            status_code=404,
            detail="Source fragment was not found for this material's current revision",
        )

    if dmap_id is not None:
        dmap_json = store.get_dmap(course_id)
        if dmap_json:
            try:
                dmap = DMAP.model_validate_json(dmap_json)
            except Exception:
                dmap = None
            if dmap is not None:
                node = get_dmap_node_by_id(dmap, dmap_id)
                if node:
                    parts = [node.title] + [e.text_preview for e in node.elements]
                    text = "\n".join(parts)
                    page_ref = node.page_ref or ""
                    locator = node.title or dmap_id
                    return SourcePreviewResponse(
                        text=text,
                        page_ref=page_ref,
                        file_name=file_name,
                        locator=locator,
                    )
                elem = get_dmap_element_by_id(dmap, dmap_id)
                if elem:
                    text = elem.text_preview or elem.caption or elem.latex or ""
                    page_ref = elem.page_ref or ""
                    locator = f"元素 {dmap_id}"
                    return SourcePreviewResponse(
                        text=text,
                        page_ref=page_ref,
                        file_name=file_name,
                        locator=locator,
                    )

    if chunk_index is not None:
        _qdrant = QdrantStore()
        chunk_payload = _qdrant.get_chunk_by_index(course_id, material_id, chunk_index)
        if chunk_payload:
            text = chunk_payload.get("text", "")
            page_ref = str(chunk_payload.get("page", ""))
            locator = f"第{chunk_index + 1}部分"
            return SourcePreviewResponse(
                text=text,
                page_ref=page_ref,
                file_name=file_name,
                locator=locator,
            )

    raise HTTPException(status_code=404, detail="Source fragment not found")
