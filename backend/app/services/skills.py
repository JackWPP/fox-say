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
