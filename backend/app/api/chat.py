from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.courses import course_store
from app.schemas.foxsay import CragAnswer
from app.services.crag import ask

router = APIRouter(prefix="/courses/{course_id}/chat")


class ChatRequest(BaseModel):
    question: str


@router.post("", response_model=CragAnswer)
async def chat(course_id: str, body: ChatRequest):
    course = course_store.get(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return await ask(course_id, course.title, body.question)
