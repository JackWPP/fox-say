"""agent_chat ReAct 循环测试(全部 mock LLM, 不真调 API)。

覆盖:
- 单轮无 tool_call → yield done
- 单轮有 tool_call → 执行后第二轮给 content → yield done
- max rounds 全是 tool_call → 强制生成"基于现有信息"回答, 不无限循环
- LLM 抛异常 → yield {type: "error", ...}, 不静默
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.services import agent


# ---------------------------------------------------------------------------
# Mock OpenAI 响应构造器
# ---------------------------------------------------------------------------


def _msg_with_content(content: str) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=None)


def _msg_with_tool_call(
    tool_name: str, args: dict, call_id: str = "call_1"
) -> SimpleNamespace:
    tc = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=tool_name, arguments=json.dumps(args, ensure_ascii=False)),
        type="function",
    )
    return SimpleNamespace(content=None, tool_calls=[tc])


def _fake_response(message: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


# ---------------------------------------------------------------------------
# 通用 mock LLM client
# ---------------------------------------------------------------------------


class _MockLLMClient:
    """一个简单的 OpenAI 客户端 mock, 每次 create() 返回下一个预制 response。"""

    def __init__(self, responses: list[SimpleNamespace], raise_after: int | None = None) -> None:
        self._responses = list(responses)
        self._raise_after = raise_after
        self.calls = 0
        parent = self

        class _Completions:
            def create(self_inner, **kwargs: Any) -> SimpleNamespace:
                parent.calls += 1
                if parent._raise_after is not None and parent.calls > parent._raise_after:
                    raise RuntimeError("simulated LLM failure")
                idx = parent.calls - 1
                if idx < len(parent._responses):
                    return parent._responses[idx]
                # 兜底,避免 None
                return _fake_response(_msg_with_content("(no more responses)"))

        self.chat = SimpleNamespace(completions=_Completions())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _collect(agen):
    out = []
    async for ev in agen:
        out.append(ev)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_agent_chat_no_tool_call_yields_done(monkeypatch):
    """LLM 直接返回 content, 无 tool_call → yield done 事件。"""
    client = _MockLLMClient([_fake_response(_msg_with_content("你好!"))])
    monkeypatch.setattr(agent, "_get_client", lambda: client)

    events = asyncio.run(_collect(agent.agent_chat("c1", "微积分", "讲讲极限")))

    types = [e["type"] for e in events]
    assert "done" in types
    done = next(e for e in events if e["type"] == "done")
    assert done["answer"] == "你好!"
    assert client.calls == 1


def test_agent_chat_with_tool_call_executes(monkeypatch):
    """第一次 tool_call, 第二次 content → 工具被执行 + 最终 done。"""
    store = SimpleNamespace(get_review_plan=lambda cid: None)

    def _fake_get_course_map(course_id, store):
        return json.dumps({"note": "课程索引尚未生成"}, ensure_ascii=False)
    monkeypatch.setattr("app.services.query_tools.get_course_map", _fake_get_course_map)

    r1 = _fake_response(_msg_with_tool_call("get_course_map", {}))
    r2 = _fake_response(_msg_with_content("课程索引如下..."))
    client = _MockLLMClient([r1, r2])
    monkeypatch.setattr(agent, "_get_client", lambda: client)

    events = asyncio.run(_collect(agent.agent_chat("c1", "微积分", "课程结构", store=store)))

    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "done" in types
    tc = next(e for e in events if e["type"] == "tool_call")
    assert tc["tool"] == "get_course_map"
    done = next(e for e in events if e["type"] == "done")
    assert "课程索引" in done["answer"]
    assert client.calls == 2


def test_agent_chat_max_rounds_force_answer(monkeypatch):
    """LLM 一直返回 tool_call → max rounds 后强制生成回答, 不无限循环。"""
    store = SimpleNamespace(get_review_plan=lambda cid: None)

    def _fake_get_course_map(course_id, store):
        return json.dumps({"note": "课程索引尚未生成"}, ensure_ascii=False)
    monkeypatch.setattr("app.services.query_tools.get_course_map", _fake_get_course_map)

    r1 = _fake_response(_msg_with_tool_call("get_course_map", {}))
    r2 = _fake_response(_msg_with_tool_call("get_course_map", {}))
    r3 = _fake_response(_msg_with_tool_call("get_course_map", {}))
    r4 = _fake_response(_msg_with_content("基于已有信息: 没找到索引"))
    client = _MockLLMClient([r1, r2, r3, r4])
    monkeypatch.setattr(agent, "_get_client", lambda: client)

    events = asyncio.run(_collect(agent.agent_chat("c1", "微积分", "x", store=store)))

    types = [e["type"] for e in events]
    assert "done" in types
    # 3 轮 ReAct + 1 强制回答 = 4 次
    assert client.calls == 4
    done = next(e for e in events if e["type"] == "done")
    assert "基于已有信息" in done["answer"]


def test_agent_chat_llm_error_yields_error(monkeypatch):
    """LLM 抛异常 → yield {type: 'error', message: '...'}, 不静默。"""
    # 第一次 create() 就抛异常:raise_after=0 → 1 > 0 触发
    client = _MockLLMClient([], raise_after=0)
    monkeypatch.setattr(agent, "_get_client", lambda: client)

    events = asyncio.run(_collect(agent.agent_chat("c1", "微积分", "x")))

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert "LLM" in error_events[0]["message"] or "失败" in error_events[0]["message"]


def test_agent_chat_max_rounds_llm_error_yields_error(monkeypatch):
    """max rounds 强制回答那一步 LLM 抛异常 → 也 yield error。"""
    store = SimpleNamespace(get_review_plan=lambda cid: None)

    def _fake_get_course_map(course_id, store):
        return json.dumps({"note": "no"}, ensure_ascii=False)
    monkeypatch.setattr("app.services.query_tools.get_course_map", _fake_get_course_map)

    r1 = _fake_response(_msg_with_tool_call("get_course_map", {}))
    r2 = _fake_response(_msg_with_tool_call("get_course_map", {}))
    r3 = _fake_response(_msg_with_tool_call("get_course_map", {}))
    # 3 轮 ReAct 正常, 强制回答那一步抛异常
    client = _MockLLMClient([r1, r2, r3], raise_after=3)
    monkeypatch.setattr(agent, "_get_client", lambda: client)

    events = asyncio.run(_collect(agent.agent_chat("c1", "微积分", "x", store=store)))

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) >= 1
