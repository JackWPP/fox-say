"""V2 course evidence APIs.

These routes deliberately do not share the legacy material preview router:
they only expose evidence that is valid for a material's current, ready
revision and never fall back to DMAP locators or old Qdrant chunks.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.schemas.evidence import SourceFragmentPreview


router = APIRouter(prefix="/courses/{course_id}/source-fragments")


@router.get("/{fragment_id}", response_model=SourceFragmentPreview)
async def get_current_source_fragment_preview(
    course_id: str,
    fragment_id: str,
    store: SqliteStore = Depends(get_store),
) -> SourceFragmentPreview:
    """Open a V2 citation only when its material revision is current and ready."""
    if store.get_course(course_id) is None:
        raise HTTPException(status_code=404, detail="Course not found")

    resolved = store.get_current_ready_source_fragment_preview(course_id, fragment_id)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail="Source fragment was not found for this course's current material revision",
        )
    fragment, file_name = resolved
    return SourceFragmentPreview(
        course_id=fragment.course_id,
        material_id=fragment.material_id,
        material_revision=fragment.material_revision,
        fragment_id=fragment.fragment_id,
        file_name=file_name,
        text=fragment.text,
        locator=fragment.locator(),
        heading_path=fragment.heading_path,
        page_start=fragment.page_start,
        page_end=fragment.page_end,
        slide_start=fragment.slide_start,
        slide_end=fragment.slide_end,
        char_start=fragment.char_start,
        char_end=fragment.char_end,
        kind=fragment.kind,
    )
