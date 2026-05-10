import logging
import re
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.schemas.foxsay import CragAnswer, Citation
from app.services.retrieval import retrieve

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = settings.deepseek_api_key or "placeholder"
        _client = OpenAI(api_key=api_key, base_url=settings.deepseek_api_base)
    return _client


SYSTEM_PROMPT = (
    "你是一个课程学习助手。你必须严格遵守以下规则：\n"
    "1. 你只能基于提供的课程材料回答问题，不得使用模型自身常识补充课程外的内容。\n"
    "2. 每条回答必须包含来源引用，格式为：来自 [文件名] · 第X部分\n"
    "3. 如果提供的材料不足以回答问题，你必须拒答。\n"
    "4. 不得编造、泛化或转向通用百科回答。"
)

AMBIGUOUS_SYSTEM_PROMPT = (
    "你是一个课程学习助手。当前检索到的材料与问题的相关性较低，你需要谨慎回答。\n"
    "你必须严格遵守以下规则：\n"
    "1. 你只能基于提供的课程材料回答，不得使用模型常识补充。\n"
    "2. 每条回答必须包含来源引用，格式为：来自 [文件名] · 第X部分\n"
    "3. 明确标注你的回答置信度较低，避免做出确定性断言。\n"
    "4. 如果材料不足以回答，必须拒答。"
)

_CITATION_PATTERN = re.compile(r"来自\s*\[.+?\]\s*·\s*第.+?部分")


def _ensure_citations(answer_text: str, citations: list[Citation]) -> str:
    if not citations:
        return answer_text
    if _CITATION_PATTERN.search(answer_text):
        return answer_text
    source_lines = []
    seen: set[str] = set()
    for c in citations:
        key = f"{c.file_name}|{c.locator}"
        if key not in seen:
            source_lines.append(f"来自 [{c.file_name}] · {c.locator}")
            seen.add(key)
    sources_block = "\n\n**来源：**\n" + "\n".join(f"- {s}" for s in source_lines)
    return answer_text + sources_block


async def ask(course_id: str, course_title: str, question: str, store: Any = None) -> CragAnswer:
    retrieval_result = retrieve(course_id, question, store=store)
    confidence = retrieval_result["confidence"]
    top_score = retrieval_result["top_score"]
    results = retrieval_result["results"]

    if confidence == "out_of_scope":
        return CragAnswer(
            course_id=course_id,
            answer=f"这个问题超出了{course_title}的范围，我不知道。别想骗我乱说。",
            citations=[],
            confidence_status="out_of_scope",
            relevance_score=top_score,
            refusal_reason="out_of_scope",
        )

    context_parts: list[str] = []
    citations: list[Citation] = []
    for r in results:
        context_parts.append(r["text"])
        citations.append(Citation(
            file_name=r["metadata"]["file_name"],
            locator=r["metadata"]["locator"],
        ))

    graph_context = retrieval_result.get("graph_context", "")
    if graph_context:
        context_parts.append(f"[知识图谱关联概念]\n{graph_context}")

    context = "\n\n".join(context_parts)

    if confidence == "grounded":
        answer_text = await _llm_answer(question, context, SYSTEM_PROMPT)
    else:
        answer_text = await _llm_answer(question, context, AMBIGUOUS_SYSTEM_PROMPT)

    answer_text = _ensure_citations(answer_text, citations)

    refusal_reason = None if confidence != "ambiguous" else "low_confidence"

    return CragAnswer(
        course_id=course_id,
        answer=answer_text,
        citations=citations,
        confidence_status=confidence,
        relevance_score=top_score,
        refusal_reason=refusal_reason,
    )


async def _llm_answer(question: str, context: str, system_prompt: str) -> str:
    client = _get_client()

    user_content = f"课程材料：\n{context}\n\n问题：{question}"

    response = client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content or ""
