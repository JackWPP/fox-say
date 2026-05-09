import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.schemas.foxsay import Course, Material
from app.services.chunking import chunk_text
from app.services.parsing import parse_text


@pytest.mark.asyncio
async def test_upload_material(client: AsyncClient):
    resp = await client.post(
        "/courses/test-course-1/materials",
        files={"file": ("notes.txt", b"Hello world content", "text/plain")},
        data={"kind": "text_note"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_material_with_course(client: AsyncClient):
    await client.post("/courses", json={"title": "测试课程"})
    courses = (await client.get("/courses")).json()
    course_id = courses[0]["id"]

    resp = await client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("notes.txt", b"Hello world content", "text/plain")},
        data={"kind": "text_note"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_id"] == course_id
    assert data["filename"] == "notes.txt"
    assert data["kind"] == "text_note"
    assert data["status"] == "processing"


@pytest.mark.asyncio
async def test_upload_material_infer_kind(client: AsyncClient):
    await client.post("/courses", json={"title": "测试课程2"})
    courses = (await client.get("/courses")).json()
    course_id = [c["id"] for c in courses if c["title"] == "测试课程2"][0]

    resp = await client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("lecture.pdf", b"%PDF-1.4 fake content", "application/pdf")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "pdf"


@pytest.mark.asyncio
async def test_list_materials(client: AsyncClient):
    await client.post("/courses", json={"title": "测试课程3"})
    courses = (await client.get("/courses")).json()
    course_id = [c["id"] for c in courses if c["title"] == "测试课程3"][0]

    resp = await client.get(f"/courses/{course_id}/materials")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_material_status_not_found(client: AsyncClient):
    await client.post("/courses", json={"title": "测试课程4"})
    courses = (await client.get("/courses")).json()
    course_id = [c["id"] for c in courses if c["title"] == "测试课程4"][0]

    resp = await client.get(f"/courses/{course_id}/materials/nonexistent/status")
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
