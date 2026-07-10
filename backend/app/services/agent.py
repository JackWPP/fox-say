"""FoxSay Agent 主循环 + 7 工具集。

设计原则:
- ReAct 循环 max 8 轮(复杂跨章节问题需要多步工具调用)
- 错误必须可见(HEC-1):LLM 失败时 SSE 推 {type: "error", message: "..."}
- schema 显式带 course_id(HEC-6):所有 query 工具入参都接收 course_id, 禁止反推
- DSML 防御:DeepSeek 模型可能输出伪工具调用语法,必须正确处理不烧轮次
- 工具容错:get_concept/get_chapter_outline 支持名称模糊查找,ID 未知时不卡住
- 无进展检测:连续相同工具调用强制跳出,防止死循环

工具集(7 个):
  search_wiki          三层混合检索(章节+KC+chunk)
  get_course_map       拿课程索引全文
  get_concept          按 ID 或名称拿完整 KC 卡
  get_chapter_outline  按 chapter_id 或标题拿章节摘要
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
        _client = OpenAI(api_key=api_key, base_url=settings.deepseek_api_base, timeout=60)
    return _client


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "你是 FoxSay, 一只聪明但有点皮的小狐狸, 也是这门课的 AI 学习伙伴。\n\n"
    "## 教学法原则\n"
    "1. **费曼技巧优先**: 解释任何概念时，先用最简单直白的语言讲清楚核心直觉"
    "（可以用生活类比、生动例子），然后再给出正式定义，最后举 1-2 个具体例子。\n"
    "2. **预判误解**: 主动提醒学生容易搞混的点、常见陷阱、与相似概念的区别。\n"
    "3. **公式推导**: 涉及公式时，先讲「这个公式在说什么、为什么合理」，"
    "再给数学表达，最后说明每个符号的含义。\n"
    "4. **小狐狸语气**: 语言生动活泼，可以偶尔带点小调皮，但不要油腻。"
    "像一个聪明的学长/学姐在给你讲题。\n"
    "5. **结尾延伸**: 每次回答完，主动提一个值得思考的延伸问题，引导深入思考。\n"
    "6. **模糊追问**: 如果问题太模糊（比如只说「讲讲这个」），先礼貌追问具体想了解哪方面，"
    "不要猜着答。\n\n"
    "## 核心规则\n"
    "1. 优先基于当前课程材料回答。当材料不足以回答时，可以用通用知识补充，"
    "但必须明确声明「课程材料中未覆盖此内容，以下是通用理解，建议对照教材确认」。\n"
    "2. 引用材料时，必须用格式 `来自 [文件名] · 第X部分`，在正文中自然嵌入。\n"
    "   引用笔记时，必须用格式 `来自笔记 · [笔记标题]`。\n"
    "3. 回答用 Markdown 排版，有清晰的结构（标题、列表、加粗重点），但不要过度分节。\n"
    "4. **数学公式格式**: 所有数学公式必须用标准 LaTeX 格式并用分隔符包裹：\n"
    "   - 行内公式用单个美元符号：`$P(A|B) = \\frac{P(AB)}{P(B)}$`\n"
    "   - 独立公式块用双美元符号：`$$P(A|B) = \\frac{P(AB)}{P(B)}$$`\n"
    "   - 不要用纯文本写公式（如 'P(A|B) = P(AB)/P(B)'），必须用 LaTeX 渲染。\n"
    "   - **重要**：美元符号`$`只能用于包裹真正的数学公式，绝不能包裹普通中文词汇、\n"
    "     术语名称或非数学文本（错误示例：`$病因$`、`$阴阳$`、`$概念$`）。普通强调请用**加粗**。\n"
    "   - 常用符号：\\frac{}{}（分数）、\\cap（交集）、\\cup（并集）、\\sum（求和）、"
    "\\int（积分）、\\geq/\\leq（大于等于/小于等于）、\\cdot（乘号）。\n\n"
    "## 工具使用策略（重要！）\n"
    "- **第一步永远是 search_wiki**: 任何问题先用 `search_wiki` 搜索相关材料，"
    "获取 concept_id/chapter_id 等 ID 后再调用其他工具。不要猜测 ID！\n"
    "- **定义/是什么类问题**: 先用 `search_wiki` 找到概念，再用 `get_concept` 获取完整 KC 卡。\n"
    "- **比较/对比类问题**: 先用 `search_wiki` 获取多个相关 KC，再对比分析。\n"
    "- **为什么/原理类问题**: 先用 `search_wiki` 找到概念，再用 `follow_prerequisite` 追溯先修知识。\n"
    "- **全局/课程结构问题**: 用 `get_course_map`。\n"
    "- **具体章节内容**: 先用 `search_wiki` 找到章节，再用 `get_chapter_outline`。\n"
    "- **复习相关问题**: 用 `get_review_plan`。\n"
    "- 如果不知道 concept_id 或 chapter_id，传 concept_name 或 chapter_title 进行模糊查找。\n"
    "- 如果工具返回错误或未找到，不要用相同参数重复调用，换一种方式或用 search_wiki 重新搜索。\n"
    "- 如果 `search_wiki` 返回的 note 提示「检索结果与问题无关」，"
    "说明课程材料未覆盖此内容。你可以基于通用知识回答，但必须声明这是补充说明，不是来自课程材料。\n"
    "- 获得足够信息后直接回答，不要做不必要的工具调用。\n"
    "- **工具调用预算**: 你最多有 8 轮工具调用机会。绝大多数问题 1-3 轮即可解决，请高效使用。\n"
    "- **动态能力(Skill)**: 除了上述查询工具，你还可以使用以下能力：\n"
    "  - `generate_lecture`: 生成章节讲义(学生在请求「讲解」「讲义」时使用)\n"
    "  - `generate_quiz`: 生成练习题(学生在请求「出题」「练习」时使用)\n"
    "  - `generate_flashcards`: 生成闪卡(学生在请求「闪卡」「快速复习」时使用)\n"
    "  - `show_concept_graph`: 显示概念先修图谱(学生在请求「知识图谱」「关系图」时使用)\n"
    "  - Skill 会直接生成最终内容，调用后无需再调用其他工具。\n"
    "  - **不要在 search_wiki 之前调用 Skill**——先搜索确认概念存在再生成内容。\n"
    "- **follow_prerequisite vs show_concept_graph**: 需要文字追溯先修知识用 follow_prerequisite；"
    "学生请求可视化图谱时用 show_concept_graph。不要同时调用两者。\n"
    "- **get_chapter_outline vs generate_lecture**: 需要章节结构摘要用 get_chapter_outline；"
    "学生请求完整讲义/讲解用 generate_lecture。不要连续调用两者。\n"
)

# ---------------------------------------------------------------------------
# Tools (7 个)
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_wiki",
            "description": "在课程 Wiki 中做语义检索(章节/KC/原始材料三层)。任何问题的第一步都应该用这个工具搜索，获取相关材料和ID。",
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
            "description": "拿课程索引全文(markdown)。用于了解课程全局结构、章节列表。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_concept",
            "description": "获取知识点(KC)的完整内容：定义、公式、常见错误等。如果不知道concept_id，可以传concept_name按名称模糊查找。",
            "parameters": {
                "type": "object",
                "properties": {
                    "concept_id": {"type": "string", "description": "KC ID（从search_wiki结果获取）"},
                    "concept_name": {"type": "string", "description": "概念名称（当不知道ID时，按名称模糊查找）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chapter_outline",
            "description": "获取章节摘要(overview, 重点, 难点)。如果不知道chapter_id，可以传chapter_title按标题模糊查找。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_id": {"type": "string", "description": "章节ID（从search_wiki结果获取）"},
                    "chapter_title": {"type": "string", "description": "章节标题（当不知道ID时，按标题模糊查找）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "follow_prerequisite",
            "description": "沿知识点的先修链向上回溯,返回先修概念列表。需要concept_id（从search_wiki或get_concept结果获取）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "concept_id": {"type": "string", "description": "起点 KC ID"},
                    "depth": {
                        "type": "integer",
                        "default": 2,
                        "description": "回溯深度,默认 2",
                    },
                },
                "required": ["concept_id"],
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
                    "dmap_id": {"type": "string", "description": "DMAP 节点或元素 ID"},
                },
                "required": ["dmap_id"],
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

MAX_ROUNDS = 8

# ---------------------------------------------------------------------------
# DSML defense layer
# ---------------------------------------------------------------------------
# Some DeepSeek models emit a fake tool-call syntax in `content` text instead
# of using the real `tool_calls` field. We strip it and provide clear feedback
# to prevent infinite DSML loops.

_PIPE = r"[|｜]+"

_DSML_ANY_TAG_RE = re.compile(
    rf"<\s*{_PIPE}\s*DSML\s*{_PIPE}[^>]*>.*?<\s*/\s*{_PIPE}\s*DSML\s*{_PIPE}[^>]*>",
    re.DOTALL,
)
_DSML_ORPHAN_RE = re.compile(rf"</?\s*{_PIPE}\s*DSML\s*{_PIPE}[^>]*>")


def _strip_dsml_blocks(content: str) -> str:
    """Remove all DSML tags from text (defense in depth)."""
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
    selected_source_ids: list[str] | None = None,
    selected_note_ids: list[str] | None = None,
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
    dsml_streak = 0
    last_tool_key: str | None = None
    repeat_count = 0
    tool_history: list[str] = []
    search_wiki_count = 0
    force_answer = False

    for _round in range(MAX_ROUNDS):
        # 中期检查：round 5时如果还没收集到source且仍在调工具，强制回答
        if _round >= 5 and not collected_sources and not force_answer:
            logger.warning("Round %d with no sources collected, forcing answer", _round)
            messages.append({
                "role": "system",
                "content": (
                    "你已经调用了多次工具但还没有找到相关材料。"
                    "课程材料可能没有覆盖这个问题。请基于你的通用知识给出有帮助的回答，"
                    "同时明确声明「课程材料中未覆盖此内容，以下是通用理解，建议对照教材确认」。"
                    "不要继续无意义的工具调用。"
                ),
            })
            force_answer = True
            break

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
            logger.exception("LLM call failed in agent loop round %d", _round)
            yield {"type": "error", "message": "AI 连接失败, 请检查网络后重试"}
            return

        msg = response.choices[0].message

        # ---- DSML guard ----
        dsml_in_content = bool(msg.content) and "DSML" in msg.content
        if dsml_in_content:
            dsml_streak += 1
            logger.info("DSML detected in content (round %d, streak %d)", _round, dsml_streak)
            cleaned_content = _strip_dsml_blocks(msg.content or "")
            messages.append({
                "role": "assistant",
                "content": cleaned_content if cleaned_content else "[DSML tags removed]",
            })
            if dsml_streak >= 2:
                logger.warning("DSML streak >= 2, forcing final answer")
                messages.append({
                    "role": "system",
                    "content": (
                        "你多次输出了非法的工具调用语法。请不要再尝试调用工具，"
                        "直接用中文文字基于已有信息给出回答。如果材料不足，请诚实说明。"
                    ),
                })
                break
            messages.append({
                "role": "system",
                "content": (
                    "你刚才的回复里包含了非法的工具调用语法(DSML)，已为你清理。"
                    "请使用 `tool_calls` 字段调用工具（用JSON格式），或直接用中文文字给出最终回答。"
                    "不要在文字内容中写工具调用标记。"
                ),
            })
            continue

        dsml_streak = 0

        # 无 tool_call → 最终回答
        if not msg.tool_calls:
            answer_text = _strip_dsml_blocks(msg.content or "")
            citations = _extract_citations(answer_text)
            if not citations and collected_sources:
                citations = _dedup_sources_for_citation_fallback(collected_sources)

            if not answer_text:
                answer_text = "（AI 生成了空回复，请换个问法再试试～）"

            yield {
                "type": "done",
                "answer": answer_text,
                "citations": citations,
                "in_scope": True,
                "guard_warning": None,
            }
            return

        # 有 tool_calls → 执行
        for tool_call in msg.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            # 无进展检测：同样的工具+参数重复调用
            current_tool_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True, ensure_ascii=False)}"
            if current_tool_key == last_tool_key:
                repeat_count += 1
                if repeat_count >= 2:
                    logger.warning("Detected repeated tool call %s (%d times), forcing answer", tool_name, repeat_count + 1)
                    messages.append({
                        "role": "system",
                        "content": (
                            f"你已经连续多次调用{tool_name}且参数相同，说明当前路径无法获得更多信息。"
                            "请基于已有搜索结果直接给出回答，不要继续调用相同工具。"
                            "如果材料不足以回答问题，请诚实说明哪些部分无法从材料中找到。"
                        ),
                    })
                    break
            else:
                repeat_count = 0
                last_tool_key = current_tool_key

            # 检测循环调用模式：A→B→A→B 交替
            tool_history.append(tool_name)
            if len(tool_history) >= 4:
                last4 = tool_history[-4:]
                if len(set(last4)) == 2 and last4[0] == last4[2] and last4[1] == last4[3]:
                    logger.warning("Detected alternating tool loop %s, forcing answer", last4)
                    messages.append({
                        "role": "system",
                        "content": (
                            "检测到你在两个工具之间来回调用，这通常意味着无法通过当前路径获得更多信息。"
                            "请基于已有的搜索结果直接给出回答，或诚实说明材料中没有相关内容。"
                        ),
                    })
                    break

            # search_wiki 次数过多警告
            if tool_name == "search_wiki":
                search_wiki_count += 1
                if search_wiki_count >= 3 and len(collected_sources) == 0:
                    logger.warning("search_wiki called %d times with no sources, forcing answer", search_wiki_count)
                    messages.append({
                        "role": "system",
                        "content": (
                            "你已经多次搜索但没有找到相关材料。课程材料可能没有覆盖这个问题。"
                            "请基于你的通用知识给出有帮助的回答，同时明确声明"
                            "「课程材料中未覆盖此内容，以下是通用理解，建议对照教材确认」。"
                        ),
                    })
                    break

            yield {
                "type": "tool_call",
                "tool": tool_name,
                "args": tool_args,
            }

            try:
                tool_result = await _execute_tool(
                    tool_name, tool_args, course_id, store,
                    selected_source_ids=selected_source_ids,
                    selected_note_ids=selected_note_ids,
                )
                if "未知工具" in tool_result:
                    tool_result = await _execute_skill(tool_name, tool_args, course_id, store)
            except Exception as exc:
                logger.exception("Tool %s execution failed", tool_name)
                tool_result = json.dumps({"error": f"工具执行出错: {exc}"}, ensure_ascii=False)

            # Skill 返回内容时直接作为最终回答
            from app.services.skills import get_skill as _get_skill
            if _get_skill(tool_name) is not None:
                try:
                    skill_data = json.loads(tool_result)
                    if "error" not in skill_data:
                        content = skill_data.get("content", "")
                        if content:
                            logger.info("Skill %s returned content (%d chars), stopping loop", tool_name, len(content))
                            citations = _extract_citations(content)
                            yield {
                                "type": "done",
                                "answer": content,
                                "citations": citations,
                                "in_scope": True,
                                "guard_warning": None,
                            }
                            return
                        else:
                            logger.info("Skill %s returned data, using as answer", tool_name)
                            yield {
                                "type": "done",
                                "answer": tool_result,
                                "citations": [],
                                "in_scope": True,
                                "guard_warning": None,
                            }
                            return
                except (json.JSONDecodeError, KeyError):
                    pass

            # 检查工具返回是否有引导性note，如果有则添加到system提示
            tool_note = None
            try:
                result_data = json.loads(tool_result)
                if isinstance(result_data, dict) and result_data.get("note"):
                    tool_note = result_data["note"]
            except (json.JSONDecodeError, ValueError):
                pass

            # 从 search_wiki 结果中收集 source 备用 + 早期相关性检查
            if tool_name == "search_wiki":
                try:
                    data = json.loads(tool_result)
                    new_sources = 0
                    for r in data.get("results", []):
                        src = {
                            "file_name": r.get("file_name", ""),
                            "locator": r.get("locator", ""),
                            "source": r.get("source_ref", ""),
                        }
                        if src["file_name"]:
                            collected_sources.append(src)
                            new_sources += 1

                    # CRAG: score < 0.55 时标注为补充回答，让 LLM 透明回答 (AGENTS.md CRAG Policy)
                    if data.get("_crag_supplementary"):
                        messages.append({
                            "role": "system",
                            "content": (
                                "检索结果表明课程材料中没有覆盖此内容（score < 0.55）。"
                                "请基于你的通用知识给出有帮助的回答，并在回答开头明确声明：\n"
                                "「课程材料中未覆盖此内容，以下是通用理解，建议对照教材确认。」"
                            ),
                        })

                    # 第一次search_wiki低分/空结果时立即引导
                    if _round == 0 and (new_sources == 0 or data.get("note")):
                        note_msg = data.get("note", "未找到相关内容")
                        messages.append({
                            "role": "system",
                            "content": (
                                f"第一次搜索结果提示：{note_msg}。\n"
                                "请考虑：1)换更具体的课程术语重新search_wiki；"
                                "2)如果问题确实与课程材料无关，基于通用知识回答并声明这是补充说明。"
                                "不要继续调用get_concept/get_chapter_outline等需要ID的工具。"
                            ),
                        })
                except (json.JSONDecodeError, KeyError):
                    pass

            # Append assistant tool call + tool result (OpenAI format)
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

            # 如果工具返回note，添加明确引导让LLM注意
            if tool_note and ("未找到" in tool_note or "需要" in tool_note or "请先" in tool_note):
                messages.append({
                    "role": "system",
                    "content": f"工具返回提示：{tool_note}",
                })

        else:
            continue
        break

    # 达到 max rounds 或被强制跳出 → 基于已有信息生成回答
    if force_answer and not collected_sources:
        final_prompt = (
            "你已尝试多次工具调用但未找到相关材料。"
            "课程材料可能没有覆盖这个问题。请基于你的通用知识给出有帮助的回答，"
            "并在回答开头声明「课程材料中未覆盖此内容，以下是通用理解，建议对照教材确认」。"
            "不要编造课程内容，不要继续调用工具。"
        )
    else:
        final_prompt = (
            "请基于已有的工具查询结果，给出你的最终回答。\n"
            "要求：\n"
            "1. 必须引用来源，使用 `来自 [文件名] · 第X部分` 格式。\n"
            "2. 如果工具结果足以回答问题，完整回答。\n"
            "3. 如果工具结果只能部分回答，先基于已有信息回答能确定的部分，"
            "再明确说明哪些部分材料中没有覆盖，绝对不要编造内容。\n"
            "4. 如果工具结果完全不足以回答（没有任何相关来源），"
            "请声明「课程材料中未覆盖此内容，以下是通用理解，建议对照教材确认」，"
            "然后基于通用知识给出有帮助的回答。\n"
            "5. 不要继续调用任何工具，直接给出文字回答。"
        )

    try:
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages + [{"role": "system", "content": final_prompt}],
            temperature=0.3,
            extra_body={"thinking": {"type": "disabled"}},
        )
        answer_text = _strip_dsml_blocks(response.choices[0].message.content or "")
        if not answer_text or len(answer_text.strip()) < 10:
            raise RuntimeError("Empty or too short answer from forced LLM call")
    except Exception as e:
        logger.exception("LLM call failed at forced answer")
        # 降级重试：用更简短的 prompt
        try:
            retry_response = client.chat.completions.create(
                model=settings.deepseek_model,
                messages=messages + [{"role": "system", "content": "请用一两句话简要回答上一个问题。"}],
                temperature=0.5,
                extra_body={"thinking": {"type": "disabled"}},
            )
            answer_text = _strip_dsml_blocks(retry_response.choices[0].message.content or "")
        except Exception:
            answer_text = ""

        if not answer_text or len(answer_text.strip()) < 10:
            if collected_sources:
                unique_sources: list[dict] = []
                seen_keys: set[str] = set()
                for s in collected_sources:
                    key = f"{s.get('file_name','')}|{s.get('locator','')}"
                    if key not in seen_keys and s.get("file_name"):
                        seen_keys.add(key)
                        unique_sources.append(s)
                answer_text = (
                    "我查阅了课程材料，找到了一些相关内容，你可以看看这些来源：\n\n"
                    + "\n".join(f"- 来自 [{s['file_name']}] · {s['locator']}" for s in unique_sources[:5])
                )
            else:
                yield {
                    "type": "error",
                    "message": f"AI 回答生成失败，请换个问法再试试～（多次工具调用后仍无法生成有效回答）",
                }
                return

    citations = _extract_citations(answer_text)
    if not citations and collected_sources:
        citations = _dedup_sources_for_citation_fallback(collected_sources)

    if not answer_text:
        answer_text = "（AI 暂时无法生成有效回答，请换个问法再试试～）"

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


async def _execute_tool(
    name: str,
    args: dict,
    course_id: str,
    store: Any,
    selected_source_ids: list[str] | None = None,
    selected_note_ids: list[str] | None = None,
) -> str:
    """路由工具到对应实现。"""
    from app.services import query_tools
    from app.services.retrieval import search_wiki_layer

    if name == "search_wiki":
        query = args.get("query", "")
        layer = args.get("layer", "all")
        top_k = args.get("top_k", 5)
        if store is None:
            return json.dumps({"results": [], "count": 0, "note": "store not provided"}, ensure_ascii=False)
        results = search_wiki_layer(
            course_id, query, layer, top_k, store,
            selected_material_ids=selected_source_ids,
            selected_note_ids=selected_note_ids,
        )

        max_score = max((r.get("score", 0) for r in results), default=0)
        payload: dict[str, Any] = {"results": results, "count": len(results)}
        if not results or max_score < 0.55:
            payload["note"] = "课程材料中未覆盖此内容。请基于通用知识回答，并声明这是补充说明。"
            payload["_crag_supplementary"] = True
            payload["_max_score"] = max_score
        elif max_score < 0.72:
            payload["note"] = "检索结果相关性较低，请谨慎回答。"
        return json.dumps(payload, ensure_ascii=False)

    if name == "get_course_map":
        return query_tools.get_course_map(course_id, store)

    if name == "get_concept":
        concept_id = args.get("concept_id", "")
        concept_name = args.get("concept_name", "")
        if concept_id:
            result = query_tools.get_concept(course_id, concept_id, store)
            result_data = json.loads(result)
            if "note" not in result_data:
                return result
            # concept_id not found, fall through to name search
        if concept_name:
            return query_tools.get_concept_by_name(course_id, concept_name, store)
        if not concept_id and not concept_name:
            return json.dumps({"note": "请提供 concept_id 或 concept_name。建议先用 search_wiki 搜索获取正确的 ID。"}, ensure_ascii=False)
        return query_tools.get_concept(course_id, concept_id, store)

    if name == "get_chapter_outline":
        chapter_id = args.get("chapter_id", "")
        chapter_title = args.get("chapter_title", "")
        if chapter_id:
            result = query_tools.get_chapter_outline(course_id, chapter_id, store)
            result_data = json.loads(result)
            if "note" not in result_data:
                return result
        if chapter_title:
            return query_tools.get_chapter_by_title(course_id, chapter_title, store)
        if not chapter_id and not chapter_title:
            return json.dumps({"note": "请提供 chapter_id 或 chapter_title。建议先用 search_wiki 搜索获取正确的 ID。"}, ensure_ascii=False)
        return query_tools.get_chapter_outline(course_id, chapter_id, store)

    if name == "follow_prerequisite":
        depth = args.get("depth", 2)
        concept_id = args.get("concept_id", "")
        if not concept_id:
            return json.dumps({"note": "follow_prerequisite 需要 concept_id，请先用 search_wiki 获取。", "prerequisites": []}, ensure_ascii=False)
        return query_tools.follow_prerequisite(course_id, concept_id, depth, store)

    if name == "get_source_content":
        dmap_id = args.get("dmap_id", "")
        if not dmap_id:
            return json.dumps({"note": "get_source_content 需要 dmap_id，请先用 search_wiki 获取。"}, ensure_ascii=False)
        return query_tools.get_source_content(course_id, dmap_id, store)

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
    """从回答文本中提取引用格式。

    支持:
    - `来自 [文件名] · 第X部分` (材料引用)
    - `来自笔记 · [笔记标题]` (笔记引用)
    """
    citations: list[dict] = []
    seen: set[str] = set()

    patterns = [
        re.compile(r"来自笔记\s*·\s*(.+?)(?:[。，,。\n]|$)"),
        re.compile(r"来自\s*\[?(.+?)\]?\s*·\s*(第.+?部分)"),
        re.compile(r"\[(.+?)\]\s*·\s*(第.+?部分)"),
        re.compile(r"([\w一-鿿.-]+\.(?:pdf|ppt|txt|md))\s*·\s*(第.+?部分)"),
    ]

    for pattern in patterns:
        for match in pattern.finditer(text):
            groups = match.groups()
            if len(groups) == 1 and "笔记" in pattern.pattern:
                file_name = "笔记"
                locator = groups[0].strip()
            elif len(groups) >= 2:
                file_name = groups[0].strip()
                locator = groups[1].strip()
            else:
                continue
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
