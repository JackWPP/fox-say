import asyncio
import logging
from typing import TYPE_CHECKING

from app.api.courses import course_store
from app.db.store import SkeletonStore
from app.services.chunking import chunk_text
from app.services.embedding import embed_texts
from app.services.parsing import parse_document
from app.services.skeleton import generate_skeleton
from app.services.vectorstore import QdrantStore

if TYPE_CHECKING:
    from app.db.store import MaterialStore

logger = logging.getLogger(__name__)

_qdrant = QdrantStore()
skeleton_store = SkeletonStore()

_material_texts: dict[str, dict[str, str]] = {}


async def process_material(
    course_id: str,
    material_id: str,
    file_path: str,
    kind: str,
    material_store: "MaterialStore",
) -> None:
    try:
        text = parse_document(file_path, kind)
        chunks = chunk_text(text)
        texts = [c["text"] for c in chunks]
        embeddings = embed_texts(texts)

        metadata = {
            "course_id": course_id,
            "material_id": material_id,
        }
        _qdrant.upsert_chunks(course_id, chunks, embeddings, metadata)

        if course_id not in _material_texts:
            _material_texts[course_id] = {}
        _material_texts[course_id][material_id] = text

        material = material_store.get(course_id, material_id)
        if material is not None:
            updated = material.model_copy(update={"status": "ready"})
            material_store.update(course_id, material_id, updated)

        just_ready = _check_course_ready(course_id, material_store)
        if just_ready:
            asyncio.create_task(_generate_and_store_skeleton(course_id))
    except Exception:
        logger.exception("Failed to process material %s for course %s", material_id, course_id)
        material = material_store.get(course_id, material_id)
        if material is not None:
            updated = material.model_copy(update={"status": "failed"})
            material_store.update(course_id, material_id, updated)


def _check_course_ready(course_id: str, material_store: "MaterialStore") -> bool:
    materials = material_store.get_all(course_id)
    if not materials:
        return False
    all_ready = all(m.status == "ready" for m in materials)
    if all_ready:
        course = course_store.get(course_id)
        if course is not None and course.status != "ready":
            updated = course.model_copy(update={"status": "ready"})
            course_store.update(course_id, updated)
            return True
    return False


async def _generate_and_store_skeleton(course_id: str) -> None:
    try:
        course = course_store.get(course_id)
        if course is None:
            return
        texts_dict = _material_texts.get(course_id, {})
        combined_text = "\n\n".join(texts_dict.values())
        skeleton = await generate_skeleton(course_id, course.title, combined_text)
        skeleton_store.create(course_id, skeleton)
    except Exception:
        logger.exception("Failed to generate skeleton for course %s", course_id)
