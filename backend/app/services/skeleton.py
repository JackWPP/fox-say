import json
import logging

from openai import OpenAI

from app.core.config import settings
from app.schemas.foxsay import CourseSkeleton
from app.services.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = settings.deepseek_api_key or "placeholder"
        _client = OpenAI(api_key=api_key, base_url=settings.deepseek_api_base)
    return _client


SYSTEM_PROMPT = (
    "你是一个课程骨架分析助手。你只能根据当前课程提供的材料文本进行分析。\n"
    "你必须严格遵守课程隔离原则：不得使用模型常识补充课程材料外的内容。\n"
    "请从材料文本中提取以下信息并以 JSON 格式返回：\n"
    "{\n"
    '  "chapters": [\n'
    '    {"id": "ch-1", "title": "章节标题", "key_concepts": ["概念1"], "importance": "high|medium|low", "exam_weight": 0.3}\n'
    "  ],\n"
    '  "core_concepts": ["核心概念1", "核心概念2"],\n'
    '  "difficulty_areas": ["难点1"],\n'
    '  "prerequisite_chain": [["概念A", "概念B"]]\n'
    "}\n"
    "只返回 JSON，不要包含其他文字。"
)


async def generate_skeleton(
    course_id: str,
    course_title: str,
    materials_text: str,
) -> CourseSkeleton:
    kg = KnowledgeGraph.for_course(course_id)

    try:
        skeleton = await _llm_generate(course_id, course_title, materials_text, kg)
    except Exception:
        logger.exception("LLM skeleton generation failed for course %s, falling back to chunking", course_id)
        skeleton = _fallback_generate(course_id, course_title, materials_text, kg)

    return skeleton


async def _llm_generate(
    course_id: str,
    course_title: str,
    materials_text: str,
    kg: KnowledgeGraph,
) -> CourseSkeleton:
    client = _get_client()

    user_content = f"课程名：{course_title}\n\n课程材料文本：\n{materials_text[:8000]}"

    response = client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )

    raw = response.choices[0].message.content or ""

    parsed = _parse_llm_json(raw)

    chapters_data = parsed.get("chapters", [])
    core_concepts = parsed.get("core_concepts", [])
    _difficulty_areas = parsed.get("difficulty_areas", [])
    prerequisite_chain = parsed.get("prerequisite_chain", [])

    for concept in core_concepts:
        concept_id = concept.replace(" ", "_").lower()
        kg.add_concept(concept_id, label=concept)

    for pair in prerequisite_chain:
        if len(pair) == 2:
            from_id = pair[0].replace(" ", "_").lower()
            to_id = pair[1].replace(" ", "_").lower()
            kg.add_dependency(from_id, to_id)

    return kg.to_skeleton(course_id, chapters_data)


def _parse_llm_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


def _fallback_generate(
    course_id: str,
    course_title: str,
    materials_text: str,
    kg: KnowledgeGraph,
) -> CourseSkeleton:
    chunk_size = 1500
    chunks: list[str] = []
    for i in range(0, len(materials_text), chunk_size):
        chunks.append(materials_text[i : i + chunk_size])

    chapters_data: list[dict] = []
    for idx, chunk in enumerate(chunks):
        title = chunk[:50].strip().split("\n")[0] or f"第{idx + 1}部分"
        chapters_data.append({
            "id": f"ch-{idx + 1}",
            "title": title,
            "key_concepts": [],
            "importance": "medium",
            "exam_weight": round(1.0 / max(len(chunks), 1), 2),
        })

    return kg.to_skeleton(course_id, chapters_data)
