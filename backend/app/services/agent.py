"""FoxSay Agent 主循环 + 7 工具集(阶段 3 重写)。

设计原则:
- ReAct 循环 max 3 轮(原 5 轮,绝大多数问题 1 轮解决)
- 错误必须可见(HEC-1):LLM 失败时 SSE 推 {type: "error", message: "..."}
- schema 显式带 course_id(HEC-6):所有 query 工具入参都接收 course_id, 禁止反推
- 死代码全清:不留任何手写空 history 占位 / 写死章节 ID 解析那种

工具集(7 个):
  search_wiki          三层混合检索(章节+KC+chunk)
  get_course_map       拿课程索引全文
  get_concept          按 ID 拿完整 KC 卡
  get_chapter_outline  按 chapter_id 拿章节摘要
  follow_prerequisite  沿 prerequisites 链回溯
  get_source_content   按 DMAP ID 拿原始材料片段
  get_review_plan      拿复习计划(仅在复习相关问题时使用)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncGenerator

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """LLM 客户端单例。失败时由调用方决定如何处理(HEC-1:不许静默)。"""
    global _client
    if _client is None:
        api_key = settings.deepseek_api_key or "placeholder"
        _client = OpenAI(api_key=api_key, base_url=settings.deepseek_api_base, timeout=30)
    return _client


# ---------------------------------------------------------------------------
# System Prompt(5 条规则,精简)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "你是 FoxSay, 一只聪明但贱贱的小狐狸, 也是这门课的 AI 助教。\n\n"
    "核心规则:\n"
    "1. 只能回答当前课程相关问题。超出范围时礼貌但欠揍地拒绝。\n"
    "2. 引用材料时, 必须用格式 `来自 [文件名] · 第X部分`, 在正文中自然嵌入。\n"
    "3. 用户要求生成内容时,直接调对应工具,不要先搜索:\n"
    "   - 生成讲义 → generate_lecture(chapter_id, depth)\n"
    "   - 出练习题 → generate_quiz(chapter_id, count, type)\n"
    "   - 生成闪卡 → generate_flashcards(chapter_id, count)\n"
    "   - 概念关系图 → show_concept_graph(concept_id)\n"
    "4. 回答问题时,先搜索再回答:\n"
    "   - 事实性问题 → search_wiki(layer=micro)\n"
    "   - 概念解释  → get_concept 拿完整 KC 卡\n"
    "   - 章节概览  → get_course_map 或 get_chapter_outline\n"
    "   - 先修概念  → follow_prerequisite\n"
    "   - 原始引用  → get_source_content\n"
    "5. 复习相关问题才用 get_review_plan。\n"
    "6. 回答自然有结构(Markdown), 不要逐条罗列搜索结果。"
)

# ---------------------------------------------------------------------------
# Tools (7 个)
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_wiki",
            "description": "在课程 Wiki 中做语义检索(章节/KC/原始材料三层)。事实性问题首选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "中文检索词,尽量用课程术语",
                    },
                    "layer": {
                        "type": "string",
                        "enum": ["macro", "micro", "all"],
                        "default": "all",
                        "description": "macro=章节级, micro=KC级, all=三层合并",
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "description": "返回结果数量",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_map",
            "description": "拿课程索引全文(markdown)。用于了解课程全局。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_concept",
            "description": "按 concept_id 拿完整知识卡(KC)内容:定义、公式、常见错误等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "课程ID"},
                    "concept_id": {"type": "string", "description": "KC ID"},
                },
                "required": ["course_id", "concept_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chapter_outline",
            "description": "按 chapter_id 拿章节摘要(overview, 重点, 难点)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "课程ID"},
                    "chapter_id": {"type": "string", "description": "章节ID"},
                },
                "required": ["course_id", "chapter_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "follow_prerequisite",
            "description": "沿 KC.prerequisites 链向上回溯,返回先修概念列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "课程ID"},
                    "concept_id": {"type": "string", "description": "起点 KC ID"},
                    "depth": {
                        "type": "integer",
                        "default": 2,
                        "description": "回溯深度,默认 2",
                    },
                },
                "required": ["course_id", "concept_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_source_content",
            "description": "按 DMAP 节点/元素 ID 拿原始材料片段(text_preview)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "课程ID"},
                    "dmap_id": {"type": "string", "description": "DMAP 节点或元素 ID"},
                },
                "required": ["course_id", "dmap_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_review_plan",
            "description": "拿当前课程的复习计划(每日重点、薄弱环节)。仅复习相关问题使用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _get_tools() -> list[dict]:
    """获取 Agent 工具列表:静态 7 个 + 动态注册的 Skills。"""
    from app.services.skills import build_tools
    return TOOLS + build_tools()


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------

MAX_ROUNDS = 5

# ---------------------------------------------------------------------------
# DSML defense layer
# ---------------------------------------------------------------------------
# Some DeepSeek models emit a fake tool-call syntax in `content` text instead
# of using the real `tool_calls` field, leaving raw markup like:
#   < | DSML | tool_calls> < | DSML | invoke name="X"> < | DSML | parameter
#   name="k" type="t">value</ | DSML | parameter> </ | DSML | invoke>
#   </ | DSML | tool_calls>
# Or with full-width pipes and no spaces (markdown-table escape):
#   <｜｜DSML｜｜tool_calls>...
# Strategy: strip it. Don't try to execute it — the LLM typically passes
# wrong arg names (e.g. `source_id` instead of `dmap_id`) and retrying just
# burns rounds. Mirrored by the frontend `stripDSML` in MarkdownRenderer.tsx.

# Pipe class: ASCII '|' or full-width '｜' (U+FF5C), one or more.
_PIPE = r"[|｜]+"

_DSML_ANY_TAG_RE = re.compile(
    rf"<\s*{_PIPE}\s*DSML\s*{_PIPE}[^>]*>.*?<\s*/\s*{_PIPE}\s*DSML\s*{_PIPE}[^>]*>",
    re.DOTALL,
)
_DSML_ORPHAN_RE = re.compile(rf"</?\s*{_PIPE}\s*DSML\s*{_PIPE}[^>]*>")


def _strip_dsml_blocks(content: str) -> str:
    """Remove all DSML tags from text (defense in depth — used by frontend too)."""
    cleaned = _DSML_ANY_TAG_RE.sub("", content)
    cleaned = _DSML_ORPHAN_RE.sub("", cleaned)
    return cleaned.strip()


async def agent_chat(
    course_id: str,
    course_title: str,
    question: str,
    chat_history: list[dict] | None = None,
    store: Any = None,
    review_context: str = "",
) -> AsyncGenerator[dict, None]:
    """Agent ReAct 循环:SSE 事件流。

    Yields:
        {type: "tool_call", tool, args}
        {type: "done", answer, citations, ...}
        {type: "error", message}
    """
    client = _get_client()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    context_msg = f"当前课程:{course_title}\n课程ID:{course_id}"
    if review_context:
        context_msg += f"\n\n当前复习上下文:{review_context}"
    messages.append({"role": "system", "content": context_msg})

    if chat_history:
        messages.extend(chat_history[-20:])

    messages.append({"role": "user", "content": question})

    collected_sources: list[dict] = []

    for _round in range(MAX_ROUNDS):
        try:
            response = client.chat.completions.create(
                model=settings.deepseek_model,
                messages=messages,
                tools=_get_tools(),
                tool_choice="auto",
                temperature=0.3,
                extra_body={"thinking": {"type": "disabled"}},
            )
        except Exception:
            # HEC-1:错误必须可见,不许静默
            logger.exception("LLM call failed in agent loop round %d", _round)
            yield {"type": "error", "message": "LLM 调用失败, 请重试"}
            return

        msg = response.choices[0].message

        # ---- DSML guard ----
        # Some DeepSeek models emit fake tool-call syntax in `content` text instead
        # of using the real `tool_calls` field. Strategy: strip it (don't try to
        # execute it — args are usually wrong and retrying wastes rounds).
        dsml_in_content = bool(msg.content) and "DSML" in msg.content
        if dsml_in_content:
            logger.info("DSML detected in content (round %d), stripping", _round)
            # If the LLM was confused into tool-calling mode, tell it explicitly
            # and force a clean answer on the next pass.
            messages.append({
                "role": "system",
                "content": (
                    "你刚才的回复里包含了非法的工具调用语法 (DSML), 已为你清理。"
                    "请用 `tool_calls` 字段调用工具, 或直接用中文文字给出最终回答。"
                ),
            })

        # 无 tool_call → 流式输出最终回答
        if not msg.tool_calls:
            answer_text = _strip_dsml_blocks(msg.content or "")
            citations = _extract_citations(answer_text)
            if not citations and collected_sources:
                citations = _dedup_sources_for_citation_fallback(collected_sources)

            # Degenerate case: LLM only emitted DSML and we stripped it clean.
            # Surface a friendly placeholder so the user doesn't see a blank bubble.
            if not answer_text:
                answer_text = "（模型在尝试调用工具时输出了无效语法,我已自动清理。请换个问法或稍后再试。）"

            yield {
                "type": "done",
                "answer": answer_text,
                "citations": citations,
                "in_scope": True,
                "guard_warning": None,
            }
            return

        # 执行 tool_calls
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
                # 如果原始工具返回"未知工具",尝试作为 Skill 执行
                if "未知工具" in tool_result:
                    tool_result = await _execute_skill(tool_name, tool_args, course_id, store)
            except Exception as exc:
                # HEC-1:工具异常要让 LLM 看到,不要 return ""
                logger.exception("Tool %s execution failed", tool_name)
                tool_result = json.dumps({"error": str(exc)}, ensure_ascii=False)

            # Skill 返回内容时直接作为最终回答,不再继续循环
            from app.services.skills import get_skill
            if get_skill(tool_name) is not None:
                try:
                    skill_data = json.loads(tool_result)
                    if "error" not in skill_data:
                        content = skill_data.get("content", "")
                        if content:
                            citations = _extract_citations(content)
                            yield {
                                "type": "done",
                                "answer": content,
                                "citations": citations,
                                "in_scope": True,
                                "guard_warning": None,
                            }
                            return
                except (json.JSONDecodeError, KeyError):
                    pass

            # 从 search_wiki 结果中收集 source 备用
            if tool_name == "search_wiki":
                try:
                    data = json.loads(tool_result)
                    for r in data.get("results", []):
                        collected_sources.append(
                            {
                                "file_name": r.get("file_name", ""),
                                "locator": r.get("locator", ""),
                                "source": r.get("source_ref", ""),
                            }
                        )
                except (json.JSONDecodeError, KeyError):
                    pass

            messages.append(
                {
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
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )

    # 达到 max rounds → 强制生成"基于现有信息"的回答
    try:
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages
            + [
                {
                    "role": "system",
                    "content": "请基于已有的工具查询结果, 给出你的最终回答。必须在回答中引用来源。",
                }
            ],
            temperature=0.3,
            extra_body={"thinking": {"type": "disabled"}},
        )
        # Strip DSML one more time as belt-and-suspenders
        answer_text = _strip_dsml_blocks(response.choices[0].message.content or "")
    except Exception:
        # HEC-1:仍然让前端知道
        logger.exception("LLM call failed at max-rounds forced answer")
        yield {"type": "error", "message": "达到最大工具调用轮次仍无法生成回答"}
        return

    citations = _extract_citations(answer_text)
    if not citations and collected_sources:
        citations = _dedup_sources_for_citation_fallback(collected_sources)

    # Same degenerate-case guard as the normal path
    if not answer_text:
        answer_text = "（达到最大工具调用轮次仍无法生成有效回答,请换个问法或稍后再试。）"

    yield {
        "type": "done",
        "answer": answer_text,
        "citations": citations,
        "in_scope": True,
        "guard_warning": None,
    }


# ---------------------------------------------------------------------------
# 工具执行路由
# ---------------------------------------------------------------------------


async def _execute_tool(name: str, args: dict, course_id: str, store: Any) -> str:
    """路由 7 个工具到对应实现。"""
    from app.services import query_tools
    from app.services.retrieval import search_wiki_layer

    if name == "search_wiki":
        # 直接调底层 retrieval 函数,query_tools.search_wiki 是 agent 不用的包装
        query = args.get("query", "")
        layer = args.get("layer", "all")
        top_k = args.get("top_k", 5)
        if store is None:
            return json.dumps({"results": [], "count": 0, "note": "store not provided"}, ensure_ascii=False)
        results = search_wiki_layer(course_id, query, layer, top_k, store)

        # CRAG 门控:检查检索结果的最高分,控制 LLM 回答边界
        max_score = max((r.get("score", 0) for r in results), default=0)
        payload: dict[str, Any] = {"results": results, "count": len(results)}
        if not results or max_score < 0.55:
            payload["note"] = "检索结果与问题无关，可能超出课程范围。请诚实拒答。"
        elif max_score < 0.72:
            payload["note"] = "检索结果相关性较低，请谨慎回答。"
        return json.dumps(payload, ensure_ascii=False)

    if name == "get_course_map":
        return query_tools.get_course_map(course_id, store)

    if name == "get_concept":
        return query_tools.get_concept(course_id, args.get("concept_id", ""), store)

    if name == "get_chapter_outline":
        return query_tools.get_chapter_outline(course_id, args.get("chapter_id", ""), store)

    if name == "follow_prerequisite":
        depth = args.get("depth", 2)
        return query_tools.follow_prerequisite(course_id, args.get("concept_id", ""), depth, store)

    if name == "get_source_content":
        return query_tools.get_source_content(course_id, args.get("dmap_id", ""), store)

    if name == "get_review_plan":
        plan = store.get_review_plan(course_id) if store else None
        if not plan:
            return json.dumps({"note": "暂无复习计划"}, ensure_ascii=False)
        return json.dumps(
            {
                "remaining_days": plan.remaining_days,
                "daily_plan": [
                    {
                        "day": d.day_index,
                        "focus": d.focus,
                        "minutes": d.suggested_minutes,
                        "priority": d.priority,
                    }
                    for d in plan.daily_plan
                ],
                "likely_exam_points": plan.likely_exam_points,
                "weak_areas": plan.weak_areas,
            },
            ensure_ascii=False,
        )

    return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)


async def _execute_skill(name: str, args: dict, course_id: str, store: Any) -> str:
    """路由注册的 Skills 到对应 handler。"""
    from app.services.skills import get_skill
    skill = get_skill(name)
    if skill is None:
        return json.dumps({"error": f"未知 Skill: {name}"}, ensure_ascii=False)
    try:
        result = await skill.handler(course_id=course_id, store=store, **args)
        return result
    except Exception as e:
        logger.exception("Skill %s execution failed", name)
        return json.dumps({"error": f"Skill {name} 执行失败: {e}"}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 引用提取
# ---------------------------------------------------------------------------


def _extract_citations(text: str) -> list[dict]:
    """从回答文本中提取 `来自 [文件名] · 第X部分` 格式的内联引用。"""
    citations: list[dict] = []
    seen: set[str] = set()

    patterns = [
        re.compile(r"来自\s*\[?(.+?)\]?\s*·\s*(第.+?部分)"),
        re.compile(r"\[(.+?)\]\s*·\s*(第.+?部分)"),
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


def _dedup_sources_for_citation_fallback(collected: list[dict]) -> list[dict]:
    """LLM 没在回答中嵌入引用时, 用工具结果里的 source 顶上。"""
    out: list[dict] = []
    seen: set[str] = set()
    for s in collected:
        file_name = s.get("file_name", "")
        locator = s.get("locator", "")
        if not file_name:
            continue
        key = f"{file_name}|{locator}"
        if key not in seen:
            seen.add(key)
            out.append({"file_name": file_name, "locator": locator})
    return out
