from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.schemas.foxsay import CourseSkeleton, CourseSkeletonChapter, ReviewPlan


def _setup_course_with_skeleton(
    store,
    course_id: str = "review-test-1",
    title: str = "高等数学",
    exam_date: str = "2026-07-01",
) -> None:
    from app.schemas.foxsay import Course

    course = Course(id=course_id, title=title, status="ready", exam_date=exam_date)
    store.create_course(course)

    skeleton = CourseSkeleton(
        course_id=course_id,
        chapters=[
            CourseSkeletonChapter(
                id="ch-1", title="微积分基础", key_concepts=["极限", "导数"],
                importance="high", exam_weight=0.6,
            ),
            CourseSkeletonChapter(
                id="ch-2", title="线性代数", key_concepts=["矩阵", "向量"],
                importance="medium", exam_weight=0.4,
            ),
        ],
        core_concepts=["极限", "导数", "矩阵"],
        difficulty_areas=["多元微积分"],
        prerequisite_chain=[],
    )
    store.create_skeleton(skeleton)


@pytest.mark.asyncio
async def test_create_review_plan(client: AsyncClient):
    store = client._transport.app.state.store
    _setup_course_with_skeleton(store)

    with patch("app.services.review._llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = ReviewPlan(
            course_id="review-test-1",
            remaining_days=53,
            daily_plan=[
                {"day_index": 1, "focus": "微积分基础", "suggested_minutes": 90, "priority": "high"},
                {"day_index": 2, "focus": "线性代数", "suggested_minutes": 60, "priority": "medium"},
            ],
            likely_exam_points=["极限", "导数"],
            weak_areas=["多元微积分"],
        )

        resp = await client.post("/courses/review-test-1/review-plan", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_id"] == "review-test-1"
        assert len(data["daily_plan"]) == 2
        assert data["daily_plan"][0]["focus"] == "微积分基础"
        assert data["likely_exam_points"] == ["极限", "导数"]
        assert data["weak_areas"] == ["多元微积分"]


@pytest.mark.asyncio
async def test_create_review_plan_with_override_exam_date(client: AsyncClient):
    store = client._transport.app.state.store
    _setup_course_with_skeleton(store)

    with patch("app.services.review._llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = ReviewPlan(
            course_id="review-test-1",
            remaining_days=30,
            daily_plan=[
                {"day_index": 1, "focus": "微积分", "suggested_minutes": 90, "priority": "high"},
            ],
            likely_exam_points=[],
            weak_areas=[],
        )

        resp = await client.post("/courses/review-test-1/review-plan", json={"exam_date": "2026-06-08"})
        assert resp.status_code == 200
        assert mock_llm.call_args[0][2] == "2026-06-08"


@pytest.mark.asyncio
async def test_review_plan_course_not_found(client: AsyncClient):
    resp = await client.post("/courses/nonexistent/review-plan", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_review_plan_no_exam_date(client: AsyncClient):
    store = client._transport.app.state.store
    from app.schemas.foxsay import Course

    course = Course(id="no-exam-1", title="无考试课程", status="ready")
    store.create_course(course)

    skeleton = CourseSkeleton(
        course_id="no-exam-1",
        chapters=[
            CourseSkeletonChapter(id="ch-1", title="第一章", key_concepts=[], importance="medium", exam_weight=1.0),
        ],
        core_concepts=[],
        difficulty_areas=[],
        prerequisite_chain=[],
    )
    store.create_skeleton(skeleton)

    resp = await client.post("/courses/no-exam-1/review-plan", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_btw_interjection(client: AsyncClient):
    store = client._transport.app.state.store
    _setup_course_with_skeleton(store)

    plan = ReviewPlan(
        course_id="review-test-1",
        remaining_days=53,
        daily_plan=[
            {"day_index": 1, "focus": "微积分基础", "suggested_minutes": 90, "priority": "high"},
        ],
        likely_exam_points=[],
        weak_areas=[],
    )
    store.create_review_plan(plan)

    with patch("app.api.review.ask", new_callable=AsyncMock) as mock_ask:
        from app.schemas.foxsay import CragAnswer, Citation

        mock_ask.return_value = CragAnswer(
            course_id="review-test-1",
            answer="极限是函数趋近的值。来自 notes.pdf · 第1部分",
            citations=[Citation(file_name="notes.pdf", locator="第1部分")],
            confidence_status="grounded",
            relevance_score=0.85,
        )

        resp = await client.post("/courses/review-test-1/btw", json={"question": "什么是极限"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_id"] == "review-test-1"
        assert data["question"] == "什么是极限"
        assert data["answer"]["confidence_status"] == "grounded"
        assert data["returns_to_review_step_id"] == "day-1"


@pytest.mark.asyncio
async def test_btw_with_current_step_id(client: AsyncClient):
    store = client._transport.app.state.store
    _setup_course_with_skeleton(store)

    with patch("app.api.review.ask", new_callable=AsyncMock) as mock_ask:
        from app.schemas.foxsay import CragAnswer, Citation

        mock_ask.return_value = CragAnswer(
            course_id="review-test-1",
            answer="导数是变化率。来自 notes.pdf · 第2部分",
            citations=[Citation(file_name="notes.pdf", locator="第2部分")],
            confidence_status="grounded",
            relevance_score=0.90,
        )

        resp = await client.post("/courses/review-test-1/btw", json={"question": "什么是导数", "current_step_id": "day-3"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["returns_to_review_step_id"] == "day-3"


@pytest.mark.asyncio
async def test_btw_course_not_found(client: AsyncClient):
    resp = await client.post("/courses/nonexistent/btw", json={"question": "test"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fallback_generate():
    from app.services.review import _fallback_generate

    skeleton = CourseSkeleton(
        course_id="fallback-test",
        chapters=[
            CourseSkeletonChapter(id="ch-1", title="A", key_concepts=[], importance="high", exam_weight=0.7),
            CourseSkeletonChapter(id="ch-2", title="B", key_concepts=[], importance="low", exam_weight=0.3),
        ],
        core_concepts=[],
        difficulty_areas=["难点1"],
        prerequisite_chain=[],
    )

    plan = _fallback_generate("fallback-test", 5, skeleton)
    assert plan.course_id == "fallback-test"
    assert plan.remaining_days == 5
    assert len(plan.daily_plan) <= 5
    assert plan.weak_areas == ["难点1"]
    assert "A" in plan.likely_exam_points
