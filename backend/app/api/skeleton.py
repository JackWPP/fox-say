from fastapi import APIRouter, HTTPException

from app.db.store import SkeletonStore
from app.schemas.foxsay import CourseSkeleton

router = APIRouter(prefix="/courses/{course_id}/skeleton")

skeleton_store = SkeletonStore()


@router.get("", response_model=CourseSkeleton)
async def get_skeleton(course_id: str):
    skeleton = skeleton_store.get(course_id)
    if skeleton is None:
        raise HTTPException(status_code=404, detail="Skeleton not found for this course")
    return skeleton
