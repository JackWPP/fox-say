from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import BtwInterjection, CragAnswer, Citation, ReviewPlan
from app.services.agent import agent_chat
from app.services.crag import ask
from app.services.review import generate_review_plan

router = APIRouter(prefix="/courses/{course_id}")


class ReviewPlanRequest(BaseModel):
    exam_date: str | None = None


class BtwRequest(BaseModel):
    question: str
    current_step_id: str | None = None


@router.post("/review-plan", response_model=ReviewPlan)
async def create_review_plan(course_id: str, body: ReviewPlanRequest, store: SqliteStore = Depends(get_store)):
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    exam_date = body.exam_date or course.exam_date
    if not exam_date:
        raise HTTPException(status_code=400, detail="Course has no exam date")

    skeleton = store.get_skeleton(course_id)
    if skeleton is None:
        raise HTTPException(status_code=404, detail="Skeleton not found for this course")

    plan = await generate_review_plan(course_id, course.title, exam_date, skeleton)
    store.create_review_plan(plan)
    return plan


@router.post("/btw", response_model=BtwInterjection)
async def btw_interjection(course_id: str, body: BtwRequest, store: SqliteStore = Depends(get_store)):
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    # Build review context for agent
    plan = store.get_review_plan(course_id)
    review_context = ""
    if plan:
        review_context = (
            f"用户正在超级备考复习模式中，当前在第{body.current_step_id or '1'}步。\n"
            f"复习计划总天数：{plan.remaining_days}天。\n"
            f"薄弱区域：{', '.join(plan.weak_areas)}。\n"
            f"可能考点：{', '.join(plan.likely_exam_points)}。"
        )

    # Collect answer from agent stream
    full_answer = ""
    all_citations: list[dict] = []
    async for event in agent_chat(
        course_id, course.title, body.question,
        store=store, review_context=review_context,
    ):
        if event["type"] == "done":
            full_answer = event.get("answer", "")
            all_citations = event.get("citations", [])

    if not full_answer:
        # Fallback to old CRAG
        crag_answer: CragAnswer = await ask(course_id, course.title, body.question, store=store)
        full_answer = crag_answer.answer
        all_citations = [c.model_dump() for c in crag_answer.citations]

    returns_to_step_id = body.current_step_id or ""
    if plan and plan.daily_plan and not body.current_step_id:
        returns_to_step_id = f"day-{plan.daily_plan[0].day_index}"

    return BtwInterjection(
        course_id=course_id,
        question=body.question,
        answer=CragAnswer(
            course_id=course_id,
            answer=full_answer,
            citations=[Citation(**c) for c in all_citations],
            confidence_status="grounded",
            relevance_score=1.0,
        ),
        returns_to_review_step_id=returns_to_step_id,
    )
