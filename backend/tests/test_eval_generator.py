"""Generator 测试:覆盖 30 题分布 / KC=0 fallback / 单题生成。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 把 project root 加进 sys.path,这样能 import backend.eval
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.schemas.foxsay import Citation, KC

from backend.eval.generator import (
    DEFAULT_DISTRIBUTION,
    _coerce_bloom,
    _extract_json,
    _normalize_case_id,
    generate_one,
    generate_suite,
)
from backend.eval.schemas import EvalCase, PilotSuite


# ---------------------------------------------------------------------------
# 1. 30 题分布
# ---------------------------------------------------------------------------


def test_default_distribution_totals_to_30():
    """8 + 10 + 5 + 4 + 3 = 30。"""
    assert sum(DEFAULT_DISTRIBUTION.values()) == 30
    assert DEFAULT_DISTRIBUTION["definition"] == 8
    assert DEFAULT_DISTRIBUTION["derivation"] == 10
    assert DEFAULT_DISTRIBUTION["cross_chapter"] == 5
    assert DEFAULT_DISTRIBUTION["refusal"] == 4
    assert DEFAULT_DISTRIBUTION["ambiguous"] == 3


def test_generate_suite_with_mock_llm_returns_30_cases():
    """用 mock llm_call 直接产出 30 条,不走 DeepSeek。"""

    def mock_llm(system: str, user: str) -> str:
        # 解析 user 抓题型
        if "题型: definition" in user:
            qtype = "definition"
        elif "题型: derivation" in user:
            qtype = "derivation"
        elif "题型: cross_chapter" in user:
            qtype = "cross_chapter"
        elif "题型: refusal" in user:
            qtype = "refusal"
        elif "题型: ambiguous" in user:
            qtype = "ambiguous"
        else:
            qtype = "definition"
        obj = {
            "case_id": f"FAKE-{qtype.upper()}-999",
            "question": f"mock 问题 {qtype}",
            "question_type": qtype,
            "associated_kc_id": None,
            "bloom_level": "Understanding",
            "gold_answer": "这是一个非常具体的标准答案,长度超过 50 个字符,涵盖要点。",
            "gold_citations": [{"file_name": "mock.pdf", "locator": "第一部分"}],
            "answerability": qtype != "refusal",
        }
        return json.dumps(obj, ensure_ascii=False)

    suite = generate_suite(
        course_id="test-course",
        course_title="测试课",
        kcs=[],
        llm_call=mock_llm,
    )
    assert isinstance(suite, PilotSuite)
    assert len(suite.cases) == 30
    # 分布校验
    by_type = {}
    for c in suite.cases:
        by_type.setdefault(c.eval_case.question_type, 0)
        by_type[c.eval_case.question_type] += 1
    # KC=0 时 refusal +4 → 8 题拒答
    assert by_type["refusal"] == 8
    # 其它题型按 default - refusal 增量的 -4 平移到 derivation
    assert by_type["definition"] == 8
    assert by_type["derivation"] == 6
    assert by_type["cross_chapter"] == 5
    assert by_type["ambiguous"] == 3


def test_generate_suite_kc_present_keeps_default_distribution():
    """有 KC 时,分布严格按 DEFAULT_DISTRIBUTION。"""

    def mock_llm(system: str, user: str) -> str:
        return json.dumps({
            "case_id": "X-DEF-001",
            "question": "Q",
            "question_type": "definition",
            "associated_kc_id": "kc_a",
            "bloom_level": "Understanding",
            "gold_answer": "A" * 60,
            "gold_citations": [{"file_name": "f.pdf", "locator": "p1"}],
            "answerability": True,
        }, ensure_ascii=False)

    kcs = [KC(id="kc_a", course_id="t", name="alpha")]
    suite = generate_suite(
        course_id="t",
        course_title="T",
        kcs=kcs,
        llm_call=mock_llm,
    )
    assert len(suite.cases) == 30
    types = [c.eval_case.question_type for c in suite.cases]
    assert types.count("refusal") == 4  # 没扩


# ---------------------------------------------------------------------------
# 2. 工具函数
# ---------------------------------------------------------------------------


def test_extract_json_handles_markdown_fence():
    raw = "```json\n{\"a\": 1, \"b\": 2}\n```"
    data = _extract_json(raw)
    assert data == {"a": 1, "b": 2}


def test_extract_json_handles_plain():
    raw = '{"a": 1}'
    assert _extract_json(raw) == {"a": 1}


def test_extract_json_handles_garbage_around():
    raw = '前缀文字 {"a": 1, "b": [2, 3]} 后缀'
    assert _extract_json(raw) == {"a": 1, "b": [2, 3]}


def test_coerce_bloom_normalizes_variants():
    assert _coerce_bloom("apply") == "Applying"
    assert _coerce_bloom("analyze") == "Analyzing"
    assert _coerce_bloom("remember") == "Remembering"
    assert _coerce_bloom("") == "Understanding"  # 默认
    assert _coerce_bloom("Evaluating") == "Evaluating"  # 已规范


def test_normalize_case_id_fills_when_missing():
    out = _normalize_case_id("", "linear-algebra", "definition", 7)
    assert out == "LINEAR-DEF-007"
    # 已合法就原样返回
    assert _normalize_case_id("LA-DEF-001", "x", "definition", 99) == "LA-DEF-001"


# ---------------------------------------------------------------------------
# 3. 单题生成 — 强 schema 校验
# ---------------------------------------------------------------------------


def test_generate_one_handles_malformed_llm_output_with_fallback():
    """LLM 输出乱码时,generator 内部应不抛 — 但 generate_one 会抛。
    测试兜底逻辑在 generate_suite 那一层(用 try/except)。"""

    def bad_llm(system: str, user: str) -> str:
        return "this is not json at all"

    kcs = [KC(id="kc_a", course_id="t", name="alpha")]
    with pytest.raises(Exception):
        generate_one(
            course_id="t",
            course_title="T",
            qtype="definition",
            kcs=kcs,
            seq=1,
            llm_call=bad_llm,
        )


def test_generate_suite_swallows_bad_cases():
    """generate_suite 对每题用 try/except 兜底,30 题必须能产出 30 条。"""
    call_count = {"n": 0}

    def flaky_llm(system: str, user: str) -> str:
        call_count["n"] += 1
        if call_count["n"] % 5 == 0:
            return "not json"
        return json.dumps({
            "case_id": "OK-DEF-001",
            "question": "Q",
            "question_type": "definition",
            "associated_kc_id": None,
            "bloom_level": "Understanding",
            "gold_answer": "A" * 60,
            "gold_citations": [{"file_name": "f.pdf", "locator": "p1"}],
            "answerability": True,
        }, ensure_ascii=False)

    kcs = [KC(id="kc_a", course_id="t", name="alpha")]
    suite = generate_suite(
        course_id="t",
        course_title="T",
        kcs=kcs,
        llm_call=flaky_llm,
    )
    # 仍有 30 条(失败题被占位)
    assert len(suite.cases) == 30
    # 至少有 1 条占位 (refusal 兜底 answerability=False, gold_answer 含"超出")
    refusal_placeholders = [
        c for c in suite.cases
        if "生成失败" in c.eval_case.question
    ]
    assert len(refusal_placeholders) >= 1
