import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.services.agent import agent_chat

router = APIRouter(prefix="/courses/{course_id}/review-session")


class StartSessionResponse(BaseModel):
    session_id: str
    status: str
    current_day: int


class AdvanceRequest(BaseModel):
    current_day: int
    step_id: str
    step_type: str | None = None  # 'teach' | 'quiz' | 'review'


class GenerateStepRequest(BaseModel):
    current_day: int
    step_type: str  # 'teach' | 'quiz' | 'review'


class GenerateStepResponse(BaseModel):
    content: str
    citations: list[dict]
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


@router.post("/generate-step", response_model=GenerateStepResponse)
async def generate_step(
    course_id: str,
    body: GenerateStepRequest,
    store: SqliteStore = Depends(get_store),
):
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    plan = store.get_review_plan(course_id)

    current_day_plan = plan.daily_plan[body.current_day - 1] if plan and plan.daily_plan else None
    review_context = f"用户正在复习第{body.current_day}天，当前步骤：{body.step_type}。"
    if current_day_plan:
        review_context += f"复习重点：{current_day_plan.focus}。"
    if plan:
        review_context += f"\n薄弱区域：{', '.join(plan.weak_areas)}。"
        review_context += f"\n可能考点：{', '.join(plan.likely_exam_points)}。"

    if body.step_type == "teach":
        question = "请讲解今天复习内容的核心概念，用简洁易懂的方式。"
    elif body.step_type == "quiz":
        question = "请出一道关于今天复习内容的练习题。"
    elif body.step_type == "review":
        question = "请总结今天的复习内容。"
    else:
        raise HTTPException(status_code=400, detail=f"Invalid step_type: {body.step_type}")

    full_answer = ""
    all_citations: list[dict] = []
    async for event in agent_chat(
        course_id, course.title, question,
        store=store, review_context=review_context,
    ):
        if event["type"] == "done":
            full_answer = event.get("answer", "")
            all_citations = event.get("citations", [])
        elif event["type"] == "error":
            raise HTTPException(status_code=502, detail=event.get("message", "Agent error"))

    return GenerateStepResponse(
        content=full_answer,
        citations=all_citations,
        step_id=f"day-{body.current_day}-{body.step_type}",
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
