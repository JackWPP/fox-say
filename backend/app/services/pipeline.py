import asyncio
import logging
import uuid

from app.db.sqlite_store import SqliteStore
from app.services.chunking import chunk_text
from app.services.embedding import embed_texts
from app.services.parsing import parse_document
from app.services.skeleton import generate_skeleton
from app.services.vectorstore import QdrantStore

logger = logging.getLogger(__name__)

_qdrant = QdrantStore()

_material_texts: dict[str, dict[str, str]] = {}

PIPELINE_STEPS = ["parsing", "chunking", "embedding", "storing", "skeleton_generating"]


async def process_material(
    course_id: str,
    material_id: str,
    file_path: str,
    kind: str,
    file_name: str,
    store: SqliteStore,
) -> None:
    task_ids: dict[str, str] = {}
    for step in PIPELINE_STEPS:
        tid = str(uuid.uuid4())
        task_ids[step] = tid
        store.create_task(tid, course_id, material_id, step, status="pending")

    try:
        store.update_task(task_ids["parsing"], "running")
        text = await asyncio.to_thread(parse_document, file_path, kind)
        store.update_task(task_ids["parsing"], "done")
    except Exception as exc:
        logger.warning("Full parsing failed for %s, attempting degraded extraction: %s", material_id, exc)
        store.update_task(task_ids["parsing"], "done", detail="degraded")
        try:
            text = await asyncio.to_thread(_degraded_extract, file_path, kind)
            if text.strip():
                store.update_material_status(course_id, material_id, "ready", degraded=True)
                _update_course_if_ready(course_id, store)
                _material_texts.setdefault(course_id, {})[material_id] = text
                asyncio.create_task(_generate_and_store_skeleton(course_id, store))
                return
            else:
                store.update_material_status(course_id, material_id, "failed")
                for remaining_step in ["chunking", "embedding", "storing", "skeleton_generating"]:
                    store.update_task(task_ids[remaining_step], "skipped")
                return
        except Exception as fallback_exc:
            logger.exception("Degraded extraction also failed for %s: %s", material_id, fallback_exc)
            store.update_material_status(course_id, material_id, "failed")
            for remaining_step in ["chunking", "embedding", "storing", "skeleton_generating"]:
                store.update_task(task_ids[remaining_step], "skipped")
            return

    try:
        store.update_task(task_ids["chunking"], "running")
        chunks = await asyncio.to_thread(chunk_text, text)
        store.update_task(task_ids["chunking"], "done")

        texts = [c["text"] for c in chunks]
        store.update_task(task_ids["embedding"], "running")
        embeddings = await asyncio.to_thread(embed_texts, texts)
        store.update_task(task_ids["embedding"], "done")

        metadata = {
            "course_id": course_id,
            "material_id": material_id,
            "file_name": file_name,
        }
        store.update_task(task_ids["storing"], "running")
        await asyncio.to_thread(_qdrant.upsert_chunks, course_id, chunks, embeddings, metadata)
        store.update_task(task_ids["storing"], "done")

        if course_id not in _material_texts:
            _material_texts[course_id] = {}
        _material_texts[course_id][material_id] = text

        store.update_material_status(course_id, material_id, "ready")

        just_ready = _update_course_if_ready(course_id, store)
        if just_ready:
            store.update_task(task_ids["skeleton_generating"], "running")
            asyncio.create_task(_generate_and_store_skeleton(course_id, store, task_ids.get("skeleton_generating")))
        else:
            store.update_task(task_ids["skeleton_generating"], "skipped", detail="skeleton already exists")

    except Exception:
        logger.exception("Failed to process material %s for course %s", material_id, course_id)
        store.update_material_status(course_id, material_id, "failed")
        current_running = None
        for step, tid in task_ids.items():
            task_data = store.get_tasks_for_material(course_id, material_id)
            for t in task_data:
                if t["id"] == tid and t["status"] == "running":
                    current_running = step
                    store.update_task(tid, "failed")
                    break
        if current_running:
            for step in PIPELINE_STEPS:
                if step not in task_ids:
                    continue
                task_data = store.get_tasks_for_material(course_id, material_id)
                found = False
                for t in task_data:
                    if t["id"] == task_ids[step] and t["status"] == "pending":
                        store.update_task(task_ids[step], "skipped")
                        found = True
                        break


def _update_course_if_ready(course_id: str, store: SqliteStore) -> bool:
    materials = store.get_all_materials(course_id)
    if not materials:
        return False
    all_ready = all(m.status in ("ready", "failed") for m in materials)
    if all_ready:
        course = store.get_course(course_id)
        if course is not None and course.status != "ready":
            updated = course.model_copy(update={"status": "ready"})
            store.update_course(course_id, updated)
            return True
    return False


async def _generate_and_store_skeleton(course_id: str, store: SqliteStore, task_id: str | None = None) -> None:
    try:
        course = store.get_course(course_id)
        if course is None:
            return
        texts_dict = _material_texts.get(course_id, {})
        combined_text = "\n\n".join(texts_dict.values())
        skeleton = await generate_skeleton(course_id, course.title, combined_text)
        store.create_skeleton(skeleton)
        if task_id:
            store.update_task(task_id, "done")
    except Exception:
        logger.exception("Failed to generate skeleton for course %s", course_id)
        if task_id:
            store.update_task(task_id, "failed")


def _degraded_extract(file_path: str, kind: str) -> str:
    if kind == "pdf":
        from app.services.parsing import parse_pdf
        return parse_pdf(file_path)
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""
