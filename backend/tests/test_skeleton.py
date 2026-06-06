import pytest
from httpx import ASGITransport, AsyncClient

from app.schemas.foxsay import Course, CourseSkeleton, CourseSkeletonChapter


@pytest.mark.asyncio
async def test_get_skeleton_not_found(client: AsyncClient):
    resp = await client.get("/courses/nonexistent-course/skeleton")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_skeleton_cached(client: AsyncClient):
    store = client._transport.app.state.store

    course = Course(id="skeleton-test-1", title="测试课程", status="ready")
    store.create_course(course)

    skeleton = CourseSkeleton(
        course_id="skeleton-test-1",
        chapters=[
            CourseSkeletonChapter(id="ch-1", title="第一章", key_concepts=["概念A"], importance="high", exam_weight=0.5),
        ],
        core_concepts=["概念A"],
        difficulty_areas=[],
        prerequisite_chain=[],
    )
    store.create_skeleton(skeleton)

    resp = await client.get("/courses/skeleton-test-1/skeleton")
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_id"] == "skeleton-test-1"
    assert len(data["chapters"]) == 1
    assert data["chapters"][0]["title"] == "第一章"


@pytest.mark.asyncio
async def test_skeleton_no_kg_fallback():
    """在没有 KG 的情况下,generate_skeleton 应仍能从纯文本生成骨架。"""
    from app.services.skeleton import generate_skeleton
    materials = "第一章 微积分基础。导数是变化率。第二章 线性代数。向量空间。"
    skeleton = await generate_skeleton(
        course_id="no-kg-course",
        course_title="测试课程",
        materials_text=materials,
    )
    assert skeleton.course_id == "no-kg-course"
    assert isinstance(skeleton.chapters, list)
