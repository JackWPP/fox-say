from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.courses import course_store
from app.api.skeleton import skeleton_store
from app.db.store import ReviewPlanStore
from app.schemas.foxsay import BtwInterjection, CragAnswer, ReviewPlan
from app.services.crag import ask
from app.services.review import generate_review_plan

router = APIRouter(prefix="/courses/{course_id}")

review_plan_store = ReviewPlanStore()


class ReviewPlanRequest(BaseModel):
    exam_date: str | None = None


class BtwRequest(BaseModel):
    question: str
    current_step_id: str | None = None


@router.post("/review-plan", response_model=ReviewPlan)
async def create_review_plan(course_id: str, body: ReviewPlanRequest):
    course = course_store.get(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    exam_date = body.exam_date or course.exam_date
    if not exam_date:
        raise HTTPException(status_code=400, detail="Course has no exam date")

    skeleton = skeleton_store.get(course_id)
    if skeleton is None:
        raise HTTPException(status_code=404, detail="Skeleton not found for this course")

    plan = await generate_review_plan(course_id, course.title, exam_date, skeleton)
    review_plan_store.create(course_id, plan)
    return plan


@router.post("/btw", response_model=BtwInterjection)
async def btw_interjection(course_id: str, body: BtwRequest):
    course = course_store.get(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    answer: CragAnswer = await ask(course_id, course.title, body.question)

    plan = review_plan_store.get(course_id)
    returns_to_step_id = body.current_step_id or ""
    if plan and plan.daily_plan and not body.current_step_id:
        returns_to_step_id = f"day-{plan.daily_plan[0].day_index}"

    return BtwInterjection(
        course_id=course_id,
        question=body.question,
        answer=answer,
        returns_to_review_step_id=returns_to_step_id,
    )
