import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_course(client: AsyncClient):
    resp = await client.post("/courses", json={"title": "高等数学", "teacher": "张老师", "exam_date": "2026-06-15"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "高等数学"
    assert data["status"] == "empty"
    assert data["teacher"] == "张老师"
    assert data["exam_date"] == "2026-06-15"
    assert data["id"]


@pytest.mark.asyncio
async def test_list_courses(client: AsyncClient):
    await client.post("/courses", json={"title": "线性代数"})
    await client.post("/courses", json={"title": "概率论"})
    resp = await client.get("/courses")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    titles = [c["title"] for c in data]
    assert "线性代数" in titles
    assert "概率论" in titles


@pytest.mark.asyncio
async def test_get_course(client: AsyncClient):
    create_resp = await client.post("/courses", json={"title": "物理"})
    course_id = create_resp.json()["id"]
    resp = await client.get(f"/courses/{course_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "物理"


@pytest.mark.asyncio
async def test_get_course_not_found(client: AsyncClient):
    resp = await client.get("/courses/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_timetable(client: AsyncClient):
    csv_content = "课程名,教师,考试日期\n化学,李老师,2026-07-01\n生物,王老师,2026-07-02\n"
    resp = await client.post(
        "/courses/import-timetable",
        files={"file": ("timetable.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert len(data["courses"]) == 2
    assert data["courses"][0]["title"] == "化学"
    assert data["courses"][1]["title"] == "生物"
    for c in data["courses"]:
        assert c["status"] == "empty"
