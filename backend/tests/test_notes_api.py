import pytest
from httpx import AsyncClient


async def _create_course(client: AsyncClient, title: str = "测试课程") -> str:
    resp = await client.post("/courses", json={"title": title})
    assert resp.status_code == 200
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_note(client: AsyncClient):
    course_id = await _create_course(client)
    resp = await client.post(
        f"/courses/{course_id}/notes",
        json={"title": "我的笔记", "content": "这是笔记内容"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_id"] == course_id
    assert data["title"] == "我的笔记"
    assert data["content"] == "这是笔记内容"
    assert data["id"]
    assert data["created_at"]
    assert data["source_citations"] == []


@pytest.mark.asyncio
async def test_create_note_with_citations(client: AsyncClient):
    course_id = await _create_course(client)
    resp = await client.post(
        f"/courses/{course_id}/notes",
        json={
            "title": "带引用的笔记",
            "content": "笔记内容带引用",
            "source_citations": [{"file_name": "lecture.pdf", "locator": "第3部分"}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["source_citations"]) == 1
    assert data["source_citations"][0]["file_name"] == "lecture.pdf"


@pytest.mark.asyncio
async def test_create_note_course_not_found(client: AsyncClient):
    resp = await client.post(
        "/courses/nonexistent/notes",
        json={"title": "笔记", "content": "内容"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_notes(client: AsyncClient):
    course_id = await _create_course(client)
    await client.post(f"/courses/{course_id}/notes", json={"title": "笔记1", "content": "内容1"})
    await client.post(f"/courses/{course_id}/notes", json={"title": "笔记2", "content": "内容2"})
    resp = await client.get(f"/courses/{course_id}/notes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    titles = [n["title"] for n in data]
    assert "笔记1" in titles
    assert "笔记2" in titles


@pytest.mark.asyncio
async def test_get_note(client: AsyncClient):
    course_id = await _create_course(client)
    create_resp = await client.post(
        f"/courses/{course_id}/notes",
        json={"title": "详情笔记", "content": "详情内容"},
    )
    note_id = create_resp.json()["id"]
    resp = await client.get(f"/courses/{course_id}/notes/{note_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "详情笔记"
    assert resp.json()["content"] == "详情内容"


@pytest.mark.asyncio
async def test_get_note_not_found(client: AsyncClient):
    course_id = await _create_course(client)
    resp = await client.get(f"/courses/{course_id}/notes/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_note(client: AsyncClient):
    course_id = await _create_course(client)
    create_resp = await client.post(
        f"/courses/{course_id}/notes",
        json={"title": "原标题", "content": "原内容"},
    )
    note_id = create_resp.json()["id"]
    resp = await client.patch(
        f"/courses/{course_id}/notes/{note_id}",
        json={"title": "新标题", "content": "新内容"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "新标题"
    assert data["content"] == "新内容"
    assert data["updated_at"]


@pytest.mark.asyncio
async def test_update_note_partial(client: AsyncClient):
    course_id = await _create_course(client)
    create_resp = await client.post(
        f"/courses/{course_id}/notes",
        json={"title": "原标题", "content": "原内容"},
    )
    note_id = create_resp.json()["id"]
    resp = await client.patch(
        f"/courses/{course_id}/notes/{note_id}",
        json={"title": "只改标题"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "只改标题"
    assert data["content"] == "原内容"


@pytest.mark.asyncio
async def test_delete_note(client: AsyncClient):
    course_id = await _create_course(client)
    create_resp = await client.post(
        f"/courses/{course_id}/notes",
        json={"title": "要删除", "content": "内容"},
    )
    note_id = create_resp.json()["id"]
    resp = await client.delete(f"/courses/{course_id}/notes/{note_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    resp2 = await client.get(f"/courses/{course_id}/notes/{note_id}")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_note_not_found(client: AsyncClient):
    course_id = await _create_course(client)
    resp = await client.delete(f"/courses/{course_id}/notes/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_notes_isolated_between_courses(client: AsyncClient):
    c1 = await _create_course(client, "课程1")
    c2 = await _create_course(client, "课程2")
    await client.post(f"/courses/{c1}/notes", json={"title": "课程1笔记", "content": "c1"})
    await client.post(f"/courses/{c2}/notes", json={"title": "课程2笔记", "content": "c2"})
    notes1 = (await client.get(f"/courses/{c1}/notes")).json()
    notes2 = (await client.get(f"/courses/{c2}/notes")).json()
    assert len(notes1) == 1
    assert len(notes2) == 1
    assert notes1[0]["title"] == "课程1笔记"
    assert notes2[0]["title"] == "课程2笔记"


@pytest.mark.asyncio
async def test_source_preview_requires_course_and_material(client: AsyncClient):
    resp = await client.get("/courses/nonexistent/materials/m1/source-preview")
    assert resp.status_code == 404

    course_id = await _create_course(client)
    resp = await client.get(f"/courses/{course_id}/materials/nonexistent/source-preview")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_source_preview_not_found_when_no_source(client: AsyncClient):
    course_id = await _create_course(client)
    resp = await client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("test.txt", b"test content", "text/plain")},
        data={"kind": "text_note"},
    )
    material_id = resp.json()["id"]
    resp = await client.get(
        f"/courses/{course_id}/materials/{material_id}/source-preview",
        params={"chunk_index": 0},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_citation_extraction_notes_format():
    from app.services.agent import _extract_citations
    text = "这是一个重要概念，来自笔记 · 重点概念笔记。更多内容来自 [lecture.pdf] · 第3部分。"
    citations = _extract_citations(text)
    assert len(citations) >= 1
    note_cites = [c for c in citations if c["file_name"] == "笔记"]
    assert len(note_cites) >= 1
    assert "重点概念笔记" in note_cites[0]["locator"]
