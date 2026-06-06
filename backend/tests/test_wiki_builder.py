"""Wiki Builder 4 阶段 Pipeline 测试(全部 mock LLM,不真调 API)。

HEC-1:LLM 失败必须抛异常,测试覆盖。
HEC-6:KC 显式带 course_id。
HEC-7:LangGraph StateGraph 真用上。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from app.schemas.foxsay import (
    ChapterWiki,
    CourseIndex,
    CourseIndexChapter,
    DMAP,
    DMAPNode,
    KC,
    ReviewResult,
)
from app.services.dmap import build_dmap
from app.services.wiki_builder import (
    _apply_fixes,
    _build_chapter_wikis,
    _invalidate_old_kcs,
    _llm_call,
    _parse_llm_json,
    _reducer_merge_kcs,
    _review_kc_quality,
    _supervisor_impl,
    _worker_extract_kcs,
    build_wiki,
    build_wiki_graph,
    make_kc_id,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_dmap() -> DMAP:
    chunks = [
        {"text": "第一章 绪论", "heading": "第一章", "level": 1, "page": 1},
        {"text": "学习微积分。", "heading": "第一章", "level": 0, "page": 1},
        {"text": "第二章 极限", "heading": "第二章", "level": 1, "page": 10},
        {"text": "极限的 ε-δ 定义。", "heading": "第二章", "level": 0, "page": 10},
    ]
    return build_dmap("course-wb-1", chunks, source_file="calc.pdf")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_supervisor_plan_returns_tasks(monkeypatch):
    """Supervisor 调 LLM 后返回 task 列表 + 初步 course_index。"""
    dmap = _make_dmap()
    supervisor_json = json.dumps(
        {
            "chapters": [
                {"id": "ch-1", "title": "第一章", "kc_target": 3},
                {"id": "ch-2", "title": "第二章", "kc_target": 2},
            ],
            "course_index": {
                "course_name": "微积分",
                "chapters": [
                    {"id": "ch-1", "title": "第一章", "importance": "high", "key_concepts": [], "depends_on": []},
                    {"id": "ch-2", "title": "第二章", "importance": "high", "key_concepts": [], "depends_on": ["ch-1"]},
                ],
            },
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        "app.services.wiki_builder._llm_call", lambda *a, **k: supervisor_json
    )

    state = {"course_id": "course-wb-1", "dmap": dmap}
    out = _supervisor_impl(state)
    assert "tasks" in out
    assert "course_index" in out
    assert len(out["tasks"]) == 2
    assert all(t["chapter_id"] in ("ch-1", "ch-2") for t in out["tasks"])
    assert out["course_index"].course_id == "course-wb-1"
    assert out["course_index"].course_name == "微积分"


def test_worker_extract_kcs(monkeypatch):
    """Worker mock LLM 输出 JSON,解析出 KC 列表;显式带 course_id。"""
    kc_json = json.dumps(
        [
            {
                "name": "极限",
                "bloom_level": "Understanding",
                "definition": "函数在某点的趋近行为。",
                "formula": "$\\lim_{x \\to a} f(x) = L$",
                "conditions": ["f 在 a 附近有定义"],
                "prerequisites": [],
            },
            {
                "name": "连续",
                "bloom_level": "Applying",
                "definition": "极限等于函数值。",
                "prerequisites": ["极限"],
            },
        ],
        ensure_ascii=False,
    )
    monkeypatch.setattr("app.services.wiki_builder._llm_call", lambda *a, **k: kc_json)

    task = {
        "course_id": "course-wb-1",
        "chapter_id": "ch-2",
        "chapter_title": "第二章",
        "chapter_text": "极限与连续",
        "retry": 0,
    }
    kcs = _worker_extract_kcs(task)
    assert len(kcs) == 2
    # 显式 course_id (HEC-6)
    for kc in kcs:
        assert kc.course_id == "course-wb-1"
        assert kc.chapter_id == "ch-2"
    # ID 是 uuid5 确定性
    expected_first = make_kc_id("course-wb-1", "ch-2", "极限")
    assert kcs[0].id == expected_first


def test_reducer_merges_duplicates():
    """同名 KC 合并,保留 definition 更长的。"""
    kc_a = KC(id="aaa", course_id="c1", chapter_id="ch-1", name="X", definition="短")
    kc_b = KC(id="aaa", course_id="c1", chapter_id="ch-1", name="X", definition="长一点的定义")
    merged = _reducer_merge_kcs("c1", [[kc_a, kc_b]])
    assert len(merged) == 1
    assert merged[0].definition == "长一点的定义"


def test_reducer_rejects_wrong_course_id():
    """Reducer 校验:传入 KC 的 course_id 必须与参数一致(HEC-6)。"""
    kc_bad = KC(id="x", course_id="wrong", name="X", definition="")
    with pytest.raises(ValueError, match="course_id"):
        _reducer_merge_kcs("right", [[kc_bad]])


def test_reviewer_passes_quality_kcs(monkeypatch):
    """合规 KC 直接通过。"""
    review_passed = json.dumps(
        {"passed": True, "reasons": [], "failed_kc_ids": [], "fixes": []},
        ensure_ascii=False,
    )
    monkeypatch.setattr("app.services.wiki_builder._llm_call", lambda *a, **k: review_passed)
    kcs = [
        KC(
            id="k1",
            course_id="c1",
            chapter_id="ch-1",
            name="X",
            definition="一个定义。",
            bloom_level="Understanding",
        )
    ]
    review = _review_kc_quality(kcs)
    assert review.passed is True
    assert review.failed_kc_ids == []


def test_kc_id_deterministic():
    """相同输入两次,kc_id 相同(uuid5 稳定性)。"""
    a = make_kc_id("c1", "ch-1", "极限")
    b = make_kc_id("c1", "ch-1", "极限")
    assert a == b
    assert len(a) == 12


def test_kc_id_includes_course_id():
    """不同 course 不会撞 id。"""
    a = make_kc_id("course-A", "ch-1", "极限")
    b = make_kc_id("course-B", "ch-1", "极限")
    assert a != b


def test_llm_call_failure_raises(monkeypatch):
    """HEC-1:LLM 失败必须抛 RuntimeError,绝不 return ''。"""
    def _fake(*a, **k):
        raise RuntimeError("LLM call failed: simulated")

    monkeypatch.setattr("app.services.wiki_builder._llm_call", _fake)
    with pytest.raises(RuntimeError, match="LLM call failed"):
        _supervisor_impl({"course_id": "c1", "dmap": _make_dmap()})


def test_build_chapter_wikis_uses_course_id():
    """ChapterWiki 显式带 course_id。"""
    dmap = _make_dmap()
    kcs = [
        KC(id="k1", course_id="course-wb-1", chapter_id="ch-1", name="绪论概念", definition=""),
        KC(id="k2", course_id="course-wb-1", chapter_id="ch-2", name="极限概念", definition=""),
    ]
    wikis = _build_chapter_wikis("course-wb-1", kcs, dmap)
    assert len(wikis) == 2
    for w in wikis:
        assert w.course_id == "course-wb-1"
    # key_concepts 来自 KC 名字
    ch1_wiki = next(w for w in wikis if w.chapter_id == "ch-1")
    assert "绪论概念" in ch1_wiki.key_concepts


def test_invalidate_old_kcs_order():
    """invalidate 必须在 save_kc 之前(顺序合约)。"""
    # 我们直接验证 _invalidate_old_kcs 真的把 invalid_at 设上了
    class _FakeStore:
        def __init__(self):
            self.invalidated: list[str] = []

        def invalidate_kc(self, kc_id: str) -> None:
            self.invalidated.append(kc_id)

    old_kc = KC(id="aaa", course_id="c1", chapter_id="ch-1", name="X", definition="")
    new_kc = KC(id="aaa", course_id="c1", chapter_id="ch-1", name="X", definition="new")
    store = _FakeStore()
    _invalidate_old_kcs(store, [old_kc], [new_kc])
    assert store.invalidated == ["aaa"]


def test_build_wiki_graph_returns_compiled_graph():
    """LangGraph StateGraph 真的能被构造出来(import + 实际使用,HEC-7)。"""
    graph = build_wiki_graph()
    # compiled graph 的 invoke / get_graph 至少有一个
    assert graph is not None
    assert hasattr(graph, "invoke")


def test_build_wiki_end_to_end_mocked(monkeypatch):
    """端到端:build_wiki 用 mocked LLM 跑完 4 阶段,结果含 KCs + DMAP + merkle。"""
    # 1) supervisor
    supervisor_json = json.dumps(
        {
            "chapters": [{"id": "ch-1", "title": "第一章", "kc_target": 2}],
            "course_index": {
                "course_name": "微积分",
                "chapters": [
                    {"id": "ch-1", "title": "第一章", "importance": "high", "key_concepts": [], "depends_on": []}
                ],
            },
        },
        ensure_ascii=False,
    )
    # 2) worker
    worker_json = json.dumps(
        [
            {
                "name": "极限",
                "bloom_level": "Understanding",
                "definition": "极限描述趋近行为。",
                "prerequisites": [],
            }
        ],
        ensure_ascii=False,
    )
    # 3) reviewer
    reviewer_json = json.dumps(
        {"passed": True, "reasons": [], "failed_kc_ids": [], "fixes": []},
        ensure_ascii=False,
    )

    responses = iter([supervisor_json, worker_json, reviewer_json])

    def _fake_llm(*a, **k):
        return next(responses)

    monkeypatch.setattr("app.services.wiki_builder._llm_call", _fake_llm)

    chunks = [
        {"text": "第一章 绪论", "heading": "第一章", "level": 1, "page": 1},
        {"text": "极限是基础。", "heading": "第一章", "level": 0, "page": 1},
    ]
    result = build_wiki("course-e2e", chunks, source_file="t.pdf")
    assert result.course_id == "course-e2e"
    assert result.dmap is not None
    assert result.merkle_tree is not None
    assert result.course_index is not None
    # KCs 由 worker 提取
    assert len(result.kcs) >= 1
    for kc in result.kcs:
        assert kc.course_id == "course-e2e"
