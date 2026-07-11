"""V2-F6 Review API tests: plan generation, session lifecycle, and /btw."""

from __future__ import annotations


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


async def test_review_plan_no_projection(client):
    """Plan generation returns 422 when projection is not ready."""
    course = await client.post("/courses", json={"title": "复习测试"})
    course_id = course.json()["id"]

    resp = await client.post(f"/courses/{course_id}/review/plan")
    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "projection_not_ready"


async def test_review_plan_not_found(client):
    """GET review plan returns 404 when none exists."""
    course = await client.post("/courses", json={"title": "复习测试"})
    course_id = course.json()["id"]

    resp = await client.get(f"/courses/{course_id}/review/plan")
    assert resp.status_code == 404


async def test_review_session_no_plan(client):
    """Start session returns 404 when no plan exists."""
    course = await client.post("/courses", json={"title": "复习测试"})
    course_id = course.json()["id"]

    resp = await client.post(f"/courses/{course_id}/review/session/start")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "no_active_plan"


async def test_review_session_current_empty(client):
    """GET current session returns has_active_session=false when none exists."""
    course = await client.post("/courses", json={"title": "复习测试"})
    course_id = course.json()["id"]

    resp = await client.get(f"/courses/{course_id}/review/session/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_active_session"] is False


async def test_review_session_not_found(client):
    """Advance on non-existent session returns 404."""
    course = await client.post("/courses", json={"title": "复习测试"})
    course_id = course.json()["id"]

    resp = await client.post(
        f"/courses/{course_id}/review/session/rs_nonexistent/advance"
    )
    assert resp.status_code == 404


async def test_review_answer_not_in_attempt(client):
    """Submit answer when not in attempt step returns 404 or 400."""
    course = await client.post("/courses", json={"title": "复习测试"})
    course_id = course.json()["id"]

    resp = await client.post(
        f"/courses/{course_id}/review/session/rs_nonexistent/answer",
        json={"answer": "test"},
    )
    assert resp.status_code in (400, 404)


async def test_review_observations_empty(client):
    """GET observations returns empty list for new course."""
    course = await client.post("/courses", json={"title": "复习测试"})
    course_id = course.json()["id"]

    resp = await client.get(f"/courses/{course_id}/review/observations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["observations"] == []
    assert data["total"] == 0


async def test_review_complete_nonexistent(client):
    """Complete non-existent session returns 400."""
    course = await client.post("/courses", json={"title": "复习测试"})
    course_id = course.json()["id"]

    resp = await client.post(
        f"/courses/{course_id}/review/session/rs_nonexistent/complete"
    )
    assert resp.status_code == 400


async def test_review_cancel_nonexistent(client):
    """Cancel non-existent session returns 404."""
    course = await client.post("/courses", json={"title": "复习测试"})
    course_id = course.json()["id"]

    resp = await client.delete(
        f"/courses/{course_id}/review/session/rs_nonexistent"
    )
    assert resp.status_code == 404


async def test_review_btw_no_session(client):
    """/btw returns 404 when no active session."""
    course = await client.post("/courses", json={"title": "复习测试"})
    course_id = course.json()["id"]

    resp = await client.post(
        f"/courses/{course_id}/review/session/rs_nonexistent/btw",
        json={"question": "test question"},
    )
    assert resp.status_code == 404
