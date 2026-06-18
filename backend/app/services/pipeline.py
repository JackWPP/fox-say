import asyncio
import logging
import uuid

from app.db.sqlite_store import SqliteStore
from app.services.chunking import chunk_text
from app.services.embedding import embed_texts
from app.services.parsing import parse_document
from app.services.skeleton import generate_skeleton
from app.services.vectorstore import QdrantStore
from app.api.events import push_event
from app.services.dmap import build_dmap
from app.services.merkle import compute_merkle_tree, diff_merkle_trees
from app.services.wiki_builder import build_wiki_async

logger = logging.getLogger(__name__)

_qdrant = QdrantStore()

_material_texts: dict[str, dict[str, str]] = {}

PIPELINE_STEPS = [
    "parsing", "build_dmap", "wiki_build",
    "chunking", "embedding", "storing", "skeleton_generating",
]

# 这些步骤在所有材料就绪后统一执行(不逐材料跑)
_COURSE_LEVEL_STEPS = {"build_dmap", "wiki_build", "skeleton_generating"}


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
    except ValueError as exc:
        logger.warning("Unsupported material kind for %s: %s", material_id, exc)
        store.update_task(task_ids["parsing"], "failed", detail=str(exc))
        store.update_material_status(course_id, material_id, "failed")
        for remaining_step in ["build_dmap", "wiki_build", "chunking", "embedding", "storing", "skeleton_generating"]:
            store.update_task(task_ids[remaining_step], "skipped")
        return
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
                for remaining_step in ["build_dmap", "wiki_build", "chunking", "embedding", "storing"]:
                    store.update_task(task_ids[remaining_step], "skipped")
                return
            else:
                store.update_material_status(course_id, material_id, "failed")
                for remaining_step in ["build_dmap", "wiki_build", "chunking", "embedding", "storing", "skeleton_generating"]:
                    store.update_task(task_ids[remaining_step], "skipped")
                return
        except Exception as fallback_exc:
            logger.exception("Degraded extraction also failed for %s: %s", material_id, fallback_exc)
            store.update_material_status(course_id, material_id, "failed")
            for remaining_step in ["build_dmap", "wiki_build", "chunking", "embedding", "storing", "skeleton_generating"]:
                store.update_task(task_ids[remaining_step], "skipped")
            return

    # Build DMAP from docling (or fallback flat text), then trigger Wiki build (best-effort)
    docling_chunks: list[dict] = []
    if kind == "pdf":
        try:
            from app.services.parsing_docling import parse_pdf_docling
            docling_chunks = await asyncio.to_thread(parse_pdf_docling, file_path)
        except Exception as e:
            logger.warning("Docling failed for %s, trying MinerU: %s", material_id, e)

        # Docling 没产出结构化 chunks → 试 MinerU API 获取带 heading 的结构化输出
        if not docling_chunks:
            try:
                from app.services.mineru import parse_pdf_mineru
                md_text = await asyncio.to_thread(parse_pdf_mineru, file_path)
                if md_text and len(md_text) > 100:
                    logger.info("MinerU returned %d chars for %s", len(md_text), material_id)
                    # 用 MinerU 的 markdown 作为 text (覆盖 pdfplumber 的结果)
                    text = md_text
                    # 从 markdown 标题生成结构化 chunks
                    docling_chunks = _markdown_to_chunks(md_text)
            except Exception as e:
                logger.warning("MinerU fallback failed for %s: %s", material_id, e)

    if not docling_chunks:
        # Flat fallback: treat entire text as a paragraph element (no heading/level)
        docling_chunks = [{"text": text, "heading": "", "level": 0, "page": 0}]

    # 存储 docling_chunks 供后续 course-level wiki_build 使用
    if course_id not in _material_texts:
        _material_texts[course_id] = {}
    _material_texts[course_id][material_id] = text

    # build_dmap + wiki_build 不再逐材料执行,标记为 pending 等 course-level 处理
    store.update_task(task_ids["build_dmap"], "skipped", detail="deferred to course-level")
    store.update_task(task_ids["wiki_build"], "skipped", detail="deferred to course-level")

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
        await asyncio.to_thread(_qdrant.delete_by_material, course_id, material_id)
        await asyncio.to_thread(_qdrant.upsert_chunks, course_id, chunks, embeddings, metadata)
        store.update_task(task_ids["storing"], "done")

        store.update_material_status(course_id, material_id, "ready")
        push_event(course_id, "material_processed", {"material_id": material_id})

        just_ready = _update_course_if_ready(course_id, store)
        if just_ready:
            # 所有材料就绪 → 统一跑 DMAP + wiki_build + skeleton
            asyncio.create_task(_build_course_wiki(course_id, store))
        else:
            store.update_task(task_ids["skeleton_generating"], "skipped", detail="waiting for other materials")

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
                t = store.get_tasks_for_material(course_id, material_id)
                for task_row in t:
                    if task_row["id"] == task_ids[step] and task_row["status"] == "pending":
                        store.update_task(task_ids[step], "skipped")
                        break


def _update_course_if_ready(course_id: str, store: SqliteStore) -> bool:
    materials = store.get_all_materials(course_id)
    if not materials:
        return False
    all_terminal = all(m.status in ("ready", "failed") for m in materials)
    at_least_one_ready = any(m.status == "ready" for m in materials)
    if all_terminal and at_least_one_ready:
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
        push_event(course_id, "skeleton_ready", {"course_id": course_id})
        if task_id:
            store.update_task(task_id, "done")
    except Exception:
        logger.exception("Failed to generate skeleton for course %s", course_id)
        if task_id:
            store.update_task(task_id, "failed")


async def _build_course_wiki(course_id: str, store: SqliteStore) -> None:
    """所有材料就绪后统一跑 DMAP + wiki_build + skeleton。

    合并所有材料文本,只跑一次 wiki_build,避免逐材料覆盖。
    """
    logger.info("All materials ready for %s, building course wiki", course_id)

    # 1. 合并所有材料文本
    texts_dict = _material_texts.get(course_id, {})
    if not texts_dict:
        logger.warning("No material texts for %s, skipping wiki build", course_id)
        return
    combined_text = "\n\n".join(texts_dict.values())

    # 2. 生成 docling_chunks (从合并文本)
    docling_chunks = [{"text": combined_text, "heading": "", "level": 0, "page": 0}]

    # 3. build_dmap
    try:
        dmap_obj = build_dmap(course_id, docling_chunks, source_file="merged")
        store.save_dmap(course_id, dmap_obj.model_dump_json())
        logger.info("DMAP built for %s: %d chapters", course_id, len(dmap_obj.root.children))
    except Exception:
        logger.exception("DMAP build failed for %s", course_id)
        return

    # 4. wiki_build
    try:
        old_merkle_json = store.get_merkle_tree(course_id)
        old_merkle = None
        if old_merkle_json:
            from app.schemas.foxsay import MerkleTree
            try:
                old_merkle = MerkleTree.model_validate_json(old_merkle_json)
            except Exception:
                old_merkle = None
        new_merkle = compute_merkle_tree(dmap_obj)
        try:
            store.save_merkle_tree(course_id, new_merkle.model_dump_json())
        except Exception:
            pass
        await build_wiki_async(
            course_id, docling_chunks, store,
            old_merkle_tree=old_merkle,
            source_file="merged",
        )
        logger.info("Wiki build completed for %s", course_id)
    except Exception:
        logger.exception("Wiki build failed for %s", course_id)

    # 5. skeleton
    try:
        course = store.get_course(course_id)
        if course:
            skeleton = await generate_skeleton(course_id, course.title, combined_text)
            store.create_skeleton(skeleton)
            push_event(course_id, "skeleton_ready", {"course_id": course_id})
            logger.info("Skeleton generated for %s", course_id)
    except Exception:
        logger.exception("Skeleton generation failed for %s", course_id)


def _degraded_extract(file_path: str, kind: str) -> str:
    if kind == "pdf":
        from app.services.parsing import parse_pdf
        return parse_pdf(file_path)
    return ""


def _markdown_to_chunks(md_text: str) -> list[dict]:
    """把 MinerU 返回的 Markdown 转成 build_dmap 期望的 chunks 格式。

    解析 Markdown 标题 (# / ## / ###) 作为 heading + level,
    非标题段落作为 text。
    """
    import re
    chunks: list[dict] = []
    current_heading = ""
    current_level = 0
    current_text_parts: list[str] = []

    def _flush():
        text = "\n".join(current_text_parts).strip()
        if text:
            chunks.append({
                "text": text,
                "heading": current_heading,
                "level": current_level,
                "page": 0,
            })

    heading_re = re.compile(r"^(#{1,6})\s+(.+)$")

    for line in md_text.split("\n"):
        m = heading_re.match(line.strip())
        if m:
            _flush()
            current_text_parts = []
            current_level = len(m.group(1))
            current_heading = m.group(2).strip()
        else:
            current_text_parts.append(line)

    _flush()
    return chunks
