"""LLM-based quiz generation from KC data."""
import json
import logging
from typing import Any

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.deepseek_api_key or "placeholder",
            base_url=settings.deepseek_api_base,
            timeout=60,
        )
    return _client


_SYSTEM_PROMPT = """\
你是一位出题专家，根据提供的知识点（KC）数据为学生生成练习题。
严格遵守以下规则：
- 只基于提供的 KC 数据出题，不凭借模型常识补充内容
- 选择题必须有 4 个选项（A/B/C/D），且只有一个正确答案
- 填空题的答案必须能在 KC 定义/公式/直觉中找到
- 证明/简答题给出参考答案要点
- 干扰项要有迷惑性，不能过于明显
- 返回严格 JSON，不包含任何 markdown 包装符号

输出格式：
{
  "questions": [
    {
      "id": "q-1",
      "type": "choice|fill|proof",
      "kc_id": "<kc的id>",
      "kc_name": "<kc名称>",
      "question": "<题目>",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "A",
      "explanation": "<简短解析>"
    }
  ]
}
填空/证明题没有 options 字段，answer 为完整答案文本。
"""


def _kc_to_context(kc: Any) -> str:
    parts = [f"KC: {kc.name} (id={kc.id})"]
    if kc.definition:
        parts.append(f"  定义: {kc.definition}")
    if kc.formula:
        parts.append(f"  公式: {kc.formula}")
    if kc.intuition:
        parts.append(f"  直觉理解: {kc.intuition}")
    if kc.examples:
        parts.append(f"  例子: {'; '.join(kc.examples[:2])}")
    if kc.common_mistakes:
        parts.append(f"  常见错误: {'; '.join(kc.common_mistakes[:2])}")
    if kc.exam_patterns:
        parts.append(f"  考试模式: {'; '.join(kc.exam_patterns[:2])}")
    return "\n".join(parts)


def generate_quiz(
    kcs: list[Any],
    count: int = 5,
    q_type: str = "mixed",
) -> list[dict]:
    """Call LLM to generate quiz questions from KC list. Returns list of question dicts."""
    if not kcs:
        return []

    # Limit KC context to avoid token overflow
    selected_kcs = kcs[:min(len(kcs), count * 2)]
    kc_context = "\n\n".join(_kc_to_context(kc) for kc in selected_kcs)

    type_instruction = {
        "choice": f"生成 {count} 道选择题",
        "fill": f"生成 {count} 道填空题",
        "proof": f"生成 {count} 道简答/证明题",
        "mixed": f"生成共 {count} 道题，类型按 choice:fill:proof ≈ 2:2:1 的比例混合",
    }.get(q_type, f"生成 {count} 道混合题型")

    user_prompt = (
        f"{type_instruction}。\n\n"
        f"以下是本次出题使用的知识点数据：\n\n{kc_context}"
    )

    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        raw = resp.choices[0].message.content or ""
        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        return data.get("questions", [])
    except json.JSONDecodeError as e:
        logger.error("Quiz LLM returned invalid JSON: %s", e)
        return []
    except Exception as e:
        logger.error("Quiz generation failed: %s", e)
        return []
