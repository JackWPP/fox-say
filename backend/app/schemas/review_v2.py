"""V2-F6 Review Mode schemas: plan, session, attempt, observation, and service result types."""

from __future__ import annotations

from dataclasses import dataclass, field


# -- Service result dataclasses --


@dataclass(frozen=True)
class ReviewSessionState:
    session_id: str
    plan_id: str
    course_id: str
    current_day: int
    current_step: str
    current_item_id: str | None = None
    status: str = "active"
    day_title: str = ""
    day_items: list[dict] = field(default_factory=list)
    day_items_count: int = 0
    total_days: int = 0
    current_item: dict | None = None
    current_attempt: dict | None = None
    grade: dict | None = None
    needs_tutor: bool = False
    next_action: str | None = None
    kc_statuses: dict[str, str] = field(default_factory=dict)
    day_summary: str = ""
    is_last_day: bool = False
    observations_created: int = 0


@dataclass(frozen=True)
class GradingResult:
    attempt_id: str
    grade: dict
    needs_tutor: bool
    next_step: str = "feedback"
    observations_created: int = 0


@dataclass(frozen=True)
class BtwResult:
    envelope: dict
    return_anchor: dict


@dataclass(frozen=True)
class ReviewSessionSummary:
    session_id: str
    status: str = "completed"
    days_completed: int = 0
    total_attempts: int = 0
    correct_attempts: int = 0
    partial_attempts: int = 0
    incorrect_attempts: int = 0
    observations_count: int = 0
    kcs_covered: int = 0
    started_at: str = ""
    completed_at: str = ""


@dataclass(frozen=True)
class CurrentSessionState:
    has_active_session: bool = False
    session: dict | None = None
    plan: dict | None = None
    current_attempt: dict | None = None
    last_grade: dict | None = None
    is_stale: bool = False
    stale_reason: str | None = None


@dataclass(frozen=True)
class ObservationList:
    observations: list[dict] = field(default_factory=list)
    total: int = 0
    by_kc: dict[str, int] = field(default_factory=dict)


# -- State machine constants --

REVIEW_STEPS = (
    "briefing",
    "teach",
    "attempt",
    "grading",
    "tutor",
    "feedback",
    "next_item",
    "next_day_recap",
    "done",
)

VALID_TRANSITIONS: dict[str, list[str]] = {
    "briefing": ["teach"],
    "teach": ["attempt"],
    "attempt": ["grading"],
    "grading": ["tutor", "feedback"],
    "tutor": ["feedback"],
    "feedback": ["next_item", "next_day_recap", "done"],
    "next_item": ["teach"],
    "next_day_recap": ["briefing", "done"],
}

BTW_ALLOWED_STEPS = frozenset({"attempt", "feedback", "tutor"})
