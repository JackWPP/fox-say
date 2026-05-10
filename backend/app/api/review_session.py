import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore

router = APIRouter(prefix="/courses/{course_id}/review-session")


class StartSessionResponse(BaseModel):
    session_id: str
    status: str
    current_day: int


class AdvanceRequest(BaseModel):
    current_day: int
    step_id: str


class ProgressResponse(BaseModel):
    session_id: str | None
    status: str
    current_day: int
    current_step: str | None
    completed_steps: list[str]


@router.post("/start", response_model=StartSessionResponse)
async def start_session(course_id: str, store: SqliteStore = Depends(get_store)):
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    existing = store.get_review_session(course_id)
    if existing and existing.get("status") == "active":
        return StartSessionResponse(
            session_id=existing["id"],
            status="active",
            current_day=existing["current_day"],
        )

    session_id = str(uuid.uuid4())
    store.create_review_session(session_id, course_id)
    return StartSessionResponse(session_id=session_id, status="active", current_day=1)


@router.post("/advance", response_model=ProgressResponse)
async def advance_session(
    course_id: str,
    body: AdvanceRequest,
    store: SqliteStore = Depends(get_store),
):
    session = store.get_review_session(course_id)
    if session is None:
        raise HTTPException(status_code=404, detail="No active review session")

    completed = session.get("completed_steps", [])
    if body.step_id not in completed:
        completed = [*completed, body.step_id]

    store.update_review_session(
        session["id"],
        current_day=body.current_day,
        completed_steps_json=completed,
    )

    updated = store.get_review_session(course_id)
    return ProgressResponse(
        session_id=updated["id"],
        status=updated["status"],
        current_day=updated["current_day"],
        current_step=updated.get("current_step"),
        completed_steps=updated["completed_steps"],
    )


@router.get("/progress", response_model=ProgressResponse)
async def get_progress(course_id: str, store: SqliteStore = Depends(get_store)):
    session = store.get_review_session(course_id)
    if session is None:
        return ProgressResponse(
            session_id=None,
            status="not_started",
            current_day=1,
            current_step=None,
            completed_steps=[],
        )
    return ProgressResponse(
        session_id=session["id"],
        status=session["status"],
        current_day=session["current_day"],
        current_step=session.get("current_step"),
        completed_steps=session["completed_steps"],
    )


@router.post("/complete", response_model=ProgressResponse)
async def complete_session(course_id: str, store: SqliteStore = Depends(get_store)):
    session = store.get_review_session(course_id)
    if session is None:
        raise HTTPException(status_code=404, detail="No active review session")

    store.complete_review_session(session["id"])
    return ProgressResponse(
        session_id=session["id"],
        status="completed",
        current_day=session["current_day"],
        current_step=session.get("current_step"),
        completed_steps=session["completed_steps"],
    )
