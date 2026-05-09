import asyncio
import os
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from app.core.config import settings
from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import Material, MaterialKind
from app.services.pipeline import process_material

router = APIRouter(prefix="/courses/{course_id}/materials")

_KIND_MAP: dict[str, MaterialKind] = {
    ".pdf": "pdf",
    ".ppt": "ppt",
    ".pptx": "ppt",
    ".txt": "text_note",
    ".md": "text_note",
}

_VALID_KINDS = {"pdf", "ppt", "text_note"}


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
    )
    store.create_material(material, file_path=file_path)

    asyncio.create_task(process_material(course_id, material_id, file_path, resolved_kind, file.filename or "unknown", store))

    return material


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

    store.delete_tasks_for_material(course_id, material_id)
    store.update_material_status(course_id, material_id, "processing", degraded=False)

    asyncio.create_task(
        process_material(course_id, material_id, file_path, material.kind, material.filename, store)
    )

    return store.get_material(course_id, material_id)


@router.get("/{material_id}/progress")
async def get_material_progress(course_id: str, material_id: str, store: SqliteStore = Depends(get_store)):
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
