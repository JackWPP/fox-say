"""Pilot 集格式校验器。

调用 qwen3-4b-2507 (非 reasoning, 快),对每条 EvalCase 跑 7 条规则,
输出 {verdict, failed_rules[]}。

7 条规则:
R1 schema 合法 (pydantic EvalCase 校验已能保证,但 LLM 也要复述"通过")
R2 question_type 与 answerability 语义一致
R3 answerability=false → gold_answer 必须含"超出范围"类拒答文案
R4 answerability=true 且非 ambiguous → gold_answer 长度 ≥ 50 字
R5 associated_kc_id 非空 → 必须在 kc 列表里 (get_kc 找到)
R6 bloom_level 是 6 阶 Bloom 之一
R7 gold_citations 数量与 question_type 匹配
   (definition ≥ 1, derivation ≥ 1, cross_chapter ≥ 2, refusal ≥ 0, ambiguous ≥ 0)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable

from openai import OpenAI

from app.core.config import settings
from app.schemas.foxsay import EvalCase, KC

from backend.eval.schemas import ValidatorReport, Verdict

logger = logging.getLogger(__name__)

_VALID_BLOOM = {
    "Remembering", "Understanding", "Applying",
    "Analyzing", "Evaluating", "Creating",
}

# 每种题型最少引用条数(validator 强约束)
_MIN_CITATIONS = {
    "definition": 1,
    "derivation": 1,
    "cross_chapter": 2,
    "refusal": 0,
    "ambiguous": 0,
}

# "拒答" 关键词,任意一个命中即视为拒答文案
_REFUSAL_KEYWORDS = (
    "超出", "不知道", "不属于", "范围", "本课程", "本题不在",
    "拒答", "无法回答", "没有涉及",
)


def _get_judge_client() -> OpenAI:
    return OpenAI(
        api_key=settings.judge_api_key or "lm-studio",
        base_url=settings.judge_api_base,
    )


def _rule_r2_type_answerability(case: EvalCase) -> str | None:
    """R2:question_type 与 answerability 语义一致。"""
    if case.question_type == "refusal" and case.answerability is True:
        return "R2"
    if case.question_type in {"definition", "derivation", "cross_chapter"} and case.answerability is False:
        return "R2"
    return None


def _rule_r3_refusal_text(case: EvalCase) -> str | None:
    """R3:answerability=false → gold_answer 必须含拒答文案。"""
    if case.answerability is True:
        return None
    answer = case.gold_answer or ""
    if not any(kw in answer for kw in _REFUSAL_KEYWORDS):
        return "R3"
    return None


def _rule_r4_gold_length(case: EvalCase) -> str | None:
    """R4:answerability=true 且非 ambiguous → gold_answer ≥ 50 字。"""
    if case.answerability is False:
        return None
    if case.question_type == "ambiguous":
        return None
    if len(case.gold_answer or "") < 50:
        return "R4"
    return None


def _rule_r5_associated_kc(case: EvalCase, kc_lookup: dict[str, KC] | None) -> str | None:
    """R5:associated_kc_id 非空 → get_kc 必须找到。"""
    if not case.associated_kc_id:
        return None
    if kc_lookup is None:
        return None  # 没有 kc_lookup,跳过
    if case.associated_kc_id not in kc_lookup:
        return "R5"
    return None


def _rule_r6_bloom(case: EvalCase) -> str | None:
    """R6:bloom_level 6 阶之一。"""
    if case.bloom_level not in _VALID_BLOOM:
        return "R6"
    return None


def _rule_r7_citations(case: EvalCase) -> str | None:
    """R7:gold_citations 数量匹配。"""
    need = _MIN_CITATIONS.get(case.question_type, 1)
    if len(case.gold_citations) < need:
        return "R7"
    return None


def _check_local_rules(
    case: EvalCase,
    kc_lookup: dict[str, KC] | None = None,
) -> list[str]:
    """本地确定性 6 规则(R2~R7)。R1 schema 合法在 EvalCase.model_validate
    那一步就保证,这里不再判。"""
    failed: list[str] = []
    for fn in (
        lambda: _rule_r2_type_answerability(case),
        lambda: _rule_r3_refusal_text(case),
        lambda: _rule_r4_gold_length(case),
        lambda: _rule_r5_associated_kc(case, kc_lookup),
        lambda: _rule_r6_bloom(case),
        lambda: _rule_r7_citations(case),
    ):
        r = fn()
        if r:
            failed.append(r)
    return failed


_SYSTEM_PROMPT = """你是 FoxSay 评测集质检员。你会收到一条 EvalCase 的 JSON,
请用「极其严格」的标准核对下面 7 条规则,逐条回答 "pass" 或 "fail",
最后一行输出 JSON {"verdict": "pass|fail", "failed_rules": ["R1", ...]}。
只输出 7 行 + 1 行 JSON,不要其它解释。

R1 schema 合法 (case_id / course_id / question / question_type / gold_answer 五项非空)
R2 question_type 与 answerability 语义一致
R3 answerability=false → gold_answer 含拒答关键词(超出/不知道/不属于/范围/本课程 等)
R4 answerability=true 且 question_type≠ambiguous → gold_answer ≥ 50 字
R5 associated_kc_id 非空 → 必须形如 kc_xxx (uuid5 风格, 16+ 字符)
R6 bloom_level 是 6 阶之一 (Remembering/Understanding/Applying/Analyzing/Evaluating/Creating)
R7 gold_citations 数量与 question_type 匹配
   (definition≥1 / derivation≥1 / cross_chapter≥2 / refusal=0 / ambiguous=0)
"""


def _parse_llm_verdict(raw: str) -> tuple[Verdict, list[str]]:
    """解析 qwen3-4b 的输出,容错抓 JSON 尾巴。"""
    # 找最后一行 { ... }
    text = raw.strip()
    m = re.search(r"\{[^{}]*\"verdict\"[^{}]*\}", text, re.DOTALL)
    if not m:
        # 尝试全局 json
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return "fail", ["R1"]
        return _parse_llm_verdict(json.dumps(data))[0], data.get("failed_rules", ["R1"])  # type: ignore[return-value]
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return "fail", ["R1"]
    verdict = data.get("verdict", "fail")
    if verdict not in {"pass", "fail"}:
        verdict = "fail"
    failed = data.get("failed_rules", []) or []
    if not isinstance(failed, list):
        failed = []
    return verdict, [str(x) for x in failed]


def validate_case(
    case: EvalCase,
    kc_lookup: dict[str, KC] | None = None,
    llm_call: Callable[[str, str], str] | None = None,
) -> ValidatorReport:
    """单条 EvalCase 校验。

    1. 本地确定性规则 (R2~R7) 先跑
    2. 再让 qwen3-4b 复述一次 (主要用于 R1 schema 完整性 + 抓漏)
    3. 合并失败规则,任一 fail → verdict=fail
    """
    local_failed = _check_local_rules(case, kc_lookup)
    raw_judge = ""

    if llm_call is None:
        client = _get_judge_client()

        def llm_call(system: str, user: str) -> str:
            resp = client.chat.completions.create(
                model=settings.judge_fast_model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
            )
            return resp.choices[0].message.content or ""

    user_prompt = "EvalCase JSON:\n" + case.model_dump_json(ensure_ascii=False)
    try:
        raw_judge = llm_call(_SYSTEM_PROMPT, user_prompt)
        _, llm_failed = _parse_llm_verdict(raw_judge)
    except Exception as e:  # noqa: BLE001
        logger.warning("qwen3-4b 校验失败,降级到本地规则: %s", e)
        llm_failed = []

    all_failed = sorted(set(local_failed) | set(llm_failed))
    verdict: Verdict = "pass" if not all_failed else "fail"

    return ValidatorReport(
        case_id=case.case_id,
        verdict=verdict,
        failed_rules=all_failed,
        raw_judge=raw_judge[:400],
    )


def validate_suite(
    cases: list[EvalCase],
    kc_lookup: dict[str, KC] | None = None,
    llm_call: Callable[[str, str], str] | None = None,
) -> list[ValidatorReport]:
    return [validate_case(c, kc_lookup, llm_call) for c in cases]
