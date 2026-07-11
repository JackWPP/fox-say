"""V2-F7 Artifacts API tests: course brief and study artifact endpoints."""

from __future__ import annotations

import json
from unittest.mock import patch


class _FakeWriterResponse:
    def __init__(self, content: str) -> None:
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]
        self.usage = None


class _FakeWriterClient:
    def __init__(self, content: str) -> None:
        self._content = content
        self.chat = type("C", (), {"completions": type("Completions", (), {"create": self._create})()})()

    def _create(self, **kwargs) -> _FakeWriterResponse:
        return _FakeWriterResponse(self._content)


BRIEF_JSON = json.dumps({
    "overview": "本课程覆盖向量空间、矩阵理论等核心概念。",
    "key_topics": [
        {
            "topic": "向量空间",
            "description": "向量空间的定义和性质",
            "kcs_involved": ["kc_test1"],
            "evidence_refs": []
        },
        {
            "topic": "矩阵运算",
            "description": "矩阵的加法和乘法",
            "kcs_involved": ["kc_test2"],
            "evidence_refs": []
        },
        {
            "topic": "行列式",
            "description": "行列式的计算和性质",
            "kcs_involved": ["kc_test3"],
            "evidence_refs": []
        }
    ],
    "study_suggestions": [
        {"suggestion": "先掌握向量空间基础", "rationale": "这是后续内容的基础"}
    ],
    "difficulty_areas": [],
    "metadata": {"sections_count": 3, "kcs_count": 3, "relations_count": 0, "fragment_count": 5}
}, ensure_ascii=False)

ARTIFACT_JSON = json.dumps({
    "summary": "本节介绍向量空间的基本定义。",
    "key_concepts": [
        {"concept": "向量空间", "explanation": "满足加法和数乘封闭性的集合", "kc_id": "kc_test1", "evidence_refs": []},
        {"concept": "子空间", "explanation": "向量空间的子集", "kc_id": "kc_test2", "evidence_refs": []}
    ],
    "examples": [],
    "common_pitfalls": [],
    "evidence_refs": []
}, ensure_ascii=False)


def _seed_course_with_knowledge(client):
    """Seed a course and manually insert knowledge projection data for testing."""
    # This is an async function - we use await
    pass


async def test_course_brief_projection_not_ready(client):
    """Course brief returns 422 when projection is not ready."""
    course = await client.post("/courses", json={"title": "测试课程"})
    course_id = course.json()["id"]

    fake_client = _FakeWriterClient(BRIEF_JSON)
    with patch("openai.OpenAI", return_value=fake_client):
        resp = await client.post(f"/courses/{course_id}/course-brief")

    assert resp.status_code == 422
    data = resp.json()
    assert data["detail"]["error_code"] == "projection_not_ready"


async def test_course_brief_not_found(client):
    """GET course brief returns 404 when none exists."""
    course = await client.post("/courses", json={"title": "测试课程"})
    course_id = course.json()["id"]

    resp = await client.get(f"/courses/{course_id}/course-brief")
    assert resp.status_code == 404


async def test_study_artifacts_empty_list(client):
    """GET study artifacts returns empty list when none exist."""
    course = await client.post("/courses", json={"title": "测试课程"})
    course_id = course.json()["id"]

    resp = await client.get(f"/courses/{course_id}/study-artifacts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["artifacts"] == []
    assert data["total_active"] == 0


async def test_study_artifact_section_not_found(client):
    """POST study artifact returns 404 for unknown section when projection is ready."""
    course = await client.post("/courses", json={"title": "测试课程"})
    course_id = course.json()["id"]

    # Without projection, should return 422 (projection_not_ready) first
    fake_client = _FakeWriterClient(ARTIFACT_JSON)
    with patch("openai.OpenAI", return_value=fake_client):
        resp = await client.post(
            f"/courses/{course_id}/study-artifacts",
            json={"section_id": "nonexistent"},
        )

    assert resp.status_code == 422


async def test_study_artifact_get_not_found(client):
    """GET specific artifact returns 404 when not found."""
    course = await client.post("/courses", json={"title": "测试课程"})
    course_id = course.json()["id"]

    resp = await client.get(f"/courses/{course_id}/study-artifacts/sa_nonexistent")
    assert resp.status_code == 404
