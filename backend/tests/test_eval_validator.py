"""Validator 测试:覆盖 7 规则本地校验 + LLM 校验。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.schemas.foxsay import Citation, EvalCase, KC

from backend.eval.validator import (
    _check_local_rules,
    _parse_llm_verdict,
    validate_case,
    validate_suite,
)
from backend.eval.schemas import ValidatorReport


def _make_case(**overrides) -> EvalCase:
    base = {
        "case_id": "LA-DEF-001",
        "course_id": "linear-algebra",
        "question": "什么是特征值?",
        "question_type": "definition",
        "associated_kc_id": "kc_eigen",
        "bloom_level": "Understanding",
        "gold_answer": (
            "特征值是方阵 A 满足 Av=λv 的非零标量 λ,其中 v 是特征向量。"
            "它刻画了线性变换在不同方向上的伸缩比例,是矩阵分析的核心概念。"
        ),
        "gold_citations": [{"file_name": "线性代数.pdf", "locator": "第四章"}],
        "answerability": True,
    }
    base.update(overrides)
    return EvalCase.model_validate(base)


# ---------------------------------------------------------------------------
# 1. R2 question_type ↔ answerability 一致性
# ---------------------------------------------------------------------------


def test_r2_refusal_must_be_unanswerable():
    case = _make_case(question_type="refusal", answerability=True)
    failed = _check_local_rules(case)
    assert "R2" in failed


def test_r2_definition_must_be_answerable():
    case = _make_case(question_type="definition", answerability=False)
    failed = _check_local_rules(case)
    assert "R2" in failed


def test_r2_consistent_no_fail():
    case = _make_case(question_type="definition", answerability=True)
    failed = _check_local_rules(case)
    assert "R2" not in failed


# ---------------------------------------------------------------------------
# 2. R3 拒答文案
# ---------------------------------------------------------------------------


def test_r3_unanswerable_must_have_refusal_keyword():
    case = _make_case(
        question_type="refusal",
        answerability=False,
        gold_answer="这是一个无关问题,不知道。",
    )
    failed = _check_local_rules(case)
    assert "R3" not in failed  # "不知道" 命中


def test_r3_unanswerable_missing_keyword_fails():
    case = _make_case(
        question_type="refusal",
        answerability=False,
        gold_answer="这只是一个简短答案。",
    )
    failed = _check_local_rules(case)
    assert "R3" in failed


# ---------------------------------------------------------------------------
# 3. R4 gold_answer 长度
# ---------------------------------------------------------------------------


def test_r4_answerable_definition_needs_50_chars():
    case = _make_case(
        question_type="definition",
        gold_answer="短",  # < 50
    )
    failed = _check_local_rules(case)
    assert "R4" in failed


def test_r4_ambiguous_exempt_from_length():
    case = _make_case(
        question_type="ambiguous",
        answerability=True,
        gold_answer="短",  # < 50 但 ambiguous 豁免
    )
    failed = _check_local_rules(case)
    assert "R4" not in failed


def test_r4_unanswerable_exempt_from_length():
    case = _make_case(
        question_type="refusal",
        answerability=False,
        gold_answer="短",  # < 50 但 answerability=False 豁免
    )
    failed = _check_local_rules(case)
    assert "R4" not in failed


# ---------------------------------------------------------------------------
# 4. R5 associated_kc_id 必须在 KC 列表里
# ---------------------------------------------------------------------------


def test_r5_associated_kc_must_be_in_lookup():
    kc = KC(id="kc_eigen", course_id="linear-algebra", name="特征值")
    case = _make_case(associated_kc_id="kc_eigen")
    failed = _check_local_rules(case, kc_lookup={kc.id: kc})
    assert "R5" not in failed


def test_r5_associated_kc_missing_fails():
    case = _make_case(associated_kc_id="kc_nonexistent")
    failed = _check_local_rules(case, kc_lookup={})
    assert "R5" in failed


def test_r5_associated_kc_none_skips_check():
    case = _make_case(associated_kc_id=None)
    failed = _check_local_rules(case, kc_lookup={})
    assert "R5" not in failed


# ---------------------------------------------------------------------------
# 5. R6 bloom_level
# ---------------------------------------------------------------------------


def test_r6_invalid_bloom_fails():
    # EvalCase.bloom_level 是 str,Pydantic 不限值,所以坏值会进到本地规则
    case = _make_case(bloom_level="NotABloomLevel")
    failed = _check_local_rules(case)
    assert "R6" in failed


def test_r6_valid_bloom_passes():
    for b in ("Remembering", "Understanding", "Applying",
              "Analyzing", "Evaluating", "Creating"):
        case = _make_case(bloom_level=b)
        assert "R6" not in _check_local_rules(case)


# ---------------------------------------------------------------------------
# 6. R7 citations 数量
# ---------------------------------------------------------------------------


def test_r7_cross_chapter_needs_2_citations():
    case = _make_case(
        question_type="cross_chapter",
        gold_citations=[{"file_name": "f.pdf", "locator": "p1"}],  # 只 1
    )
    failed = _check_local_rules(case)
    assert "R7" in failed


def test_r7_refusal_allows_zero_citations():
    case = _make_case(
        question_type="refusal",
        answerability=False,
        gold_citations=[],
    )
    failed = _check_local_rules(case)
    assert "R7" not in failed


# ---------------------------------------------------------------------------
# 7. validate_case 端到端 (走 LLM, 用 mock)
# ---------------------------------------------------------------------------


def test_validate_case_happy_path():
    case = _make_case()

    def mock_llm(system: str, user: str) -> str:
        return json.dumps({"verdict": "pass", "failed_rules": []})

    report = validate_case(case, llm_call=mock_llm)
    assert isinstance(report, ValidatorReport)
    assert report.verdict == "pass"
    assert report.failed_rules == []


def test_validate_case_with_local_fail_overrides_to_fail():
    case = _make_case(question_type="refusal", answerability=True)  # R2 fail

    def mock_llm(system: str, user: str) -> str:
        return json.dumps({"verdict": "pass", "failed_rules": []})

    report = validate_case(case, llm_call=mock_llm)
    assert report.verdict == "fail"
    assert "R2" in report.failed_rules


def test_validate_case_llm_exception_degrades_gracefully():
    case = _make_case()

    def bad_llm(system: str, user: str) -> str:
        raise RuntimeError("network down")

    report = validate_case(case, llm_call=bad_llm)
    # 本地规则全过 → LLM 失败时 verdict 仍为 pass(降级)
    assert report.verdict == "pass"
    assert report.failed_rules == []


def test_validate_suite_batches_results():
    cases = [
        _make_case(case_id="LA-DEF-001"),
        _make_case(case_id="LA-DEF-002", bloom_level="NotABloom"),
    ]

    def mock_llm(system: str, user: str) -> str:
        return json.dumps({"verdict": "pass", "failed_rules": []})

    reports = validate_suite(cases, llm_call=mock_llm)
    assert len(reports) == 2
    assert reports[0].verdict == "pass"
    assert reports[1].verdict == "fail"
    assert "R6" in reports[1].failed_rules


# ---------------------------------------------------------------------------
# 8. LLM verdict 解析容错
# ---------------------------------------------------------------------------


def test_parse_llm_verdict_handles_markdown():
    raw = 'some preamble\n```json\n{"verdict": "fail", "failed_rules": ["R3"]}\n```\n'
    verdict, failed = _parse_llm_verdict(raw)
    assert verdict == "fail"
    assert failed == ["R3"]


def test_parse_llm_verdict_handles_pure_garbage():
    verdict, failed = _parse_llm_verdict("not json at all")
    assert verdict == "fail"
    assert failed == ["R1"]
