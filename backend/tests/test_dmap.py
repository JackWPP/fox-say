"""DMAP 构建测试(纯 Python,不调 LLM)。"""

import pytest

from app.services.dmap import build_dmap, extract_cross_refs
from app.schemas.foxsay import DMAP, DMAPNode


def test_build_dmap_basic():
    """2 个 heading 1 + 1 个 heading 2,验证树结构。"""
    chunks = [
        {"text": "第一章 微积分基础", "heading": "第一章", "level": 1, "page": 1},
        {"text": "导数是变化率。", "heading": "第一章", "level": 0, "page": 1},
        {"text": "1.1 极限", "heading": "1.1 极限", "level": 2, "page": 2},
        {"text": "极限的 ε-δ 定义。", "heading": "1.1 极限", "level": 0, "page": 2},
        {"text": "第二章 线性代数", "heading": "第二章", "level": 1, "page": 10},
        {"text": "向量空间定义。", "heading": "第二章", "level": 0, "page": 10},
    ]
    dmap = build_dmap("course-1", chunks, source_file="calc.pdf")

    assert isinstance(dmap, DMAP)
    assert dmap.course_id == "course-1"
    assert dmap.root.type == "course"
    # 应该有 2 个 chapter
    chapters = [c for c in dmap.root.children if c.type == "chapter"]
    assert len(chapters) == 2
    assert chapters[0].id == "ch-1"
    assert chapters[0].title == "第一章"
    assert chapters[1].id == "ch-2"
    assert chapters[1].title == "第二章"

    # 第一个 chapter 下面应该有 1 个 section(1.1 极限)
    assert len(chapters[0].children) == 1
    assert chapters[0].children[0].type == "section"
    assert chapters[0].children[0].title == "1.1 极限"

    # elements 挂到正确节点
    assert len(chapters[1].elements) == 1
    assert "向量空间" in chapters[1].elements[0].text_preview


def test_extract_cross_refs():
    """输入"见第三章",验证 cross_ref 列表。"""
    chunks = [
        {"text": "第一章 绪论", "heading": "第一章", "level": 1, "page": 1},
        {"text": "我们将在第三章讨论积分。", "heading": "第一章", "level": 0, "page": 1},
        {"text": "第三章 积分", "heading": "第三章", "level": 1, "page": 50},
        {"text": "积分定义。", "heading": "第三章", "level": 0, "page": 50},
    ]
    dmap = build_dmap("course-x", chunks)

    ch1 = dmap.root.children[0]
    assert ch1.id == "ch-1"
    # 找到 cross_refs 中有指向 ch-3 的
    refs = ch1.cross_refs
    assert any(r.target_id == "ch-3" for r in refs), f"expected ch-3 ref in {refs}"

    # ch-3 不应该指向自己
    ch3 = dmap.root.children[1]
    assert ch3.id == "ch-3"
    self_refs = [r for r in ch3.cross_refs if r.target_id == "ch-3"]
    assert len(self_refs) == 0


def test_build_dmap_empty_chunks_raises():
    """空 chunks 不算错(会得到一个空 dmap),但空 course_id 必须抛。"""
    with pytest.raises(ValueError):
        build_dmap("", [])
