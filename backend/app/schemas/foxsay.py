from typing import Literal

from pydantic import BaseModel

CourseStatus = Literal["empty", "processing", "ready", "failed"]
MaterialKind = Literal["pdf", "ppt", "image", "text_note"]
Importance = Literal["high", "medium", "low"]
ConfidenceStatus = Literal["grounded", "ambiguous", "out_of_scope"]


class Course(BaseModel):
    id: str
    title: str
    status: CourseStatus
    teacher: str | None = None
    exam_date: str | None = None


class Material(BaseModel):
    id: str
    course_id: str
    filename: str
    kind: MaterialKind
    status: CourseStatus


class CourseSkeletonChapter(BaseModel):
    id: str
    title: str
    key_concepts: list[str]
    importance: Importance
    exam_weight: float


class CourseSkeleton(BaseModel):
    course_id: str
    chapters: list[CourseSkeletonChapter]
    core_concepts: list[str]
    difficulty_areas: list[str]
    prerequisite_chain: list[list[str]]


class Citation(BaseModel):
    file_name: str
    locator: str


class CragAnswer(BaseModel):
    course_id: str
    answer: str
    citations: list[Citation]
    confidence_status: ConfidenceStatus
    relevance_score: float
    refusal_reason: str | None = None


class ReviewPlanDay(BaseModel):
    day_index: int
    focus: str
    suggested_minutes: int
    priority: Importance


class ReviewPlan(BaseModel):
    course_id: str
    remaining_days: int
    daily_plan: list[ReviewPlanDay]
    likely_exam_points: list[str]
    weak_areas: list[str]


class BtwInterjection(BaseModel):
    course_id: str
    question: str
    answer: CragAnswer
    returns_to_review_step_id: str


class ImportTimetableResponse(BaseModel):
    imported: int
    courses: list[Course]


class CreateCourseRequest(BaseModel):
    title: str
    teacher: str | None = None
    exam_date: str | None = None
