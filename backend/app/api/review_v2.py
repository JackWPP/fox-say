"""V2-F6 Review API: revision-bound conversational review mode endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/courses/{course_id}")


class GeneratePlanRequest(BaseModel):
    exam_date: str | None = None


class AdvanceRequest(BaseModel):
    to_step: str | None = None


class AnswerRequest(BaseModel):
    answer: str


class BtwRequest(BaseModel):
    question: str
    workflow_hint: str = "auto"


def _get_review_service(request: Request):
    from app.services.review_service import ReviewService
    from app.services.audited_chat_writer import AuditedChatWriter
    from app.services.v2_agent_tools import V2AgentTools
    from app.core.config import settings
    import openai

    store = request.app.state.store
    client = openai.OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_api_base,
    )
    writer = AuditedChatWriter(
        store, client=client, model=settings.deepseek_model,
        course_budget_tokens=settings.knowledge_course_default_token_budget,
    )
    tools = V2AgentTools(store)
    return ReviewService(store, tools, writer)


@router.post("/review/plan")
async def generate_plan(course_id: str, request: Request,
                         body: GeneratePlanRequest | None = None):
    svc = _get_review_service(request)
    exam_date = body.exam_date if body else None
    try:
        plan = await svc.generate_plan(course_id, exam_date)
    except ValueError as exc:
        msg = str(exc)
        if msg == "projection_not_ready":
            raise HTTPException(422, {"error_code": "projection_not_ready"})
        if msg == "no_knowledge_components":
            raise HTTPException(422, {"error_code": "no_knowledge_components"})
        if msg == "active_session_exists":
            raise HTTPException(409, {"error_code": "active_session_exists"})
        raise HTTPException(400, {"error_code": msg})
    return {"plan": plan}


@router.get("/review/plan")
async def get_plan(course_id: str, request: Request):
    svc = _get_review_service(request)
    plan = await svc.get_current_plan(course_id)
    if plan is None:
        raise HTTPException(404, "No review plan found")
    return {"plan": plan}


@router.post("/review/session/start")
async def start_session(course_id: str, request: Request):
    svc = _get_review_service(request)
    try:
        state = await svc.start_session(course_id)
    except ValueError as exc:
        msg = str(exc)
        if msg == "no_active_plan":
            raise HTTPException(404, {"error_code": "no_active_plan"})
        if msg == "plan_stale":
            raise HTTPException(400, {"error_code": "plan_stale"})
        if msg == "active_session_exists":
            raise HTTPException(409, {"error_code": "active_session_exists"})
        raise HTTPException(400, {"error_code": msg})
    return {
        "session_id": state.session_id,
        "plan_id": state.plan_id,
        "current_day": state.current_day,
        "current_step": state.current_step,
        "day_title": state.day_title,
        "day_items_count": state.day_items_count,
        "day_items": state.day_items,
        "total_days": state.total_days,
    }


@router.post("/review/session/{session_id}/advance")
async def advance_session(course_id: str, session_id: str, request: Request,
                           body: AdvanceRequest | None = None):
    svc = _get_review_service(request)
    to_step = body.to_step if body else None
    try:
        state = await svc.advance_session(session_id, to_step)
    except ValueError as exc:
        msg = str(exc)
        if msg == "session_not_found":
            raise HTTPException(404, {"error_code": "session_not_found"})
        if msg == "session_not_active":
            raise HTTPException(409, {"error_code": "session_not_active"})
        if msg == "session_stale":
            raise HTTPException(400, {"error_code": "session_stale"})
        raise HTTPException(400, {"error_code": msg})

    response: dict = {
        "current_step": state.current_step,
        "current_day": state.current_day,
        "current_item_id": state.current_item_id,
    }
    if state.current_item:
        response["current_item"] = state.current_item
    if state.current_attempt:
        response["attempt_id"] = state.current_attempt.get("id")
        response["question"] = state.current_attempt.get("question")
    if state.grade:
        response["grade"] = state.grade
        response["needs_tutor"] = state.needs_tutor
        response["next_action"] = state.next_action
        response["observations_created"] = state.observations_created
    if state.current_step == "next_day_recap":
        response["day_summary"] = state.day_summary
        response["kc_statuses"] = state.kc_statuses
        response["is_last_day"] = state.is_last_day
    return response


@router.post("/review/session/{session_id}/answer")
async def submit_answer(course_id: str, session_id: str, request: Request,
                         body: AnswerRequest):
    svc = _get_review_service(request)
    try:
        grading = await svc.submit_answer(session_id, body.answer)
    except ValueError as exc:
        msg = str(exc)
        if msg == "session_not_found":
            raise HTTPException(404, {"error_code": "session_not_found"})
        if msg == "session_stale":
            raise HTTPException(409, {"error_code": "session_stale"})
        if msg == "not_in_attempt_step":
            raise HTTPException(400, {"error_code": "not_in_attempt_step"})
        if msg.startswith("no_awaiting_attempt"):
            raise HTTPException(400, {"error_code": "no_awaiting_attempt"})
        raise HTTPException(400, {"error_code": msg})
    return {
        "attempt_id": grading.attempt_id,
        "grade": grading.grade,
        "needs_tutor": grading.needs_tutor,
        "next_step": grading.next_step,
        "observations_created": grading.observations_created,
    }


@router.post("/review/session/{session_id}/complete")
async def complete_session(course_id: str, session_id: str, request: Request):
    svc = _get_review_service(request)
    try:
        summary = await svc.complete_session(session_id)
    except ValueError as exc:
        raise HTTPException(400, {"error_code": str(exc)})
    return {
        "session_id": summary.session_id,
        "status": summary.status,
        "summary": {
            "days_completed": summary.days_completed,
            "total_attempts": summary.total_attempts,
            "correct_attempts": summary.correct_attempts,
            "partial_attempts": summary.partial_attempts,
            "incorrect_attempts": summary.incorrect_attempts,
            "observations_count": summary.observations_count,
            "started_at": summary.started_at,
            "completed_at": summary.completed_at,
        },
    }


@router.post("/review/session/{session_id}/btw")
async def handle_btw(course_id: str, session_id: str, request: Request,
                      body: BtwRequest):
    svc = _get_review_service(request)
    try:
        result = await svc.handle_btw(session_id, body.question, body.workflow_hint)
    except ValueError as exc:
        msg = str(exc)
        if msg == "no_active_review_session":
            raise HTTPException(404, {"error_code": "no_active_session"})
        if msg.startswith("/btw not available"):
            raise HTTPException(400, {"error_code": "btw_not_available"})
        raise HTTPException(400, {"error_code": msg})
    return {"envelope": result.envelope, "return_anchor": result.return_anchor}


@router.get("/review/session/current")
async def get_current_session(course_id: str, request: Request):
    svc = _get_review_service(request)
    state = await svc.get_current_session(course_id)
    return {
        "has_active_session": state.has_active_session,
        "session": state.session,
        "plan": state.plan,
        "current_attempt": state.current_attempt,
        "last_grade": state.last_grade,
        "is_stale": state.is_stale,
        "stale_reason": state.stale_reason,
    }


@router.delete("/review/session/{session_id}")
async def cancel_session(course_id: str, session_id: str, request: Request):
    svc = _get_review_service(request)
    try:
        result = await svc.cancel_session(session_id)
    except ValueError as exc:
        raise HTTPException(404, {"error_code": str(exc)})
    return result


@router.get("/review/observations")
async def get_observations(course_id: str, request: Request):
    svc = _get_review_service(request)
    result = await svc.get_observations(course_id)
    return {
        "observations": result.observations,
        "total": result.total,
        "by_kc": result.by_kc,
    }
