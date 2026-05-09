import uuid

from fastapi import APIRouter, UploadFile

from app.db.store import CourseStore
from app.schemas.foxsay import Course, CreateCourseRequest, ImportTimetableResponse
from app.services.timetable import parse_csv

router = APIRouter(prefix="/courses")

course_store = CourseStore()


@router.post("/import-timetable", response_model=ImportTimetableResponse)
async def import_timetable(file: UploadFile):
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
        course_store.create(course.id, course)
        courses.append(course)
    return ImportTimetableResponse(imported=len(courses), courses=courses)


@router.post("", response_model=Course)
async def create_course(body: CreateCourseRequest):
    course = Course(
        id=str(uuid.uuid4()),
        title=body.title,
        status="empty",
        teacher=body.teacher,
        exam_date=body.exam_date,
    )
    course_store.create(course.id, course)
    return course


@router.get("", response_model=list[Course])
async def list_courses():
    return course_store.get_all()


@router.get("/{course_id}", response_model=Course)
async def get_course(course_id: str):
    course = course_store.get(course_id)
    if course is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Course not found")
    return course
