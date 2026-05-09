import asyncio
import os
import uuid

from fastapi import APIRouter, Form, HTTPException, UploadFile

from app.db.store import MaterialStore
from app.schemas.foxsay import Material, MaterialKind
from app.services.pipeline import process_material

router = APIRouter(prefix="/courses/{course_id}/materials")

material_store = MaterialStore()

UPLOAD_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")

_KIND_MAP: dict[str, MaterialKind] = {
    ".pdf": "pdf",
    ".ppt": "ppt",
    ".pptx": "ppt",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".gif": "image",
    ".bmp": "image",
    ".webp": "image",
}

_VALID_KINDS = {"pdf", "ppt", "image", "text_note"}


def _infer_kind(filename: str) -> MaterialKind:
    _, ext = os.path.splitext(filename)
    return _KIND_MAP.get(ext.lower(), "text_note")


@router.post("", response_model=Material)
async def upload_material(course_id: str, file: UploadFile, kind: str = Form(default="")):
    material_id = str(uuid.uuid4())
    upload_dir = os.path.join(UPLOAD_ROOT, course_id)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{material_id}_{file.filename}")
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    resolved_kind: MaterialKind = kind if kind in _VALID_KINDS else _infer_kind(file.filename or "")

    material = Material(
        id=material_id,
        course_id=course_id,
        filename=file.filename or "unknown",
        kind=resolved_kind,
        status="processing",
    )
    material_store.create(course_id, material_id, material)

    asyncio.create_task(process_material(course_id, material_id, file_path, resolved_kind, material_store))

    return material


@router.get("/{material_id}/status", response_model=Material)
async def get_material_status(course_id: str, material_id: str):
    material = material_store.get(course_id, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    return material


@router.get("", response_model=list[Material])
async def list_materials(course_id: str):
    return material_store.get_all(course_id)
