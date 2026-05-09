import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.courses import course_store
from app.db.store import MaterialStore
from app.main import app
from app.schemas.foxsay import Course
from app.services.chunking import chunk_text
from app.services.parsing import parse_text


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _seed_course():
    course = Course(id="test-course-1", title="测试课程", status="empty")
    course_store.create(course.id, course)
    yield
    course_store._data.pop(course.id, None)


@pytest.mark.asyncio
async def test_upload_material(client: AsyncClient):
    resp = await client.post(
        "/courses/test-course-1/materials",
        files={"file": ("notes.txt", b"Hello world content", "text/plain")},
        data={"kind": "text_note"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_id"] == "test-course-1"
    assert data["filename"] == "notes.txt"
    assert data["kind"] == "text_note"
    assert data["status"] == "processing"


@pytest.mark.asyncio
async def test_upload_material_infer_kind(client: AsyncClient):
    resp = await client.post(
        "/courses/test-course-1/materials",
        files={"file": ("lecture.pdf", b"%PDF-1.4 fake content", "application/pdf")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "pdf"


@pytest.mark.asyncio
async def test_upload_material_infer_kind_default(client: AsyncClient):
    resp = await client.post(
        "/courses/test-course-1/materials",
        files={"file": ("notes.txt", b"Hello world content", "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "text_note"


@pytest.mark.asyncio
async def test_list_materials(client: AsyncClient):
    store = MaterialStore()
    from app.schemas.foxsay import Material

    m = Material(id="mat-1", course_id="test-course-1", filename="a.txt", kind="text_note", status="ready")
    store.create("test-course-1", "mat-1", m)

    from app.api.materials import material_store as api_store
    api_store.create("test-course-1", "mat-1", m)

    resp = await client.get("/courses/test-course-1/materials")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_material_status_not_found(client: AsyncClient):
    resp = await client.get("/courses/test-course-1/materials/nonexistent/status")
    assert resp.status_code == 404


def test_chunk_text():
    text = "A" * 1200
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) >= 2
    assert chunks[0]["index"] == 0
    assert chunks[0]["text"] == "A" * 500
    assert chunks[1]["index"] == 1


def test_chunk_text_empty():
    assert chunk_text("") == []


def test_parse_text():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write("Hello FoxSay")
        path = f.name
    try:
        result = parse_text(path)
        assert result == "Hello FoxSay"
    finally:
        os.unlink(path)
