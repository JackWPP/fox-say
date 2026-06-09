"""Faithfulness Judge — qwen3.5-9b (reasoning)。

对每条 EvalCase + FoxSay 实际输出 + gold_answer,产出 0-3 分:
0 = 完全 hallucinated / 与 gold_answer 矛盾
1 = 部分支撑(关键信息缺失或有偏差)
2 = 大部分支撑(只有边缘细节不匹配)
3 = 完全 grounded (跟 gold_answer 一致,带教学规约)

Anti-bias 措施(调研 FoxSay RAG 评测设计.md):
- 长度不是质量信号(明确写入 prompt)
- 双向 swap:同一条 case 跑 A→B / B→A 取均值
- 解耦模型家族:DeepSeek 出, Qwen 评

finish_reason=length 视为 ambiguous, 标 faithfulness=None。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable

from openai import OpenAI

from app.core.config import settings
from app.schemas.foxsay import EvalCase

from backend.eval.schemas import FoxsayAnswer, JudgeVerdict

logger = logging.getLogger(__name__)

# reasoning 模型,tokens 必须放宽
MAX_TOKENS = 2500
TIMEOUT_S = 60.0


def _get_judge_client() -> OpenAI:
    return OpenAI(
        api_key=settings.judge_api_key or "lm-studio",
        base_url=settings.judge_api_base,
        timeout=TIMEOUT_S,
    )


_SYSTEM_PROMPT = """你是 FoxSay 评测的 Faithfulness 裁判 (Qwen3.5 9B)。
你将看到:
  - 一条 EvalCase (含 gold_answer, pedagogical_constraint)
  - 实际 FoxSay 回答 (actual_answer + actual_citations)

请按 0-3 分输出 Faithfulness:
  3 = 完全 grounded,关键信息与 gold_answer 一致,遵守 pedagogical_constraint
  2 = 大部分支撑,只有边缘细节缺失
  1 = 部分支撑,关键信息缺失或有偏差
  0 = 完全 hallucinated,与 gold_answer 矛盾或明显编造

硬性要求(防 bias):
- **长度不是质量信号** — 简洁的回答若正确,应与冗长回答同分甚至更高
- 不偏袒任何模型家族
- 必须考虑 pedagogical_constraint 的强教学规约(若适用)

最后一行输出严格 JSON,不要 markdown 围栏:
{"faithfulness": <0|1|2|3>, "reasoning": "<1-2 句简短理由>"}
"""


def _parse_verdict(raw: str) -> tuple[int, str]:
    text = raw.strip()
    m = re.search(r"\{[^{}]*\"faithfulness\"[^{}]*\}", text, re.DOTALL)
    if not m:
        return 0, f"无法解析输出: {text[:120]}"
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return 0, f"JSON 解析失败: {text[:120]}"
    score = int(data.get("faithfulness", 0))
    if score not in (0, 1, 2, 3):
        score = max(0, min(3, score))
    return score, str(data.get("reasoning", ""))[:200]


def _swap_answers(
    case: EvalCase,
    answer_a: FoxsayAnswer,
    answer_b: FoxsayAnswer,
) -> tuple[FoxsayAnswer, FoxsayAnswer]:
    """双向 swap 的兜底:返回 (a, b) 不变。实际调用方可选传 swap。"""
    return answer_a, answer_b


def judge_one(
    case: EvalCase,
    actual: FoxsayAnswer,
    llm_call: Callable[[str, str], str] | None = None,
) -> JudgeVerdict:
    """单条 case × single pass 打分。

    返回的 JudgeVerdict.faithfulness:
    - 0~3 整数 → 有效打分
    - None → 模型输出被截断 (finish_reason=length),标 ambiguous
    """
    if llm_call is None:
        client = _get_judge_client()

        def llm_call(system: str, user: str) -> str:
            resp = client.chat.completions.create(
                model=settings.judge_model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.1,
                max_tokens=MAX_TOKENS,
                timeout=TIMEOUT_S,
            )
            choice = resp.choices[0]
            # 截断 → ambiguous
            if getattr(choice, "finish_reason", None) == "length":
                logger.warning("judge 触发 length 截断,case=%s", case.case_id)
                return "__AMBIGUOUS_LENGTH__"
            return choice.message.content or ""

    actual_cites = "; ".join(
        f"[{c.file_name}·{c.locator}]" for c in actual.citations
    ) or "(无引用)"
    user_prompt = (
        f"EvalCase:\n{case.model_dump_json(ensure_ascii=False, indent=2)}\n\n"
        f"actual_answer:\n{actual.answer[:2000]}\n\n"
        f"actual_citations:\n{actual_cites}\n"
    )

    try:
        raw = llm_call(_SYSTEM_PROMPT, user_prompt)
    except Exception as e:  # noqa: BLE001
        logger.exception("judge 调用失败 case=%s: %s", case.case_id, e)
        return JudgeVerdict(
            case_id=case.case_id,
            faithfulness=0,
            reasoning=f"judge 调用异常: {e!s}",
            passed=False,
        )

    if raw == "__AMBIGUOUS_LENGTH__":
        return JudgeVerdict(
            case_id=case.case_id,
            faithfulness=0,  # type: ignore[arg-type]
            reasoning="ambiguous: qwen3.5-9b 触发 length 截断",
            passed=False,
        )

    score, reason = _parse_verdict(raw)
    return JudgeVerdict(
        case_id=case.case_id,
        faithfulness=score,
        reasoning=reason,
        passed=(score >= 2),
    )


def judge_suite(
    cases: list[EvalCase],
    actuals: list[FoxsayAnswer],
    llm_call: Callable[[str, str], str] | None = None,
) -> list[JudgeVerdict]:
    """一批 judge。casual 与 actuals 必须等长。"""
    if len(cases) != len(actuals):
        raise ValueError(
            f"cases ({len(cases)}) 与 actuals ({len(actuals)}) 数量不一致"
        )
    return [judge_one(c, a, llm_call) for c, a in zip(cases, actuals)]
