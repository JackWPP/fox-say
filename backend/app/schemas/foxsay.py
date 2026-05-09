"""Shared backend schema placeholders aligned with frontend/src/types/foxsay.ts."""

from dataclasses import dataclass
from typing import Literal

CourseStatus = Literal["empty", "processing", "ready", "failed"]
MaterialKind = Literal["pdf", "ppt", "image", "text_note"]
Importance = Literal["high", "medium", "low"]
ConfidenceStatus = Literal["grounded", "ambiguous", "out_of_scope"]


@dataclass(frozen=True)
class Course:
    id: str
    title: str
    status: CourseStatus
    teacher: str | None = None
    exam_date: str | None = None


@dataclass(frozen=True)
class Material:
    id: str
    course_id: str
    filename: str
    kind: MaterialKind
    status: CourseStatus


@dataclass(frozen=True)
class CourseSkeletonChapter:
    id: str
    title: str
    key_concepts: tuple[str, ...]
    importance: Importance
    exam_weight: float


@dataclass(frozen=True)
class CourseSkeleton:
    course_id: str
    chapters: tuple[CourseSkeletonChapter, ...]
    core_concepts: tuple[str, ...]
    difficulty_areas: tuple[str, ...]
    prerequisite_chain: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Citation:
    file_name: str
    locator: str


@dataclass(frozen=True)
class CragAnswer:
    course_id: str
    answer: str
    citations: tuple[Citation, ...]
    confidence_status: ConfidenceStatus
    relevance_score: float
    refusal_reason: str | None = None


@dataclass(frozen=True)
class ReviewPlanDay:
    day_index: int
    focus: str
    suggested_minutes: int
    priority: Importance


@dataclass(frozen=True)
class ReviewPlan:
    course_id: str
    remaining_days: int
    daily_plan: tuple[ReviewPlanDay, ...]
    likely_exam_points: tuple[str, ...]
    weak_areas: tuple[str, ...]


@dataclass(frozen=True)
class BtwInterjection:
    course_id: str
    question: str
    answer: CragAnswer
    returns_to_review_step_id: str

