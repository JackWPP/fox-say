"""Dashboard aggregation endpoint for display screen / widget use."""
from datetime import date, datetime

from fastapi import APIRouter, Depends

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _days_left(exam_date_str: str | None) -> int | None:
    if not exam_date_str:
        return None
    try:
        exam = datetime.strptime(exam_date_str, "%Y-%m-%d").date()
        return (exam - date.today()).days
    except ValueError:
        return None


@router.get("")
def get_dashboard(store: SqliteStore = Depends(get_store)):
    """Single-request aggregation for display screens and widgets.

    Returns all courses enriched with `days_left`, plus top-level stats
    (total, ready count, nearest exam).
    """
    courses = store.get_all_courses()

    enriched = []
    nearest: dict | None = None

    for c in courses:
        dl = _days_left(c.exam_date)
        entry = {
            "id": c.id,
            "title": c.title,
            "icon": c.icon,
            "status": c.status,
            "teacher": c.teacher,
            "exam_date": c.exam_date,
            "days_left": dl,
            "material_count": c.material_count,
            "summary": c.summary,
        }
        enriched.append(entry)

        # Track nearest upcoming exam
        if dl is not None and dl >= 0:
            if nearest is None or dl < nearest["days_left"]:
                nearest = {"course_id": c.id, "title": c.title, "icon": c.icon, "days_left": dl}

    ready_count = sum(1 for c in courses if c.status == "ready")

    return {
        "courses": enriched,
        "stats": {
            "total_courses": len(courses),
            "ready_courses": ready_count,
            "nearest_exam": nearest,
        },
    }
