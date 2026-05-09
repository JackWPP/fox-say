import pytest
from httpx import ASGITransport, AsyncClient

from app.api.courses import course_store
from app.api.skeleton import skeleton_store
from app.main import app
from app.schemas.foxsay import Course, CourseSkeleton, CourseSkeletonChapter
from app.services.knowledge_graph import KnowledgeGraph


@pytest.fixture(autouse=True)
def _clean_stores():
    KnowledgeGraph.clear()
    yield
    KnowledgeGraph.clear()


class TestKnowledgeGraph:
    def test_add_concept(self):
        kg = KnowledgeGraph.for_course("test-kg-1")
        kg.add_concept("conv", label="卷积", metadata={"chapter": "ch1"})
        assert "conv" in kg._graph.nodes
        assert kg._graph.nodes["conv"]["label"] == "卷积"

    def test_add_dependency(self):
        kg = KnowledgeGraph.for_course("test-kg-2")
        kg.add_concept("linear", label="线性代数")
        kg.add_concept("conv", label="卷积")
        kg.add_dependency("linear", "conv")
        assert ("linear", "conv") in kg._graph.edges

    def test_get_prerequisite_chain(self):
        kg = KnowledgeGraph.for_course("test-kg-3")
        kg.add_concept("a", label="A")
        kg.add_concept("b", label="B")
        kg.add_concept("c", label="C")
        kg.add_dependency("a", "b")
        kg.add_dependency("b", "c")
        chain = kg.get_prerequisite_chain()
        assert ("a", "b") in chain
        assert ("b", "c") in chain

    def test_get_difficulty_areas(self):
        kg = KnowledgeGraph.for_course("test-kg-4")
        kg.add_concept("a", label="A")
        kg.add_concept("b", label="B")
        kg.add_concept("c", label="C")
        kg.add_dependency("a", "c")
        kg.add_dependency("b", "c")
        areas = kg.get_difficulty_areas()
        assert areas[0] == "c"
        assert len(areas) == 1

    def test_to_skeleton(self):
        kg = KnowledgeGraph.for_course("test-kg-5")
        kg.add_concept("a", label="微积分")
        kg.add_concept("b", label="线性代数")
        kg.add_dependency("b", "a")
        chapters_data = [
            {"id": "ch-1", "title": "微积分基础", "key_concepts": ["微积分"], "importance": "high", "exam_weight": 0.6},
            {"id": "ch-2", "title": "线性代数", "key_concepts": ["线性代数"], "importance": "medium", "exam_weight": 0.4},
        ]
        skeleton = kg.to_skeleton("course-1", chapters_data)
        assert skeleton.course_id == "course-1"
        assert len(skeleton.chapters) == 2
        assert skeleton.chapters[0].title == "微积分基础"
        assert "微积分" in skeleton.core_concepts
        assert "a" in skeleton.difficulty_areas
        assert ["b", "a"] in skeleton.prerequisite_chain

    def test_course_isolation(self):
        kg1 = KnowledgeGraph.for_course("iso-1")
        kg2 = KnowledgeGraph.for_course("iso-2")
        kg1.add_concept("x", label="X")
        assert "x" not in kg2._graph.nodes


@pytest.mark.asyncio
async def test_get_skeleton_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/courses/nonexistent-course/skeleton")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_skeleton_cached():
    course = Course(id="skeleton-test-1", title="测试课程", status="ready")
    course_store.create(course.id, course)

    skeleton = CourseSkeleton(
        course_id="skeleton-test-1",
        chapters=[
            CourseSkeletonChapter(id="ch-1", title="第一章", key_concepts=["概念A"], importance="high", exam_weight=0.5),
        ],
        core_concepts=["概念A"],
        difficulty_areas=[],
        prerequisite_chain=[],
    )
    skeleton_store.create("skeleton-test-1", skeleton)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/courses/skeleton-test-1/skeleton")
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_id"] == "skeleton-test-1"
        assert len(data["chapters"]) == 1
        assert data["chapters"][0]["title"] == "第一章"

    course_store._data.pop("skeleton-test-1", None)
    skeleton_store._data.pop("skeleton-test-1", None)
