"""MVP API boundary registry.

This file intentionally defines route contracts only. It does not implement FastAPI handlers.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiContract:
    method: str
    path: str
    purpose: str
    course_scoped: bool


MVP_API_CONTRACTS: tuple[ApiContract, ...] = (
    ApiContract("POST", "/courses/import-timetable", "Import timetable and create courses", False),
    ApiContract("POST", "/courses", "Manually create a course", False),
    ApiContract("POST", "/courses/{course_id}/materials", "Register uploaded course material", True),
    ApiContract("GET", "/courses/{course_id}/materials/{material_id}/status", "Read processing status", True),
    ApiContract("GET", "/courses/{course_id}/course-outline", "Read current evidence-backed course outline", True),
    ApiContract("GET", "/courses/{course_id}/skeleton", "Read generated course skeleton", True),
    ApiContract("POST", "/courses/{course_id}/chat", "Ask a course-bound CRAG question", True),
    ApiContract("POST", "/courses/{course_id}/review-plan", "Generate super exam review plan", True),
    ApiContract("POST", "/courses/{course_id}/btw", "Ask inline /btw question during review", True),
)
