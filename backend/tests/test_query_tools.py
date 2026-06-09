"""query_tools 单元测试(纯 mock store, 不调 LLM / embedding)。

覆盖:
- 显式 course_id 校验(HEC-6):跨课程的概念/章节必须被拒
- 缺失数据容错:返回结构化 JSON note, 不抛异常
- follow_prerequisite BFS 基本链
- get_source_content DMAP 查找
"""

from __future__ import annotations

import json
from typing import Any

from app.schemas.foxsay import (
    ChapterWiki,
    DMAP,
    DMAPElement,
    DMAPNode,
    KC,
    KCSourceRef,
)
from app.services import query_tools
from app.services.dmap import build_dmap


# ---------------------------------------------------------------------------
# Mock store
# ---------------------------------------------------------------------------


class _MockStore:
    """最小可用的 mock, 只实现 query_tools 用到的方法。"""

    def __init__(self) -> None:
        self.kcs: dict[str, KC] = {}
        self.chapters: dict[str, ChapterWiki] = {}
        self.course_index: str | None = None
        self.dmap_json: str | None = None

    # course_indices
    def get_course_index(self, course_id: str) -> str | None:
        return self.course_index

    # wiki_kcs
    def get_kc(self, kc_id: str) -> KC | None:
        return self.kcs.get(kc_id)

    def search_kcs_by_name(self, course_id: str, name: str) -> list[KC]:
        return [kc for kc in self.kcs.values() if kc.name == name and kc.course_id == course_id]

    # wiki_chapters
    def get_chapter_wiki(self, chapter_id: str) -> ChapterWiki | None:
        return self.chapters.get(chapter_id)

    # dmaps
    def get_dmap(self, course_id: str) -> str | None:
        return self.dmap_json


def _make_kc(kc_id: str, course_id: str, name: str = "X", **kwargs: Any) -> KC:
    return KC(id=kc_id, course_id=course_id, name=name, **kwargs)


def _make_chapter(chapter_id: str, course_id: str, title: str = "T") -> ChapterWiki:
    return ChapterWiki(id=chapter_id, course_id=course_id, chapter_id=chapter_id, title=title)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_course_map_no_index():
    """store.get_course_index 返回 None → 返回 "课程索引尚未生成" 的 JSON。"""
    store = _MockStore()
    out = query_tools.get_course_map("c1", store)
    data = json.loads(out)
    assert data == {"note": "课程索引尚未生成"}


def test_get_course_map_with_index():
    """正常 markdown 内容原样返回。"""
    store = _MockStore()
    store.course_index = "# 课程索引\n..."
    out = query_tools.get_course_map("c1", store)
    assert out == "# 课程索引\n..."


def test_get_concept_course_id_mismatch():
    """构造 KC course_id="A", 调 get_concept(course_id="B", concept_id) → "不属于课程 B"。"""
    store = _MockStore()
    store.kcs["k1"] = _make_kc("k1", course_id="A", name="极限")
    out = query_tools.get_concept("B", "k1", store)
    data = json.loads(out)
    assert "不属于课程 B" in data["note"]


def test_get_concept_not_found():
    """KC 不存在 → 返回 note。"""
    store = _MockStore()
    out = query_tools.get_concept("c1", "nope", store)
    data = json.loads(out)
    assert "未找到" in data["note"]


def test_get_concept_success():
    """course_id 匹配 → 返 KC 完整 model_dump。"""
    store = _MockStore()
    kc = _make_kc("k1", course_id="c1", name="极限", definition="趋近行为")
    store.kcs["k1"] = kc
    out = query_tools.get_concept("c1", "k1", store)
    data = json.loads(out)
    assert data["id"] == "k1"
    assert data["course_id"] == "c1"
    assert data["definition"] == "趋近行为"


def test_get_chapter_outline_course_id_mismatch():
    """ChapterWiki course_id 错配 → 拒。"""
    store = _MockStore()
    store.chapters["ch-1"] = _make_chapter("ch-1", course_id="A")
    out = query_tools.get_chapter_outline("B", "ch-1", store)
    data = json.loads(out)
    assert "不属于课程 B" in data["note"]


def test_get_chapter_outline_not_found():
    store = _MockStore()
    out = query_tools.get_chapter_outline("c1", "nope", store)
    data = json.loads(out)
    assert "未找到章节" in data["note"]


def test_follow_prerequisite_no_store():
    """store=None → 返回空 prerequisites 数组。"""
    out = query_tools.follow_prerequisite("c1", "k1", 2, store=None)
    data = json.loads(out)
    assert data == {"prerequisites": []}


def test_follow_prerequisite_basic():
    """A 依赖 "B", 构造 B 也在同课程 → 跟随 1 步应找到 B。"""
    store = _MockStore()
    a = _make_kc("a", course_id="c1", name="A", prerequisites=["B"])
    b = _make_kc("b", course_id="c1", name="B", definition="b def")
    store.kcs["a"] = a
    store.kcs["b"] = b
    out = query_tools.follow_prerequisite("c1", "a", depth=2, store=store)
    data = json.loads(out)
    names = [p["name"] for p in data["prerequisites"]]
    assert "B" in names


def test_follow_prerequisite_cycle_safe():
    """A 依赖 B, B 依赖 A → visited 集合阻止死循环。"""
    store = _MockStore()
    a = _make_kc("a", course_id="c1", name="A", prerequisites=["B"])
    b = _make_kc("b", course_id="c1", name="B", prerequisites=["A"])
    store.kcs["a"] = a
    store.kcs["b"] = b
    out = query_tools.follow_prerequisite("c1", "a", depth=5, store=store)
    data = json.loads(out)
    # 至少能跑完不挂, 不会无限循环
    assert isinstance(data["prerequisites"], list)


def test_follow_prerequisite_new_structure():
    """PR0 新增:覆盖结构化 KCPrerequisite 路径 (line A 完成后场景)。

    A 的 prerequisites 是 [KCPrerequisite(prerequisite_kc_id="b", ...)],
    follow_prerequisite 应通过 store.get_kc("b") 直接拿到 B,无需模糊搜索。
    """
    from app.schemas.foxsay import KCPrerequisite

    store = _MockStore()
    a = _make_kc(
        "a",
        course_id="c1",
        name="A",
        prerequisites=[
            KCPrerequisite(prerequisite_kc_id="b", dependency_strength=0.9, source="etl_judge_reviewed"),
        ],
    )
    b = _make_kc("b", course_id="c1", name="B", definition="b def")
    store.kcs["a"] = a
    store.kcs["b"] = b
    out = query_tools.follow_prerequisite("c1", "a", depth=2, store=store)
    data = json.loads(out)
    names = [p["name"] for p in data["prerequisites"]]
    assert "B" in names


def test_follow_prerequisite_mixed_old_and_new():
    """A 同时挂 prerequisites_raw=["B"] 和 prerequisites=[KCP(c)] → 两个都应找到。

    模拟 line A ETL 已部分对齐的中间状态:有些 prereq 已结构化,
    有些还停留在字符串。两条路径都要 work。
    """
    from app.schemas.foxsay import KCPrerequisite

    store = _MockStore()
    a = _make_kc(
        "a",
        course_id="c1",
        name="A",
        prerequisites=[
            KCPrerequisite(prerequisite_kc_id="c", dependency_strength=1.0),
        ],
        prerequisites_raw=["B"],
    )
    b = _make_kc("b", course_id="c1", name="B", definition="b def")
    c = _make_kc("c", course_id="c1", name="C", definition="c def")
    store.kcs["a"] = a
    store.kcs["b"] = b
    store.kcs["c"] = c
    out = query_tools.follow_prerequisite("c1", "a", depth=2, store=store)
    data = json.loads(out)
    names = {p["name"] for p in data["prerequisites"]}
    assert names == {"B", "C"}


def test_get_source_content_no_dmap():
    """store.get_dmap 返回 None → 返回 "DMAP 未找到"。"""
    store = _MockStore()
    out = query_tools.get_source_content("c1", "ch-1", store)
    data = json.loads(out)
    assert data == {"note": "DMAP 未找到"}


def test_get_source_content_node_found():
    """按 chapter node id 拿原始材料。"""
    chunks = [
        {"text": "第一章 绪论", "heading": "第一章", "level": 1, "page": 1},
        {"text": "微积分基础内容。", "heading": "第一章", "level": 0, "page": 1},
    ]
    dmap = build_dmap("c1", chunks, source_file="calc.pdf")
    store = _MockStore()
    store.dmap_json = dmap.model_dump_json()
    out = query_tools.get_source_content("c1", "ch-1", store)
    data = json.loads(out)
    assert "微积分基础内容" in data["content"]


def test_get_source_content_element_not_found():
    """合法 dmap 但 element id 不存在 → 返回 note。"""
    chunks = [
        {"text": "第一章 绪论", "heading": "第一章", "level": 1, "page": 1},
        {"text": "内容。", "heading": "第一章", "level": 0, "page": 1},
    ]
    dmap = build_dmap("c1", chunks)
    store = _MockStore()
    store.dmap_json = dmap.model_dump_json()
    out = query_tools.get_source_content("c1", "el-9999", store)
    data = json.loads(out)
    assert "未找到" in data["note"]
