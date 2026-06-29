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


# ===== 批量上传 + parsed_text 持久化 + image kind 测试 =====


@pytest.mark.asyncio
async def test_batch_upload_materials(client: AsyncClient):
    """批量上传 3 个文件,全部被接受并创建 Material 记录。"""
    await client.post("/courses", json={"title": "批量测试课程"})
    courses = (await client.get("/courses")).json()
    course_id = [c["id"] for c in courses if c["title"] == "批量测试课程"][0]

    files = [
        ("files", ("a.txt", b"content a", "text/plain")),
        ("files", ("b.txt", b"content b", "text/plain")),
        ("files", ("c.md", b"# markdown content", "text/markdown")),
    ]
    resp = await client.post(f"/courses/{course_id}/materials/batch", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    for m in data:
        assert m["course_id"] == course_id
        assert m["status"] == "processing"
    filenames = {m["filename"] for m in data}
    assert filenames == {"a.txt", "b.txt", "c.md"}


@pytest.mark.asyncio
async def test_batch_upload_too_many_files(client: AsyncClient):
    """上传超过 max_batch_upload(默认 15)个文件,返回 413。"""
    await client.post("/courses", json={"title": "超限测试课程"})
    courses = (await client.get("/courses")).json()
    course_id = [c["id"] for c in courses if c["title"] == "超限测试课程"][0]

    files = [("files", (f"f{i}.txt", b"x", "text/plain")) for i in range(16)]
    resp = await client.post(f"/courses/{course_id}/materials/batch", files=files)
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_batch_upload_empty(client: AsyncClient):
    """空文件列表返回 422(FastAPI 参数验证拒绝空 list,合理行为)。"""
    await client.post("/courses", json={"title": "空批量测试"})
    courses = (await client.get("/courses")).json()
    course_id = [c["id"] for c in courses if c["title"] == "空批量测试"][0]

    resp = await client.post(f"/courses/{course_id}/materials/batch", files=[])
    # FastAPI 在参数验证阶段拒绝空 list,返回 422 而非进入端点逻辑
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_batch_upload_course_not_found(client: AsyncClient):
    """不存在的 course_id 返回 404。"""
    resp = await client.post(
        "/courses/nonexistent-course/materials/batch",
        files=[("files", ("a.txt", b"x", "text/plain"))],
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_infer_kind_image(client: AsyncClient):
    """PNG 文件应被推断为 image kind(之前会被推断成 text_note 导致 utf-8 读取失败)。"""
    await client.post("/courses", json={"title": "图片类型测试"})
    courses = (await client.get("/courses")).json()
    course_id = [c["id"] for c in courses if c["title"] == "图片类型测试"][0]

    resp = await client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("diagram.png", b"\x89PNG fake binary", "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "image"


@pytest.mark.asyncio
async def test_parsed_text_persistence(client: AsyncClient):
    """解析文本应持久化到 DB,进程重启后仍可读取。"""
    from app.db.sqlite_store import SqliteStore
    from app.core.config import settings

    await client.post("/courses", json={"title": "持久化测试课程"})
    courses = (await client.get("/courses")).json()
    course_id = [c["id"] for c in courses if c["title"] == "持久化测试课程"][0]

    # 上传一个文本文件
    resp = await client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("persist.txt", b"persistent content for restart test", "text/plain")},
        data={"kind": "text_note"},
    )
    assert resp.status_code == 200
    material_id = resp.json()["id"]

    # 用一个新的 store 实例模拟进程重启
    restarted_store = SqliteStore(db_path=settings.sqlite_path)
    try:
        # 验证 list_materials 返回 degraded 字段(schema 对齐)
        materials = restarted_store.get_all_materials(course_id)
        assert len(materials) >= 1
        assert hasattr(materials[0], "degraded")
        # degraded 字段应该是 bool 类型(不是 None)
        assert isinstance(materials[0].degraded, bool)

        # 验证 parsed_text 持久化方法存在且可调用
        assert hasattr(restarted_store, "save_parsed_text")
        assert hasattr(restarted_store, "get_parsed_text")
        assert hasattr(restarted_store, "get_all_parsed_texts")

        # 写入 parsed_text 并验证可读
        restarted_store.save_parsed_text(course_id, material_id, "simulated parsed text")
        text = restarted_store.get_parsed_text(course_id, material_id)
        assert text == "simulated parsed text"

        # 验证 get_all_parsed_texts 返回字典
        all_texts = restarted_store.get_all_parsed_texts(course_id)
        assert material_id in all_texts
        assert all_texts[material_id] == "simulated parsed text"
    finally:
        restarted_store.close()


@pytest.mark.asyncio
async def test_list_materials_returns_degraded(client: AsyncClient):
    """list_materials 端点应返回 degraded 字段(之前恒为 False)。"""
    await client.post("/courses", json={"title": "degraded 测试课程"})
    courses = (await client.get("/courses")).json()
    course_id = [c["id"] for c in courses if c["title"] == "degraded 测试课程"][0]

    await client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("d.txt", b"content", "text/plain")},
        data={"kind": "text_note"},
    )
    resp = await client.get(f"/courses/{course_id}/materials")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    # degraded 字段必须存在且为 bool
    assert "degraded" in data[0]
    assert isinstance(data[0]["degraded"], bool)


def test_parse_with_markitdown_import():
    """验证 markitdown 可正常导入(HEC-5 依赖验证)。"""
    from app.services.parsing import parse_with_markitdown, parse_document
    assert callable(parse_with_markitdown)
    assert callable(parse_document)


def test_parse_document_unsupported_kind():
    """不支持的 kind 应抛 ValueError(HEC-1,不静默吞错)。"""
    from app.services.parsing import parse_document
    with pytest.raises(ValueError, match="Unsupported material kind"):
        parse_document("fake_path", "unsupported_kind")
