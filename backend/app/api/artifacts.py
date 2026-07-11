"""V2-F7 Artifacts API: course brief and study artifact endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/courses/{course_id}")


class GenerateBriefRequest(BaseModel):
    force: bool = False


class GenerateArtifactRequest(BaseModel):
    section_id: str | None = None
    force: bool = False


def _get_brief_service(request: Request):
    from app.services.course_brief_service import CourseBriefService
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
    return CourseBriefService(store, writer, tools)


def _get_artifact_service(request: Request):
    from app.services.artifact_service import ArtifactService
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
    return ArtifactService(store, writer, tools)


def _brief_to_response(result):
    data = {
        "brief": {
            "brief_id": result.brief_id,
            "course_id": result.course_id,
            "source_revision": result.source_revision,
            "knowledge_revision": result.knowledge_revision,
            "status": result.status,
            "brief_json": result.brief_json,
            "is_stale": result.is_stale,
            "stale_reason": result.stale_reason,
            "created_at": result.created_at,
        }
    }
    if result.error_code:
        data["error_code"] = result.error_code
    if result.error_detail:
        data["brief"]["error_detail"] = result.error_detail
    return data


def _artifact_to_response(result):
    data = {
        "artifact": {
            "artifact_id": result.artifact_id,
            "course_id": result.course_id,
            "source_revision": result.source_revision,
            "knowledge_revision": result.knowledge_revision,
            "section_id": result.section_id,
            "section_title": result.section_title,
            "artifact_type": result.artifact_type,
            "status": result.status,
            "artifact_json": result.artifact_json,
            "is_stale": result.is_stale,
            "stale_reason": result.stale_reason,
            "created_at": result.created_at,
        }
    }
    if result.error_detail:
        data["artifact"]["error_detail"] = result.error_detail
    return data


@router.post("/course-brief")
async def generate_course_brief(course_id: str, request: Request,
                                 body: GenerateBriefRequest | None = None):
    force = body.force if body else False
    svc = _get_brief_service(request)
    session_id = f"cs_{uuid.uuid4().hex[:16]}"
    turn_id = f"tn_{uuid.uuid4().hex[:16]}"

    result = await svc.generate(
        course_id=course_id, session_id=session_id,
        turn_id=turn_id, force=force,
    )

    if result.status == "not_found" and result.error_code == "projection_not_ready":
        raise HTTPException(status_code=422, detail={
            "error_code": "projection_not_ready",
            "message": result.error_detail,
        })

    if result.status == "failed":
        return _brief_to_response(result)

    return _brief_to_response(result)


@router.get("/course-brief")
async def get_course_brief(course_id: str, request: Request):
    svc = _get_brief_service(request)
    result = await svc.get_current(course_id)

    if result is None:
        raise HTTPException(status_code=404, detail="No course brief found")

    return _brief_to_response(result)


@router.post("/study-artifacts")
async def generate_study_artifacts(course_id: str, request: Request,
                                   body: GenerateArtifactRequest | None = None):
    section_id = body.section_id if body else None
    force = body.force if body else False
    svc = _get_artifact_service(request)
    session_id = f"cs_{uuid.uuid4().hex[:16]}"
    turn_id = f"tn_{uuid.uuid4().hex[:16]}"

    if section_id:
        result = await svc.generate(
            course_id=course_id, session_id=session_id,
            turn_id=turn_id, section_id=section_id, force=force,
        )
        if result.status == "not_found" and result.error_code == "section_not_found":
            raise HTTPException(status_code=404, detail={
                "error_code": "section_not_found",
                "message": result.error_detail,
            })
        if result.status == "not_found" and result.error_code == "projection_not_ready":
            raise HTTPException(status_code=422, detail={
                "error_code": "projection_not_ready",
                "message": result.error_detail,
            })
        return _artifact_to_response(result)

    batch = await svc.generate_all(
        course_id=course_id, session_id=session_id,
        turn_id=turn_id, force=force,
    )
    return {
        "artifacts": [_artifact_to_response(a)["artifact"] for a in batch.artifacts],
        "summary": {
            "total_sections": batch.total_sections,
            "generated": batch.generated,
            "failed": batch.failed,
            "skipped_existing": batch.skipped_existing,
        },
    }


@router.get("/study-artifacts")
async def list_study_artifacts(course_id: str, request: Request):
    svc = _get_artifact_service(request)
    result = await svc.list_artifacts(course_id)
    return {
        "artifacts": result.artifacts,
        "is_stale": result.is_stale,
        "total_active": result.total_active,
        "total_stale": result.total_stale,
        "total_failed": result.total_failed,
    }


@router.get("/study-artifacts/{artifact_id}")
async def get_study_artifact(course_id: str, artifact_id: str, request: Request):
    svc = _get_artifact_service(request)
    result = await svc.get_artifact(course_id, artifact_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _artifact_to_response(result)
