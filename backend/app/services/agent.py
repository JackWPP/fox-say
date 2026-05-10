import json
import logging
from typing import Any, AsyncGenerator

from openai import OpenAI

from app.core.config import settings
from app.services.guard import check_answer_in_scope

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = settings.deepseek_api_key or "placeholder"
        _client = OpenAI(api_key=api_key, base_url=settings.deepseek_api_base)
    return _client


SYSTEM_PROMPT = (
    "你是 FoxSay，一只聪明但贱贱的小狐狸，也是这门课的 AI 助教。\n\n"
    "核心规则：\n"
    "1. 你只能回答与当前课程相关的问题。如果用户问题明显超出课程范围，礼貌但欠揍地拒绝。\n"
    "2. 【必须】当你使用 search_course_materials 获取了课程材料信息后，在回答中必须用以下格式注明引用来源：\n"
    "   来自 [文件名] · 第X部分\n"
    "   每条来自材料的具体信息都要有引用。不要只在末尾列「来源」，要在正文中自然地嵌入引用。\n"
    "3. 当课程材料没有直接覆盖但仍在课程领域内时，你可以基于对课程的理解进行推理和解释，\n"
    "   但要明确标注「基于课程内容的理解」。\n"
    "4. 积极使用工具：\n"
    "   - search_course_materials: 搜索课程材料（tool 返回的 source 字段就是引用格式，直接用它）\n"
    "   - query_knowledge_graph: 查找概念关系\n"
    "   - get_course_structure: 了解课程架构\n"
    "   - get_review_plan: 查看复习计划\n"
    "5. 回答要自然、有帮助、有结构（可以用 Markdown 排版），但不要逐条罗列搜索结果。\n"
    "6. 对备考的同学紧迫一点，对日常学习的同学轻松一点。\n"
    "7. 如果工具返回的结果为空或不相关，说明材料中没有覆盖这一块，你可以基于课程知识进行推理。"
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_course_materials",
            "description": "搜索课程材料中的具体内容。当用户问到需要查资料的问题时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "中文搜索查询，尽量用课程相关的术语",
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "description": "返回结果数量，默认5",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_knowledge_graph",
            "description": "查询课程知识图谱中概念的关系、前置依赖和邻居节点。用于理解概念间的关联。",
            "parameters": {
                "type": "object",
                "properties": {
                    "concept": {
                        "type": "string",
                        "description": "要查询的概念名称",
                    },
                    "depth": {
                        "type": "integer",
                        "default": 1,
                        "description": "查询邻居的跳数，默认1",
                    },
                },
                "required": ["concept"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_structure",
            "description": "获取课程的整体架构：章节划分、核心概念、难点区域。用于了解课程全局。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_review_plan",
            "description": "获取当前的复习计划，包括每天的重点和薄弱环节。仅在用户明确问复习相关问题时使用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_concepts",
            "description": "在课程知识图谱中模糊搜索概念。用于不确定概念确切名称时查找。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的概念名称或部分名称",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


async def agent_chat(
    course_id: str,
    course_title: str,
    question: str,
    chat_history: list[dict] | None = None,
    store: Any = None,
    review_context: str = "",
) -> AsyncGenerator[dict, None]:
    """Agent loop: LLM with tools, streaming events to the frontend.

    Yields SSE-ready event dicts: {type, ...}
    Types: tool_call, token, done, error
    """
    client = _get_client()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    # Course identity
    context_msg = f"当前课程：{course_title}\n课程ID：{course_id}"
    if review_context:
        context_msg += f"\n\n当前复习上下文：{review_context}"
    messages.append({"role": "system", "content": context_msg})

    # Chat history (last 20 messages to keep context manageable)
    if chat_history:
        messages.extend(chat_history[-20:])

    messages.append({"role": "user", "content": question})

    # Collect source info from tool results for citation fallback
    collected_sources: list[dict] = []

    max_rounds = 5
    for _round in range(max_rounds):
        try:
            response = client.chat.completions.create(
                model=settings.deepseek_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
                extra_body={"thinking": {"type": "disabled"}},
            )
        except Exception:
            logger.exception("LLM call failed in agent loop round %d", _round)
            yield {"type": "error", "message": "LLM 调用失败，请重试"}
            return

        msg = response.choices[0].message

        # No tool calls → final answer, stream tokens
        if not msg.tool_calls:
            # Stream tokens from the final response
            answer_text = msg.content or ""

            # Post-answer guard
            guard_result = {}
            if store is not None and answer_text:
                try:
                    guard_result = check_answer_in_scope(answer_text, course_id, store)
                except Exception:
                    logger.exception("Guard check failed, allowing answer through")

            citations = _extract_citations(answer_text)
            # Fallback: if LLM didn't cite, use collected sources from tool results
            if not citations and collected_sources:
                seen: set[str] = set()
                for s in collected_sources:
                    key = f"{s.get('file_name', '')}|{s.get('locator', '')}"
                    if key not in seen and s.get("file_name"):
                        citations.append({"file_name": s["file_name"], "locator": s.get("locator", "")})
                        seen.add(key)

            yield {
                "type": "done",
                "answer": answer_text,
                "citations": citations,
                "in_scope": guard_result.get("in_scope", True),
                "guard_warning": guard_result.get("warning"),
            }
            return

        # Execute tool calls
        for tool_call in msg.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            yield {
                "type": "tool_call",
                "tool": tool_name,
                "args": tool_args,
            }

            try:
                tool_result = await _execute_tool(tool_name, tool_args, course_id, store)
            except Exception as exc:
                tool_result = json.dumps({"error": str(exc)}, ensure_ascii=False)

            # Collect sources from search results
            if tool_name == "search_course_materials":
                try:
                    data = json.loads(tool_result)
                    for r in data.get("results", []):
                        src = r.get("source", "")
                        collected_sources.append({"file_name": r.get("file_name", ""), "locator": r.get("locator", ""), "source": src})
                except (json.JSONDecodeError, KeyError):
                    pass

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                ],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

    # Max rounds reached — force final answer
    try:
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages + [{"role": "system", "content": "请基于已有的工具查询结果，给出你的最终回答。必须在回答中引用来源。"}],
            temperature=0.3,
            extra_body={"thinking": {"type": "disabled"}},
        )
        answer_text = response.choices[0].message.content or ""
    except Exception:
        answer_text = "嗯……我查了几次但还是不太确定。要不换个问法试试？"

    citations = _extract_citations(answer_text)
    if not citations and collected_sources:
        seen: set[str] = set()
        for s in collected_sources:
            key = f"{s.get('file_name', '')}|{s.get('locator', '')}"
            if key not in seen and s.get("file_name"):
                citations.append({"file_name": s["file_name"], "locator": s.get("locator", "")})
                seen.add(key)

    yield {
        "type": "done",
        "answer": answer_text,
        "citations": citations,
        "in_scope": True,
        "guard_warning": None,
    }


async def _execute_tool(name: str, args: dict, course_id: str, store: Any) -> str:
    if name == "search_course_materials":
        from app.services.retrieval import tool_search_materials
        return tool_search_materials(course_id, args.get("query", ""), args.get("top_k", 5))

    if name == "query_knowledge_graph":
        from app.services.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph.for_course(course_id, store=store)
        concept = args.get("concept", "")
        depth = args.get("depth", 1)
        if kg.get_concept_count() == 0:
            return json.dumps({"found": False, "note": "知识图谱尚未构建"}, ensure_ascii=False)
        matching = kg.search_concepts_fuzzy(concept)
        if not matching:
            return json.dumps({"found": False, "note": f"未找到与'{concept}'匹配的概念"}, ensure_ascii=False)
        subgraphs = []
        for m in matching[:3]:
            neighbors = kg.get_neighbors(m["id"], depth=depth)
            subgraphs.append({"concept": m["label"], "match_type": m["match_type"], "neighbors": neighbors})
        return json.dumps({"found": True, "results": subgraphs}, ensure_ascii=False)

    if name == "get_course_structure":
        skeleton = store.get_skeleton(course_id) if store else None
        if not skeleton:
            return json.dumps({"note": "课程骨架尚未生成"}, ensure_ascii=False)
        return json.dumps({
            "chapters": [
                {
                    "title": ch.title,
                    "key_concepts": ch.key_concepts,
                    "importance": ch.importance,
                    "exam_weight": ch.exam_weight,
                }
                for ch in skeleton.chapters
            ],
            "core_concepts": skeleton.core_concepts,
            "difficulty_areas": skeleton.difficulty_areas,
        }, ensure_ascii=False)

    if name == "get_review_plan":
        plan = store.get_review_plan(course_id) if store else None
        if not plan:
            return json.dumps({"note": "暂无复习计划"}, ensure_ascii=False)
        return json.dumps({
            "remaining_days": plan.remaining_days,
            "daily_plan": [
                {"day": d.day_index, "focus": d.focus, "minutes": d.suggested_minutes, "priority": d.priority}
                for d in plan.daily_plan
            ],
            "likely_exam_points": plan.likely_exam_points,
            "weak_areas": plan.weak_areas,
        }, ensure_ascii=False)

    if name == "search_concepts":
        from app.services.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph.for_course(course_id, store=store)
        if kg.get_concept_count() == 0:
            return json.dumps({"found": False, "note": "知识图谱尚未构建"}, ensure_ascii=False)
        results = kg.search_concepts_fuzzy(args.get("query", ""))
        return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False)

    return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)


def _extract_citations(text: str) -> list[dict]:
    """Extract inline citations from answer text."""
    import re
    citations: list[dict] = []
    seen: set[str] = set()

    patterns = [
        # 来自 [文件名] · 第X部分  or  来自[文件名]·第X部分
        re.compile(r"来自\s*\[?(.+?)\]?\s*·\s*(第.+?部分)"),
        # [文件名] · 第X部分 (without 来自)
        re.compile(r"\[(.+?)\]\s*·\s*(第.+?部分)"),
        # 文件名 · 第X部分
        re.compile(r"([\w一-鿿.-]+\.(?:pdf|ppt|txt|md))\s*·\s*(第.+?部分)"),
    ]

    for pattern in patterns:
        for match in pattern.finditer(text):
            file_name = match.group(1).strip()
            locator = match.group(2).strip()
            key = f"{file_name}|{locator}"
            if key not in seen:
                citations.append({"file_name": file_name, "locator": locator})
                seen.add(key)

    return citations
