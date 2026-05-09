import uuid

from fastapi import APIRouter, Depends, UploadFile

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import Course, CreateCourseRequest, ImportTimetableResponse
from app.services.timetable import parse_csv

router = APIRouter(prefix="/courses")


@router.post("/import-timetable", response_model=ImportTimetableResponse)
async def import_timetable(file: UploadFile, store: SqliteStore = Depends(get_store)):
    content = (await file.read()).decode("utf-8")
    rows = parse_csv(content)
    courses: list[Course] = []
    for row in rows:
        course = Course(
            id=str(uuid.uuid4()),
            title=row["title"],
            status="empty",
            teacher=row.get("teacher"),
            exam_date=row.get("exam_date"),
        )
        store.create_course(course)
        courses.append(course)
    return ImportTimetableResponse(imported=len(courses), courses=courses)


@router.post("", response_model=Course)
async def create_course(body: CreateCourseRequest, store: SqliteStore = Depends(get_store)):
    course = Course(
        id=str(uuid.uuid4()),
        title=body.title,
        status="empty",
        teacher=body.teacher,
        exam_date=body.exam_date,
    )
    store.create_course(course)
    return course


@router.get("", response_model=list[Course])
async def list_courses(store: SqliteStore = Depends(get_store)):
    return store.get_all_courses()


@router.get("/{course_id}", response_model=Course)
async def get_course(course_id: str, store: SqliteStore = Depends(get_store)):
    course = store.get_course(course_id)
    if course is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Course not found")
    return course
