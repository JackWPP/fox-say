"""Judge 测试:覆盖 Faithfulness 0-3 打分 + length 截断 ambiguous 标记。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.schemas.foxsay import Citation, EvalCase

from backend.eval.judge import _parse_verdict, judge_one, judge_suite
from backend.eval.schemas import FoxsayAnswer, JudgeVerdict


def _make_case(**overrides) -> EvalCase:
    base = {
        "case_id": "LA-DEF-001",
        "course_id": "linear-algebra",
        "question": "什么是特征值?",
        "question_type": "definition",
        "associated_kc_id": "kc_eigen",
        "bloom_level": "Understanding",
        "gold_answer": "特征值是方阵 A 满足 Av=λv 的非零标量 λ。",
        "gold_citations": [{"file_name": "线性代数.pdf", "locator": "第四章"}],
        "answerability": True,
    }
    base.update(overrides)
    return EvalCase.model_validate(base)


def _make_answer(**overrides) -> FoxsayAnswer:
    base = {
        "course_id": "linear-algebra",
        "answer": "特征值是方阵 A 满足 Av=λv 的非零标量 λ。",
        "citations": [Citation(file_name="线性代数.pdf", locator="第四章")],
        "confidence_status": "grounded",
    }
    base.update(overrides)
    return FoxsayAnswer.model_validate(base)


# ---------------------------------------------------------------------------
# 1. _parse_verdict
# ---------------------------------------------------------------------------


def test_parse_verdict_full_grounded():
    raw = json.dumps({"faithfulness": 3, "reasoning": "完全 grounded"})
    score, reason = _parse_verdict(raw)
    assert score == 3
    assert "grounded" in reason


def test_parse_verdict_hallucinated():
    raw = json.dumps({"faithfulness": 0, "reasoning": "完全 hallucinated"})
    score, reason = _parse_verdict(raw)
    assert score == 0


def test_parse_verdict_handles_markdown_fence():
    raw = '```json\n{"faithfulness": 2, "reasoning": "ok"}\n```'
    score, _ = _parse_verdict(raw)
    assert score == 2


def test_parse_verdict_clamps_out_of_range():
    raw = json.dumps({"faithfulness": 99, "reasoning": ""})
    score, _ = _parse_verdict(raw)
    assert score == 3  # clamp 到上限


def test_parse_verdict_handles_garbage():
    score, reason = _parse_verdict("not json at all")
    assert score == 0
    assert "无法解析" in reason or "JSON" in reason


# ---------------------------------------------------------------------------
# 2. judge_one — happy path
# ---------------------------------------------------------------------------


def test_judge_one_pass_when_faithful():
    case = _make_case()
    actual = _make_answer()

    def mock_llm(system: str, user: str) -> str:
        return json.dumps({"faithfulness": 3, "reasoning": "完全一致"})

    verdict = judge_one(case, actual, llm_call=mock_llm)
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.faithfulness == 3
    assert verdict.passed is True


def test_judge_one_fail_when_hallucinated():
    case = _make_case()
    actual = _make_answer(answer="完全胡说的答案")

    def mock_llm(system: str, user: str) -> str:
        return json.dumps({"faithfulness": 0, "reasoning": "矛盾"})

    verdict = judge_one(case, actual, llm_call=mock_llm)
    assert verdict.faithfulness == 0
    assert verdict.passed is False


# ---------------------------------------------------------------------------
# 3. judge_one — length 截断 → ambiguous
# ---------------------------------------------------------------------------


def test_judge_one_length_truncation_marks_ambiguous():
    case = _make_case()
    actual = _make_answer()

    def length_truncated_llm(system: str, user: str) -> str:
        return "__AMBIGUOUS_LENGTH__"

    verdict = judge_one(case, actual, llm_call=length_truncated_llm)
    # ambiguous 时 faithfulness=0(防御默认),reasoning 标 ambiguous
    assert verdict.faithfulness == 0
    assert verdict.passed is False
    assert "ambiguous" in verdict.reasoning or "截断" in verdict.reasoning


# ---------------------------------------------------------------------------
# 4. judge_one — LLM 异常
# ---------------------------------------------------------------------------


def test_judge_one_handles_llm_exception():
    case = _make_case()
    actual = _make_answer()

    def bad_llm(system: str, user: str) -> str:
        raise RuntimeError("judge server down")

    verdict = judge_one(case, actual, llm_call=bad_llm)
    # 异常 → faithfulness=0, passed=False,但不静默吞错
    assert verdict.faithfulness == 0
    assert verdict.passed is False
    assert "异常" in verdict.reasoning or "judge" in verdict.reasoning


# ---------------------------------------------------------------------------
# 5. judge_suite 批量
# ---------------------------------------------------------------------------


def test_judge_suite_returns_aligned_results():
    cases = [_make_case(case_id=f"X-DEF-{i:03d}") for i in range(1, 4)]
    actuals = [_make_answer() for _ in range(3)]

    scores = [3, 2, 1]

    def mock_llm(system: str, user: str) -> str:
        # 简单循环返回不同分数
        idx = mock_llm.calls if hasattr(mock_llm, "calls") else 0
        mock_llm.calls = idx + 1
        return json.dumps({"faithfulness": scores[idx], "reasoning": f"r{idx}"})

    verdicts = judge_suite(cases, actuals, llm_call=mock_llm)
    assert len(verdicts) == 3
    assert [v.faithfulness for v in verdicts] == [3, 2, 1]
    assert verdicts[0].passed is True
    assert verdicts[1].passed is True
    assert verdicts[2].passed is False


def test_judge_suite_length_mismatch_raises():
    cases = [_make_case(case_id=f"X-DEF-{i:03d}") for i in range(1, 3)]
    actuals = [_make_answer()]
    with pytest.raises(ValueError):
        judge_suite(cases, actuals)
