"""Skill 注册机制 — Agent 可调用的结构化能力单元。

设计原则:
- 新增 Skill 只需写一个函数 + @register_skill 装饰器
- Agent 的 TOOLS 列表从 SKILL_REGISTRY 动态构建
- 不改 Agent 代码即可扩展能力

Skill 分类:
- query: 只读查询(现有 7 个工具)
- generate: 生成内容(讲义、练习题、闪卡)
- interactive: 交互式展示(图谱、公式)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class SkillDef:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    category: str  # "query" | "generate" | "interactive"


SKILL_REGISTRY: dict[str, SkillDef] = {}


def register_skill(
    name: str,
    description: str,
    parameters: dict[str, Any],
    category: str = "generate",
):
    """注册一个 Skill,自动转为 Agent tool。"""
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        SKILL_REGISTRY[name] = SkillDef(
            name=name,
            description=description,
            parameters=parameters,
            handler=fn,
            category=category,
        )
        return fn
    return decorator


def get_skill(name: str) -> SkillDef | None:
    """获取已注册的 Skill。"""
    return SKILL_REGISTRY.get(name)


def list_skills() -> list[SkillDef]:
    """列出所有已注册的 Skill。"""
    return list(SKILL_REGISTRY.values())


def build_tools() -> list[dict[str, Any]]:
    """从 SKILL_REGISTRY 动态构建 Agent TOOLS 列表。"""
    tools: list[dict[str, Any]] = []
    for skill in SKILL_REGISTRY.values():
        tools.append({
            "type": "function",
            "function": {
                "name": skill.name,
                "description": skill.description,
                "parameters": skill.parameters,
            },
        })
    return tools


# ---------------------------------------------------------------------------
# 内置 Skills
# ---------------------------------------------------------------------------


@register_skill(
    "generate_lecture",
    "生成章节讲义。从 KC + Wiki 提取内容,生成结构化 Markdown 讲义(含公式和来源引用)。",
    {
        "type": "object",
        "properties": {
            "chapter_id": {"type": "string", "description": "章节 ID (如 ch-1)"},
            "depth": {
                "type": "string",
                "enum": ["brief", "detailed"],
                "default": "brief",
                "description": "brief=概要讲义, detailed=详细讲义",
            },
        },
        "required": ["chapter_id"],
    },
    category="generate",
)
async def generate_lecture_skill(
    course_id: str, chapter_id: str, depth: str = "brief", store: Any = None
) -> str:
    """从 KC + Wiki 生成结构化讲义。"""
    if store is None:
        return json.dumps({"error": "store not available"}, ensure_ascii=False)

    # 获取章节 KC (支持 ch-2 和 ch2 两种格式)
    kcs = store.get_kcs_by_course(course_id, include_invalid=False)
    normalized_id = chapter_id.replace("-", "")
    chapter_kcs = [kc for kc in kcs if kc.chapter_id == chapter_id or kc.chapter_id == normalized_id]
    if not chapter_kcs:
        return json.dumps({"error": f"章节 {chapter_id} 没有找到 KC"}, ensure_ascii=False)

    # 获取章节 Wiki
    cw = store.get_chapter_wiki(chapter_id)

    # 构建讲义内容
    parts: list[str] = []
    title = cw.title if cw else chapter_id
    parts.append(f"# {title}\n")

    if cw and cw.overview:
        parts.append(f"## 概述\n{cw.overview}\n")

    for kc in chapter_kcs:
        parts.append(f"## {kc.name}\n")
        if kc.definition:
            parts.append(f"**定义**: {kc.definition}\n")
        if kc.formula:
            parts.append(f"**公式**: `{kc.formula}`\n")
        if kc.intuition:
            parts.append(f"**直觉**: {kc.intuition}\n")
        if kc.conditions:
            parts.append(f"**条件**: {', '.join(kc.conditions)}\n")
        if kc.examples:
            parts.append("**例子**:")
            for ex in kc.examples[:3]:
                parts.append(f"- {ex}")
            parts.append("")
        if kc.common_mistakes:
            parts.append("**常见错误**:")
            for m in kc.common_mistakes[:2]:
                parts.append(f"- {m}")
            parts.append("")

    content = "\n".join(parts)
    return json.dumps({
        "content": content,
        "chapter_id": chapter_id,
        "kc_count": len(chapter_kcs),
        "depth": depth,
    }, ensure_ascii=False)


@register_skill(
    "generate_quiz",
    "生成章节练习题。从 KC 生成选择题/填空题/证明题,含答案和解析。",
    {
        "type": "object",
        "properties": {
            "chapter_id": {"type": "string", "description": "章节 ID"},
            "count": {"type": "integer", "default": 5, "description": "题目数量"},
            "type": {
                "type": "string",
                "enum": ["choice", "fill", "proof", "mixed"],
                "default": "mixed",
                "description": "题目类型",
            },
        },
        "required": ["chapter_id"],
    },
    category="generate",
)
async def generate_quiz_skill(
    course_id: str, chapter_id: str, count: int = 5, type: str = "mixed", store: Any = None
) -> str:
    """从 KC 生成练习题。"""
    if store is None:
        return json.dumps({"error": "store not available"}, ensure_ascii=False)

    kcs = store.get_kcs_by_course(course_id, include_invalid=False)
    normalized_id = chapter_id.replace("-", "")
    chapter_kcs = [kc for kc in kcs if kc.chapter_id == chapter_id or kc.chapter_id == normalized_id]
    if not chapter_kcs:
        return json.dumps({"error": f"章节 {chapter_id} 没有找到 KC"}, ensure_ascii=False)

    # 生成练习题
    questions: list[dict] = []
    for i, kc in enumerate(chapter_kcs[:count]):
        q_type = type if type != "mixed" else ["choice", "fill", "proof"][i % 3]
        question: dict = {
            "id": f"q-{chapter_id}-{i+1}",
            "type": q_type,
            "kc_name": kc.name,
            "kc_id": kc.id,
        }

        if q_type == "choice":
            question["question"] = f"关于 {kc.name}，以下哪个说法是正确的？"
            question["options"] = [
                f"A. {kc.definition}" if kc.definition else f"A. {kc.name}是一种数学概念",
                f"B. {kc.name}与先修概念无关",
                f"C. {kc.name}只在考试中出现",
                f"D. {kc.name}没有实际应用",
            ]
            question["answer"] = "A"
            question["explanation"] = kc.definition or f"{kc.name}是本章的核心概念。"

        elif q_type == "fill":
            question["question"] = f"请填写：{kc.name}的定义是______。"
            question["answer"] = kc.definition or kc.name
            question["explanation"] = f"根据课程材料，{kc.name}的定义如上。"

        else:  # proof
            question["question"] = f"请简述 {kc.name} 的核心思想。"
            question["answer"] = kc.intuition or kc.definition or f"{kc.name}是本章的重要概念。"
            question["explanation"] = kc.intuition or kc.definition

        questions.append(question)

    return json.dumps({
        "questions": questions,
        "chapter_id": chapter_id,
        "total": len(questions),
    }, ensure_ascii=False)


@register_skill(
    "generate_flashcards",
    "生成章节闪卡。从 KC 生成 front(问题)/back(答案) 对,用于快速复习。",
    {
        "type": "object",
        "properties": {
            "chapter_id": {"type": "string", "description": "章节 ID"},
            "count": {"type": "integer", "default": 10, "description": "闪卡数量"},
        },
        "required": ["chapter_id"],
    },
    category="generate",
)
async def generate_flashcards_skill(
    course_id: str, chapter_id: str, count: int = 10, store: Any = None
) -> str:
    """从 KC 生成闪卡。"""
    if store is None:
        return json.dumps({"error": "store not available"}, ensure_ascii=False)

    kcs = store.get_kcs_by_course(course_id, include_invalid=False)
    normalized_id = chapter_id.replace("-", "")
    chapter_kcs = [kc for kc in kcs if kc.chapter_id == chapter_id or kc.chapter_id == normalized_id]
    if not chapter_kcs:
        return json.dumps({"error": f"章节 {chapter_id} 没有找到 KC"}, ensure_ascii=False)

    cards: list[dict] = []
    for kc in chapter_kcs[:count]:
        card: dict = {"kc_id": kc.id, "kc_name": kc.name}

        # Front: 问题
        if kc.formula:
            card["front"] = f"{kc.name} 的公式是什么？"
        elif kc.definition:
            card["front"] = f"什么是 {kc.name}？"
        else:
            card["front"] = f"请解释 {kc.name}。"

        # Back: 答案
        back_parts: list[str] = []
        if kc.definition:
            back_parts.append(kc.definition)
        if kc.formula:
            back_parts.append(f"公式: `{kc.formula}`")
        if kc.intuition:
            back_parts.append(f"直觉: {kc.intuition}")
        card["back"] = "\n".join(back_parts) if back_parts else kc.name

        cards.append(card)

    return json.dumps({
        "cards": cards,
        "chapter_id": chapter_id,
        "total": len(cards),
    }, ensure_ascii=False)


@register_skill(
    "show_concept_graph",
    "显示概念的知识图谱。返回指定概念的先修链路和相关概念,用于可视化展示。",
    {
        "type": "object",
        "properties": {
            "concept_id": {"type": "string", "description": "KC ID"},
            "depth": {"type": "integer", "default": 2, "description": "遍历深度"},
        },
        "required": ["concept_id"],
    },
    category="interactive",
)
async def show_concept_graph_skill(
    course_id: str, concept_id: str, depth: int = 2, store: Any = None
) -> str:
    """返回概念的先修链路和相关概念。"""
    if store is None:
        return json.dumps({"error": "store not available"}, ensure_ascii=False)

    kc = store.get_kc(concept_id)
    if kc is None:
        return json.dumps({"error": f"未找到概念 {concept_id}"}, ensure_ascii=False)
    if kc.course_id != course_id:
        return json.dumps({"error": f"概念 {concept_id} 不属于课程 {course_id}"}, ensure_ascii=False)

    # 获取先修链路
    prerequisites: list[dict] = []
    if kc.prerequisites:
        for p in kc.prerequisites:
            prereq_kc = store.get_kc(p.prerequisite_kc_id)
            if prereq_kc:
                prerequisites.append({
                    "id": prereq_kc.id,
                    "name": prereq_kc.name,
                    "definition": prereq_kc.definition[:100] if prereq_kc.definition else "",
                })

    # 获取相关概念(同一章节的其他 KC)
    all_kcs = store.get_kcs_by_course(course_id, include_invalid=False)
    related = [
        {"id": k.id, "name": k.name}
        for k in all_kcs
        if k.chapter_id == kc.chapter_id and k.id != kc.id
    ][:5]

    return json.dumps({
        "concept": {
            "id": kc.id,
            "name": kc.name,
            "definition": kc.definition,
            "formula": kc.formula,
            "chapter_id": kc.chapter_id,
        },
        "prerequisites": prerequisites,
        "related": related,
        "depth": depth,
    }, ensure_ascii=False)
