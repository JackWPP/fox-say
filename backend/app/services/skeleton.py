import json
import logging
from typing import Any

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


SKELETON_FROM_GRAPH_PROMPT = (
    "你是一个课程骨架分析助手。以下是课程知识图谱中自动抽取的概念和关系列表。\n"
    "请将这些概念按章节组织起来。不要编造新概念，只能使用图谱中已有的概念。\n"
    "如果图谱数据不足以组织章节，返回空 chapters 数组。\n\n"
    "请以 JSON 格式返回：\n"
    "{\n"
    '  "chapters": [\n'
    '    {"id": "ch-1", "title": "章节标题", "key_concepts": ["概念1"], "importance": "high|medium|low", "exam_weight": 0.3}\n'
    "  ]\n"
    "}\n"
    "只返回 JSON，不要包含其他文字。"
)

SKELETON_FALLBACK_PROMPT = (
    "你是一个课程骨架分析助手。请根据提供的课程材料文本分析课程结构，"
    "以 JSON 格式返回章节组织。\n"
    "{\n"
    '  "chapters": [\n'
    '    {"id": "ch-1", "title": "章节标题", "key_concepts": ["概念1"], "importance": "high|medium|low", "exam_weight": 0.3}\n'
    "  ]\n"
    "}\n"
    "只返回 JSON，不要包含其他文字。"
)


async def generate_skeleton(
    course_id: str,
    course_title: str,
    materials_text: str,
    store: Any = None,
) -> CourseSkeleton:
    kg = KnowledgeGraph.for_course(course_id, store=store)

    try:
        skeleton = await _llm_generate(course_id, course_title, kg, materials_text)
    except Exception:
        logger.exception("LLM skeleton generation failed for course %s, falling back", course_id)
        skeleton = _fallback_generate(course_id, materials_text, kg)

    if store is not None and kg._dirty:
        kg.save(store)

    return skeleton


async def _llm_generate(
    course_id: str,
    course_title: str,
    kg: KnowledgeGraph,
    materials_text: str,
) -> CourseSkeleton:
    has_graph = kg.get_concept_count() > 0

    if has_graph:
        graph_context = kg.to_context()
        user_content = (
            f"课程名：{course_title}\n\n"
            f"知识图谱概念与关系：\n{graph_context}"
        )
        system_prompt = SKELETON_FROM_GRAPH_PROMPT
    else:
        user_content = f"课程名：{course_title}\n\n课程材料文本：\n{materials_text[:8000]}"
        system_prompt = SKELETON_FALLBACK_PROMPT

    client = _get_client()
    response = client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )

    raw = response.choices[0].message.content or ""
    parsed = _parse_llm_json(raw)
    chapters_data = parsed.get("chapters", [])

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
    materials_text: str,
    kg: KnowledgeGraph,
) -> CourseSkeleton:
    # If graph has nodes, derive chapters from graph connectivity rather than text
    if kg.get_concept_count() > 0:
        nodes = list(kg._graph.nodes(data=True))
        in_degrees = dict(kg._graph.in_degree())
        sorted_nodes = sorted(nodes, key=lambda n: in_degrees.get(n[0], 0), reverse=True)

        chapters_data: list[dict] = []
        for idx, (node_id, attrs) in enumerate(sorted_nodes[:20]):
            label = attrs.get("label", node_id)
            chapters_data.append({
                "id": f"ch-{idx + 1}",
                "title": label,
                "key_concepts": [label],
                "importance": "high" if in_degrees.get(node_id, 0) >= 3 else "medium",
                "exam_weight": round(1.0 / min(len(sorted_nodes[:20]), 1), 2),
            })
        return kg.to_skeleton(course_id, chapters_data)

    # No graph at all: fall back to text chunking
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
