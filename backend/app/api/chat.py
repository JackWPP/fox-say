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
    return await ask(course_id, course.title, body.question)
