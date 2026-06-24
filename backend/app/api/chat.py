import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import CragAnswer
from app.services.agent import agent_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses/{course_id}/chat")


class StreamRequest(BaseModel):
    question: str
    session_id: str | None = None


class CreateSessionRequest(BaseModel):
    title: str = "New Chat"


@router.post("/stream")
async def chat_stream(course_id: str, body: StreamRequest, store: SqliteStore = Depends(get_store)):
    """Agent streaming endpoint — SSE events with tool calls and final answer."""
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    # Resolve session — auto-create if not provided
    session_id = body.session_id
    if not session_id:
        sessions = store.get_chat_sessions(course_id)
        if sessions:
            session_id = sessions[0]["id"]
        else:
            session_id = str(uuid.uuid4())
            store.create_chat_session(session_id, course_id, "New Chat")
    else:
        store.touch_chat_session(session_id)

    user_msg_id = str(uuid.uuid4())
    store.save_chat_message(user_msg_id, course_id, "user", body.question, session_id=session_id)

    # Load history for this session only
    chat_history = store.get_chat_messages(course_id, session_id=session_id, limit=20)
    history_msgs: list[dict] = []
    for m in chat_history[:-1]:
        history_msgs.append({"role": m["role"], "content": m["content"]})

    async def event_generator():
        full_answer = ""
        all_citations: list[dict] = []
        try:
            async for event in agent_chat(
                course_id, course.title, body.question,
                chat_history=history_msgs, store=store,
            ):
                event_type = event.get("type", "message")
                event_data = json.dumps(event, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {event_data}\n\n"

                if event_type == "done":
                    full_answer = event.get("answer", "")
                    all_citations = event.get("citations", [])
        except Exception:
            logger.exception("Stream failed for course %s", course_id)
            yield f"event: error\ndata: {json.dumps({'message': '流式输出失败'})}\n\n"

        # Persist assistant message
        citations_json = json.dumps(all_citations, ensure_ascii=False) if all_citations else None
        assistant_msg_id = str(uuid.uuid4())
        store.save_chat_message(
            assistant_msg_id, course_id, "assistant", full_answer or "(empty)",
            session_id=session_id, citations_json=citations_json,
        )
        store.touch_chat_session(session_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    store.delete_chat_session(session_id)
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
    return {
        "course_id": course_id,
        "session_id": session_id,
        "messages": messages,
        "total": total,
        "offset": offset,
        "limit": limit,
    }
