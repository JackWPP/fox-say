from fastapi import APIRouter, Depends, HTTPException

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import CourseSkeleton

router = APIRouter(prefix="/courses/{course_id}/skeleton")


@router.get("", response_model=CourseSkeleton)
async def get_skeleton(course_id: str, store: SqliteStore = Depends(get_store)):
    skeleton = store.get_skeleton(course_id)
    if skeleton is None:
        raise HTTPException(status_code=404, detail="Skeleton not found for this course")
    return skeleton
