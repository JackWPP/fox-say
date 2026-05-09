import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import CragAnswer
from app.services.crag import ask

router = APIRouter(prefix="/courses/{course_id}/chat")


class ChatRequest(BaseModel):
    question: str


@router.post("", response_model=CragAnswer)
async def chat(course_id: str, body: ChatRequest, store: SqliteStore = Depends(get_store)):
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    user_msg_id = str(uuid.uuid4())
    store.save_chat_message(user_msg_id, course_id, "user", body.question)

    answer = await ask(course_id, course.title, body.question)

    citations_json = json.dumps([c.model_dump() for c in answer.citations]) if answer.citations else None
    assistant_msg_id = str(uuid.uuid4())
    store.save_chat_message(
        assistant_msg_id, course_id, "assistant", answer.answer,
        citations_json=citations_json,
        confidence_status=answer.confidence_status,
        refusal_reason=answer.refusal_reason,
    )

    return answer


@router.get("/history")
async def get_chat_history(course_id: str, limit: int = 100, store: SqliteStore = Depends(get_store)):
    messages = store.get_chat_messages(course_id, limit=limit)
    for msg in messages:
        if msg.get("citations_json"):
            msg["citations"] = json.loads(msg["citations_json"])
        else:
            msg["citations"] = []
        del msg["citations_json"]
    return {"course_id": course_id, "messages": messages}
