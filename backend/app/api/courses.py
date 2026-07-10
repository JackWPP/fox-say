import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import Course, CreateCourseRequest, UpdateCourseRequest, DMAP, ImportTimetableResponse
from app.services.timetable import parse_csv, parse_excel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses")


@router.post("/import-timetable", response_model=ImportTimetableResponse)
async def import_timetable(file: UploadFile, store: SqliteStore = Depends(get_store)):
    filename = file.filename or ""
    raw = await file.read()

    if filename.lower().endswith((".xlsx", ".xls")):
        rows = parse_excel(raw)
    else:
        content = raw.decode("utf-8")
        rows = parse_csv(content)
    courses: list[Course] = []
    for row in rows:
        course = Course(
            id=str(uuid.uuid4()),
            title=row["title"],
            status="empty",
            teacher=row.get("teacher"),
            exam_date=row.get("exam_date"),
        )
        store.create_course(course)
        courses.append(course)
    return ImportTimetableResponse(imported=len(courses), courses=courses)


@router.post("", response_model=Course)
async def create_course(body: CreateCourseRequest, store: SqliteStore = Depends(get_store)):
    course = Course(
        id=str(uuid.uuid4()),
        title=body.title,
        status="empty",
        teacher=body.teacher,
        exam_date=body.exam_date,
        icon=body.icon,
    )
    store.create_course(course)
    return course


@router.patch("/{course_id}", response_model=Course)
async def update_course(course_id: str, body: UpdateCourseRequest, store: SqliteStore = Depends(get_store)):
    existing = store.get_course(course_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if body.title is not None:
        existing.title = body.title
    if body.teacher is not None:
        existing.teacher = body.teacher
    if body.exam_date is not None:
        existing.exam_date = body.exam_date
    if body.icon is not None:
        existing.icon = body.icon
    updated = store.update_course(course_id, existing)
    return updated


@router.get("", response_model=list[Course])
async def list_courses(store: SqliteStore = Depends(get_store)):
    return store.get_all_courses()


@router.post("/{course_id}/quiz")
async def generate_quiz(
    course_id: str,
    body: dict,
    store: SqliteStore = Depends(get_store),
):
    """Generate quiz questions from KC data via LLM.

    Body params:
      chapter_id (optional): only use KCs from this chapter
      count (default 5): number of questions
      type (default "mixed"): "choice" | "fill" | "proof" | "mixed"
    """
    import asyncio
    from app.services.quiz import generate_quiz as _gen

    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    chapter_id: str | None = body.get("chapter_id")
    count: int = int(body.get("count", 5))
    q_type: str = body.get("type", "mixed")

    all_kcs = store.get_kcs_by_course(course_id, include_invalid=False)
    if chapter_id:
        kcs = [kc for kc in all_kcs if kc.chapter_id == chapter_id]
    else:
        kcs = all_kcs

    if not kcs:
        raise HTTPException(status_code=400, detail="No knowledge components found. Upload and process materials first.")

    questions = await asyncio.to_thread(_gen, kcs, count, q_type)
    return {
        "course_id": course_id,
        "chapter_id": chapter_id,
        "count": len(questions),
        "questions": questions,
    }


@router.get("/{course_id}", response_model=Course)
async def get_course(course_id: str, store: SqliteStore = Depends(get_store)):
    course = store.get_course(course_id)
    if course is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.post("/{course_id}/build-wiki")
async def build_wiki_endpoint(course_id: str, store: SqliteStore = Depends(get_store)):
    """Manually trigger Wiki build (KCs + chapter wikis + course_index) from stored DMAP.

    Flattens the stored DMAP back into docling_chunks and runs the standard
    4-stage wiki build pipeline. Useful for re-runs after the pipeline's default
    flow skipped it, or for incremental rebuilds.
    """
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    dmap_json = store.get_dmap(course_id)
    if not dmap_json:
        raise HTTPException(
            status_code=400,
            detail="No DMAP stored. Upload a PDF first (DMAP is built during PDF processing).",
        )

    try:
        dmap = DMAP.model_validate_json(dmap_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stored DMAP is invalid: {exc}")

    # Flatten DMAP back to docling-style chunks for build_wiki's expected input.
    # We walk chapter → section → elements, emitting one chunk per node with
    # heading + accumulated text preview.
    docling_chunks: list[dict] = []
    for chapter in dmap.root.children:
        # Emit chapter heading chunk
        chapter_text_parts = [chapter.title]
        for elem in chapter.elements:
            chapter_text_parts.append(elem.text_preview)
        if chapter_text_parts:
            docling_chunks.append({
                "text": "\n".join(chapter_text_parts),
                "heading": chapter.title,
                "level": 1,
                "page": 0,
            })
        for section in chapter.children:
            section_text_parts = [section.title]
            for elem in section.elements:
                section_text_parts.append(elem.text_preview)
            if section_text_parts:
                docling_chunks.append({
                    "text": "\n".join(section_text_parts),
                    "heading": f"{chapter.title} > {section.title}",
                    "level": 2,
                    "page": 0,
                })

    if not docling_chunks:
        raise HTTPException(status_code=400, detail="DMAP has no usable content to build wiki from")

    from app.services.merkle import MerkleTree as _MT
    from app.services.wiki_builder import build_wiki_async

    old_merkle_json = store.get_merkle_tree(course_id)
    old_merkle = None
    if old_merkle_json:
        try:
            old_merkle = _MT.model_validate_json(old_merkle_json)
        except Exception:
            old_merkle = None

    try:
        result = await build_wiki_async(
            course_id, docling_chunks, store,
            old_merkle_tree=old_merkle,
            source_file="rebuild",
        )
    except Exception as exc:
        logger.exception("Wiki build failed for %s", course_id)
        raise HTTPException(status_code=500, detail=f"Wiki build failed: {exc}")

    return {
        "kcs": len(result.kcs),
        "chapter_wikis": len(result.chapter_wikis),
        "course_index_set": result.course_index is not None,
    }


@router.get("/{course_id}/kcs")
async def list_course_kcs(course_id: str, store: SqliteStore = Depends(get_store)):
    """List all KCs for a course (for tooling and verification)."""
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    kcs = store.get_kcs_by_course(course_id, include_invalid=False)
    return {"kcs": [kc.model_dump() for kc in kcs], "count": len(kcs)}


@router.get("/{course_id}/chapter-wikis")
async def list_chapter_wikis(course_id: str, store: SqliteStore = Depends(get_store)):
    """List all chapter wikis for a course."""
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    cws = store.get_chapter_wikis_by_course(course_id)
    return {"chapter_wikis": [cw.model_dump() for cw in cws], "count": len(cws)}


@router.get("/{course_id}/course-index")
async def get_course_index(course_id: str, store: SqliteStore = Depends(get_store)):
    """Get the markdown course index."""
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    content = store.get_course_index(course_id)
    if not content:
        raise HTTPException(status_code=404, detail="No course index yet")
    return {"content": content}


@router.post("/{course_id}/summary/regenerate")
async def regenerate_course_summary(course_id: str, store: SqliteStore = Depends(get_store)):
    """用 LLM 从 course_index 重新生成课程概述并保存。"""
    import asyncio
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    from app.schemas.foxsay import CourseIndex
    index_json = store.get_course_index(course_id)
    if not index_json:
        raise HTTPException(status_code=400, detail="No course index available. Upload and process materials first.")

    try:
        course_index = CourseIndex.model_validate_json(index_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Invalid course index: {exc}")

    from app.services.wiki_builder import generate_course_summary_from_index
    try:
        summary = await asyncio.to_thread(
            generate_course_summary_from_index, course_id, course.title, course_index
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM summary generation failed: {exc}")

    if not summary:
        raise HTTPException(status_code=500, detail="Failed to generate summary")

    store.update_course_summary(course_id, summary)
    return {"summary": summary, "length": len(summary)}
