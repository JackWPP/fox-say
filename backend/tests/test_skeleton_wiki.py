"""generate_skeleton_from_wiki 测试。"""

import json

import pytest

from app.schemas.foxsay import CourseIndex, CourseIndexChapter
from app.services.skeleton import generate_skeleton_from_wiki


class _FakeStore:
    """最小的 store fake,只实现 generate_skeleton_from_wiki 用到的 2 个方法。"""

    def __init__(self, course_index: str | None, chapter_wikis: list = None):
        self._course_index = course_index
        self._chapter_wikis = chapter_wikis or []

    def get_course_index(self, course_id: str) -> str | None:
        return self._course_index

    def get_chapter_wikis_by_course(self, course_id: str) -> list:
        return list(self._chapter_wikis)


@pytest.mark.asyncio
async def test_generate_skeleton_from_wiki_no_index():
    """store.get_course_index 返回 None → 函数返回 None。"""
    store = _FakeStore(course_index=None)
    result = await generate_skeleton_from_wiki("course-x", store)
    assert result is None


@pytest.mark.asyncio
async def test_generate_skeleton_from_wiki_bad_json():
    """course_index 解析失败 → 返回 None(不抛)。"""
    store = _FakeStore(course_index="not valid json {{{")
    result = await generate_skeleton_from_wiki("course-x", store)
    assert result is None


@pytest.mark.asyncio
async def test_generate_skeleton_from_wiki_empty_chapters():
    """chapters 为空 → 返回 None。"""
    ci = CourseIndex(course_id="c1", course_name="空", chapters=[]).model_dump_json()
    store = _FakeStore(course_index=ci)
    result = await generate_skeleton_from_wiki("c1", store)
    assert result is None


@pytest.mark.asyncio
async def test_generate_skeleton_from_wiki_with_index():
    """构造一个 CourseIndex 写入 store,验证函数返回 CourseSkeleton 包含对应 chapters。"""
    ci = CourseIndex(
        course_id="course-wiki-1",
        course_name="微积分",
        core_topics=["极限", "导数"],
        chapters=[
            CourseIndexChapter(
                id="ch-1", title="第一章", importance="high", key_concepts=["极限"], depends_on=[]
            ),
            CourseIndexChapter(
                id="ch-2", title="第二章", importance="high", key_concepts=["导数"], depends_on=["ch-1"]
            ),
        ],
    )
    store = _FakeStore(course_index=ci.model_dump_json())
    result = await generate_skeleton_from_wiki("course-wiki-1", store)
    assert result is not None
    assert result.course_id == "course-wiki-1"
    assert len(result.chapters) == 2
    assert result.chapters[0].title == "第一章"
    assert "极限" in result.chapters[0].key_concepts
    assert result.core_concepts == ["极限", "导数"]
    # prereq chain: ch-2 depends on ch-1
    assert ["ch-1", "ch-2"] in result.prerequisite_chain
