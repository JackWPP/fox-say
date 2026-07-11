"""V2 Chat API: SSE streaming, history, sessions, run snapshot and cancel."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.services.audited_chat_writer import AuditedChatWriter
from app.services.deep_dive_router import should_use_deep_dive
from app.services.deep_dive_service import DeepDiveService
from app.services.quick_answer_service import QuickAnswerService
from app.services.v2_agent_tools import V2AgentTools

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses/{course_id}/chat")


class StreamRequest(BaseModel):
    question: str
    session_id: str | None = None
    selected_source_ids: list[str] = []
    selected_note_ids: list[str] = []
    workflow_hint: str = "auto"
    client_request_id: str | None = None


class CreateSessionRequest(BaseModel):
    title: str = "新对话"


def _build_service(store: SqliteStore) -> QuickAnswerService:
    client = OpenAI(
        api_key=settings.deepseek_api_key or "placeholder",
        base_url=settings.deepseek_api_base,
        timeout=settings.knowledge_model_timeout_seconds,
        max_retries=0,
    )
    writer = AuditedChatWriter(
        store,
        client=client,
        model=settings.deepseek_model,
        course_budget_tokens=settings.knowledge_course_default_token_budget,
    )
    return QuickAnswerService(store, writer)


def _build_deep_dive_service(store: SqliteStore) -> DeepDiveService:
    client = OpenAI(
        api_key=settings.deepseek_api_key or "placeholder",
        base_url=settings.deepseek_api_base,
        timeout=settings.knowledge_model_timeout_seconds,
        max_retries=0,
    )
    writer = AuditedChatWriter(
        store,
        client=client,
        model=settings.deepseek_model,
        course_budget_tokens=settings.knowledge_course_default_token_budget,
    )
    tools = V2AgentTools(store)
    return DeepDiveService(store, writer, tools)


_PHASE_MESSAGES = {
    "retrieving": ("scout", "正在检索课程证据..."),
    "mapping": ("mapper", "正在分析课程结构..."),
    "composing": ("tutor", "正在组织回答..."),
    "verifying": ("verifier", "正在验证引用..."),
}


def _chunk_text(text: str, size: int = 120) -> list[str]:
    """Split text into ~size-char chunks at natural boundaries."""
    if not text:
        return []
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= size:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, size)
        if cut < 20:
            cut = remaining.rfind("。", 0, size)
        if cut < 20:
            cut = remaining.rfind("；", 0, size)
        if cut < 20:
            cut = size
        else:
            cut += 1
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    return chunks


@router.post("/stream")
async def chat_stream(course_id: str, body: StreamRequest, store: SqliteStore = Depends(get_store)):
    """V2 streaming endpoint - SSE events with Agent phases and AnswerEnvelope."""
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    # Resolve session - auto-create if not provided
    session_id = body.session_id
    if not session_id:
        sessions = store.get_chat_sessions(course_id)
        if sessions:
            session_id = sessions[0]["id"]
        else:
            session_id = str(uuid.uuid4())
            store.create_chat_session(session_id, course_id, "新对话")
    else:
        store.touch_chat_session(session_id, course_id)

    user_msg_id = str(uuid.uuid4())
    store.save_chat_message(
        user_msg_id, course_id, "user", body.question, session_id=session_id,
    )

    turn_id = str(uuid.uuid4())
    use_deep_dive = should_use_deep_dive(
        body.question, retrieval_outcome=None, workflow_hint=body.workflow_hint
    )
    if use_deep_dive:
        service = _build_deep_dive_service(store)
        phases = ("retrieving", "mapping", "composing", "verifying")
    else:
        service = _build_service(store)
        phases = ("retrieving", "composing", "verifying")

    async def event_generator():
        run_id: str | None = None
        try:
            # Create the run via the service, then emit SSE events.
            # We call the service first to get the complete result, then
            # stream phases and tokens. This is simpler than intercepting
            # the service internals for the first version.
            result = await service.answer(
                course_id=course_id,
                session_id=session_id,
                turn_id=turn_id,
                query=body.question,
                selected_material_ids=body.selected_source_ids or None,
                selected_note_ids=body.selected_note_ids or None,
            )
            run_id = result.run_id
            envelope = result.envelope

            # accepted
            yield _sse("accepted", {
                "run_id": run_id,
                "turn_id": turn_id,
                "session_id": session_id,
                "source_revision": envelope.source_revision,
                "knowledge_revision": envelope.knowledge_revision,
            })

            # phases
            for phase_key in phases:
                role, msg = _PHASE_MESSAGES[phase_key]
                yield _sse("phase", {
                    "run_id": run_id,
                    "phase": phase_key,
                    "agent_role": role,
                    "display_message": msg,
                })

            # tokens (split answer into chunks)
            for chunk in _chunk_text(envelope.answer):
                yield _sse("token", {"run_id": run_id, "delta": chunk})

            # done
            message_id = str(uuid.uuid4())
            envelope_json = envelope.model_dump_json(ensure_ascii=False)
            citations = [c.model_dump(mode="json") for c in envelope.citations]

            # Persist assistant message with full V2 metadata
            store.save_chat_message(
                message_id, course_id, "assistant", envelope.answer,
                session_id=session_id,
                citations_json=json.dumps(citations, ensure_ascii=False) if citations else None,
                confidence_status=envelope.confidence_status,
                run_id=run_id,
                source_revision=envelope.source_revision,
                knowledge_revision=envelope.knowledge_revision,
                answer_source=envelope.answer_source,
                envelope_json=envelope_json,
            )
            store.touch_chat_session(session_id, course_id)

            yield _sse("done", {
                "run_id": run_id,
                "message_id": message_id,
                "answer": envelope.answer,
                "envelope": envelope.model_dump(mode="json"),
                "citations": citations,
                "confidence_status": envelope.confidence_status,
                "answer_source": envelope.answer_source,
                "run_status": result.run_status,
            })

            # If there were warnings, emit them as a final phase
            if result.warnings:
                for w in result.warnings:
                    yield _sse("phase", {
                        "run_id": run_id,
                        "phase": "warning",
                        "agent_role": "verifier",
                        "display_message": w,
                    })

        except Exception as exc:
            logger.exception("V2 chat stream failed for course %s", course_id)
            error_data = {
                "run_id": run_id or "",
                "error_code": "stream_failed",
                "message": str(exc)[:500],
                "retriable": True,
            }
            yield _sse("error", error_data)
            # Persist an error message so history is not empty
            error_msg_id = str(uuid.uuid4())
            store.save_chat_message(
                error_msg_id, course_id, "assistant",
                f"回答生成失败：{exc}"[:500],
                session_id=session_id,
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# --- Chat Sessions ---


@router.get("/sessions")
async def list_sessions(course_id: str, store: SqliteStore = Depends(get_store)):
    sessions = store.get_chat_sessions(course_id)
    return {"course_id": course_id, "sessions": sessions}


@router.post("/sessions")
async def create_session(course_id: str, body: CreateSessionRequest, store: SqliteStore = Depends(get_store)):
    session_id = str(uuid.uuid4())
    store.create_chat_session(session_id, course_id, body.title)
    return {"session_id": session_id, "title": body.title}


@router.delete("/sessions/{session_id}")
async def delete_session(course_id: str, session_id: str, store: SqliteStore = Depends(get_store)):
    store.delete_chat_session(session_id, course_id=course_id)
    return {"deleted": True}


# --- Chat History (paginated, session-scoped) ---


@router.get("/history")
async def get_chat_history(
    course_id: str,
    session_id: str = Query(default=""),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    store: SqliteStore = Depends(get_store),
):
    messages = store.get_chat_messages(course_id, session_id=session_id, limit=limit, offset=offset)
    total = store.count_chat_messages(course_id, session_id=session_id)
    for msg in messages:
        if msg.get("citations_json"):
            msg["citations"] = json.loads(msg["citations_json"])
        else:
            msg["citations"] = []
        if "citations_json" in msg:
            del msg["citations_json"]
        # Parse envelope if present
        if msg.get("envelope_json"):
            try:
                msg["envelope"] = json.loads(msg["envelope_json"])
            except (json.JSONDecodeError, TypeError):
                msg["envelope"] = None
        else:
            msg["envelope"] = None
    return {
        "course_id": course_id,
        "session_id": session_id,
        "messages": messages,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


# --- Agent Run Snapshot ---


@router.get("/agent-runs/{run_id}")
async def get_agent_run_snapshot(course_id: str, run_id: str, store: SqliteStore = Depends(get_store)):
    """Return the persistent run state and steps for SSE reconciliation."""
    run = store.get_agent_run(course_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    steps = store.get_agent_steps(run_id)
    return {
        "run": run.model_dump(mode="json"),
        "steps": [s.model_dump(mode="json") for s in steps],
    }


@router.post("/agent-runs/{run_id}/cancel")
async def cancel_agent_run(course_id: str, run_id: str, store: SqliteStore = Depends(get_store)):
    """Mark a non-terminal agent run as cancelled."""
    run = store.get_agent_run(course_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    terminal = {"completed", "failed", "cancelled", "stale"}
    if run.status in terminal:
        raise HTTPException(
            status_code=409,
            detail=f"Run is already in terminal status: {run.status}",
        )
    store.update_agent_run_status(course_id, run_id, "cancelled")
    return {"run_id": run_id, "status": "cancelled"}
