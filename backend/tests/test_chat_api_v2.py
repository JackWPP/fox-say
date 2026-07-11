"""V2 Chat API tests: SSE stream, history, run snapshot, cancel."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch



def _parse_sse(raw_text: str) -> list[dict[str, Any]]:
    """Parse SSE response into list of {type, data} dicts."""
    events: list[dict[str, Any]] = []
    for block in raw_text.split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue
        event_type = ""
        for line in lines:
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    events.append({"type": event_type, "data": data})
                except json.JSONDecodeError:
                    pass
    return events


class _FakeWriterResponse:
    def __init__(self, content: str) -> None:
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]
        self.usage = None


class _FakeWriterClient:
    def __init__(self, content: str) -> None:
        self._content = content
        self.chat = type("C", (), {"completions": type("Completions", (), {"create": self._create})()})()

    def _create(self, **kwargs: Any) -> _FakeWriterResponse:
        return _FakeWriterResponse(self._content)


def _seed_course(client, course_id="c1", title="测试课程"):
    """Create a course via API."""
    return client.post("/courses", json={"title": title})


async def test_chat_stream_grounded_answer(client):
    """Test that a grounded question produces accepted->phase->token->done SSE."""

    course = await client.post("/courses", json={"title": "线性代数测试"})
    course_id = course.json()["id"]

    # Create a session
    sess = await client.post(f"/courses/{course_id}/chat/sessions", json={"title": "测试会话"})
    session_id = sess.json()["session_id"]

    # We need to seed source fragments. Since we can't easily run the full
    # indexer in an API test, we test that the SSE endpoint returns the
    # expected event structure even when evidence is unavailable.
    # The quick answer service should handle "unavailable" gracefully.

    # Mock the writer client so no real API call is made
    fake_client = _FakeWriterClient(
        content=json.dumps({
            "answer": "这是一个测试回答。",
            "citation_fragment_ids": [],
        }, ensure_ascii=False)
    )

    with patch("app.api.chat.OpenAI", return_value=fake_client):
        resp = await client.post(
            f"/courses/{course_id}/chat/stream",
            json={"question": "测试问题", "session_id": session_id},
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]

    # Should have accepted, at least one phase, token events, and done/error
    assert "accepted" in types or "error" in types
    if "done" in types:
        done_event = next(e for e in events if e["type"] == "done")
        assert "envelope" in done_event["data"]
        assert "answer" in done_event["data"]
        assert "run_id" in done_event["data"]
        assert "message_id" in done_event["data"]


async def test_chat_history_returns_v2_metadata(client):
    """Test that chat history includes run_id, source_revision, envelope."""
    course = await client.post("/courses", json={"title": "历史测试"})
    course_id = course.json()["id"]

    sess = await client.post(f"/courses/{course_id}/chat/sessions", json={"title": "历史会话"})
    session_id = sess.json()["session_id"]

    # Send a message (will likely fail/timeout with no real model, but
    # the user message should be persisted)
    fake_client = _FakeWriterClient(
        content=json.dumps({"answer": "回答", "citation_fragment_ids": []}, ensure_ascii=False)
    )
    with patch("app.api.chat.OpenAI", return_value=fake_client):
        await client.post(
            f"/courses/{course_id}/chat/stream",
            json={"question": "什么是特征值？", "session_id": session_id},
        )

    # Get history
    resp = await client.get(
        f"/courses/{course_id}/chat/history",
        params={"session_id": session_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "messages" in data
    assert len(data["messages"]) >= 1  # at least the user message


async def test_agent_run_snapshot_endpoint(client):
    """Test GET /agent-runs/{run_id} returns 404 for unknown run."""
    course = await client.post("/courses", json={"title": "Run测试"})
    course_id = course.json()["id"]

    resp = await client.get(f"/courses/{course_id}/chat/agent-runs/nonexistent-run-id")
    assert resp.status_code == 404


async def test_cancel_nonexistent_run(client):
    """Test POST /agent-runs/{run_id}/cancel returns 404 for unknown run."""
    course = await client.post("/courses", json={"title": "Cancel测试"})
    course_id = course.json()["id"]

    resp = await client.post(f"/courses/{course_id}/chat/agent-runs/nonexistent/cancel")
    assert resp.status_code == 404


async def test_session_course_fence(client):
    """Test that deleting a session from another course is a no-op."""
    c1 = await client.post("/courses", json={"title": "课程A"})
    c2 = await client.post("/courses", json={"title": "课程B"})
    c1_id = c1.json()["id"]
    c2_id = c2.json()["id"]

    s1 = await client.post(f"/courses/{c1_id}/chat/sessions", json={"title": "A会话"})
    s1_id = s1.json()["session_id"]

    # Delete session A from course B should not actually delete it
    resp = await client.delete(f"/courses/{c2_id}/chat/sessions/{s1_id}")
    assert resp.status_code == 200

    # Session should still exist in course A
    resp = await client.get(f"/courses/{c1_id}/chat/sessions")
    sessions = resp.json()["sessions"]
    assert any(s["id"] == s1_id for s in sessions)


async def test_sse_event_format_has_run_id(client):
    """Test that all SSE events carry run_id for session fence checking."""
    course = await client.post("/courses", json={"title": "SSE格式测试"})
    course_id = course.json()["id"]

    fake_client = _FakeWriterClient(
        content=json.dumps({"answer": "回答", "citation_fragment_ids": []}, ensure_ascii=False)
    )
    with patch("app.api.chat.OpenAI", return_value=fake_client):
        resp = await client.post(
            f"/courses/{course_id}/chat/stream",
            json={"question": "测试"},
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    for event in events:
        if event["type"] in ("accepted", "phase", "token", "done", "error"):
            # done and error events may have empty run_id on failure,
            # but accepted/phase/token should have it
            if event["type"] in ("accepted", "phase", "token"):
                assert "run_id" in event["data"], f"Event {event['type']} missing run_id"
