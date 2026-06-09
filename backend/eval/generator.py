"""Pilot 集生成器。

调用 DeepSeek,一题一次 chat completion,产出 30 题 EvalCase:
- 8 definition
- 10 derivation
- 5 cross_chapter
- 4 refusal
- 3 ambiguous

参考:research_result/FoxSay RAG 评测设计.md "Ground Truth 字段规范"。
当课程的 KC 数量为 0 时,生成器会**多生成 answerability=False** 的题
(即多 4 题 refusal),让 30 题里始终有拒答题覆盖。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from openai import OpenAI

from app.core.config import settings
from app.schemas.foxsay import Citation, KC

from backend.eval.schemas import EvalCase, PilotCase, PilotSuite

logger = logging.getLogger(__name__)

# 30 题分布
DEFAULT_DISTRIBUTION: dict[str, int] = {
    "definition": 8,
    "derivation": 10,
    "cross_chapter": 5,
    "refusal": 4,
    "ambiguous": 3,
}

_VALID_BLOOM = {
    "Remembering", "Understanding", "Applying",
    "Analyzing", "Evaluating", "Creating",
}


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=settings.deepseek_api_key or "placeholder",
        base_url=settings.deepseek_api_base,
    )


def _format_kc_list(kcs: list[KC], max_n: int = 20) -> str:
    """把 KC 列表压缩成 LLM 友好的文本行(限前 20 个,避免超 token)。"""
    lines = []
    for kc in kcs[:max_n]:
        chap = kc.chapter_id or "?"
        lines.append(
            f"- [kc_id={kc.id} chapter={chap} name={kc.name} "
            f"bloom={kc.bloom_level} def={(kc.definition or '')[:80]}]"
        )
    return "\n".join(lines) if lines else "(无 KC 数据)"


_SYSTEM_PROMPT = """你是 FoxSay 评测工程师,负责基于一份课程的 KC 列表生成单条评测用例。
你的输出必须是**严格合法**的 JSON,且只能有一个 JSON 对象,不要有 markdown ``` 围栏。
字段约束:
- case_id: 形如 "<COURSE_TAG>-<TYPE_TAG>-<3位序号>",e.g. "LA-DEF-001"
- course_id: 直接复制传入的 course_id
- question: 学生口吻提问,30-150 字
- question_type: 必须从 5 个枚举中选一个
- associated_kc_id: 非空,跨章题/拒答题可以传 null
- bloom_level: 从 6 阶 Bloom 中选(Remembering/Understanding/Applying/Analyzing/Evaluating/Creating)
- gold_answer: 标准答案(50-400 字,定义/推导要具体,拒答要包含"超出范围"类措辞)
- gold_citations: 1-2 条,每条 {file_name, locator}
- gold_evidence_chunks: 1-2 个 Chunk ID(可虚构,e.g. "chunk_LA_p142_01")
- answerability: true / false
- pedagogical_constraint: 1-2 句,给 Judge 看的强教学规约(可空字符串)
"""


def _build_user_prompt(
    course_id: str,
    course_title: str,
    qtype: str,
    kcs: list[KC],
    n: int,
) -> str:
    kc_text = _format_kc_list(kcs)
    return f"""课程: {course_title} (id={course_id})
题型: {qtype} (这是第 1 / 仅 1 题,不要输出多个 JSON)

可选 KC 列表(请挑选最贴切的一个作为 associated_kc_id,如果跨章题可传 null):
{kc_text}

请输出严格 JSON。"""


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 输出里抠 JSON,容忍 markdown ```json ... ``` 围栏。"""
    text = text.strip()
    # 去掉 markdown 围栏
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # 尝试直接 parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 兜底:找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"无法从 LLM 输出解析 JSON: {text[:200]}")


def _normalize_case_id(raw: str, course_id: str, qtype: str, seq: int) -> str:
    """保证 case_id 形如 <COURSE_TAG>-<TYPE_TAG>-<NNN>。"""
    if not raw or "-" not in raw:
        course_tag = "".join(c for c in course_id.upper() if c.isalnum())[:6] or "C"
        type_tag = {
            "definition": "DEF",
            "derivation": "DER",
            "cross_chapter": "XCH",
            "refusal": "REF",
            "ambiguous": "AMB",
        }[qtype]
        return f"{course_tag}-{type_tag}-{seq:03d}"
    return raw


def _coerce_bloom(raw: str | None) -> str:
    if not raw:
        return "Understanding"
    # 容错:把 "apply" → "Applying", "analyze" → "Analyzing" ...
    lower = raw.strip().lower()
    for b in _VALID_BLOOM:
        if lower == b.lower() or lower == b.lower().rstrip("e") + "e":
            return b
    # 取首字母
    if lower.startswith("rem"):
        return "Remembering"
    if lower.startswith("und") or lower.startswith("com"):
        return "Understanding"
    if lower.startswith("app"):
        return "Applying"
    if lower.startswith("ana"):
        return "Analyzing"
    if lower.startswith("eva"):
        return "Evaluating"
    if lower.startswith("cre"):
        return "Creating"
    return "Understanding"


def generate_one(
    course_id: str,
    course_title: str,
    qtype: str,
    kcs: list[KC],
    seq: int,
    client: OpenAI | None = None,
    llm_call: Callable[[str, str], str] | None = None,
) -> PilotCase:
    """单题一次 LLM 调用,生成一条 PilotCase。

    llm_call: 可选注入,签名 (system, user) → str。默认走 DeepSeek。
    """
    if llm_call is None:
        c = client or _get_client()

        def llm_call(system: str, user: str) -> str:
            resp = c.chat.completions.create(
                model=settings.deepseek_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
            )
            return resp.choices[0].message.content or ""

    user_prompt = _build_user_prompt(course_id, course_title, qtype, kcs, 1)
    raw_text = llm_call(_SYSTEM_PROMPT, user_prompt)
    data = _extract_json(raw_text)

    # 修补 case_id
    data["case_id"] = _normalize_case_id(
        data.get("case_id", ""), course_id, qtype, seq
    )
    data["course_id"] = course_id
    data["question_type"] = qtype
    data["bloom_level"] = _coerce_bloom(data.get("bloom_level"))

    # 拒答题 answerability 强制 False
    if qtype == "refusal":
        data["answerability"] = False

    # associated_kc_id 必须真在 KC 列表里,否则 None
    kc_ids = {kc.id for kc in kcs}
    akc = data.get("associated_kc_id")
    if akc and akc not in kc_ids:
        data["associated_kc_id"] = None

    # gold_citations 转 Citation 对象
    raw_cites = data.pop("gold_citations", []) or []
    cites: list[Citation] = []
    for c in raw_cites:
        if isinstance(c, dict) and "file_name" in c and "locator" in c:
            cites.append(Citation(file_name=c["file_name"], locator=c["locator"]))
    data["gold_citations"] = cites

    eval_case = EvalCase.model_validate(data)
    return PilotCase(
        eval_case=eval_case,
        generator_model=settings.deepseek_model,
    )


def generate_suite(
    course_id: str,
    course_title: str,
    kcs: list[KC],
    distribution: dict[str, int] | None = None,
    llm_call: Callable[[str, str], str] | None = None,
) -> PilotSuite:
    """生成 30 题 pilot 集。

    流程:
    1. 校验 KC 数量:0 → 多分配 4 题 refusal(其它题仍然按 default 跑)
    2. 按 distribution 顺序生成,一题一调用
    3. 聚合为 PilotSuite
    """
    dist = dict(distribution or DEFAULT_DISTRIBUTION)
    if not kcs:
        # 课程无 KC:把 refusal 比例调高,确保有拒答覆盖
        dist["refusal"] = dist.get("refusal", 4) + 4
        dist["derivation"] = max(0, dist.get("derivation", 10) - 4)
        logger.warning("KC 数量=0,refusal 分配调整到 %d", dist["refusal"])

    cases: list[PilotCase] = []
    seq = 1
    for qtype, n in dist.items():
        if n <= 0:
            continue
        for _ in range(n):
            try:
                pc = generate_one(
                    course_id, course_title, qtype, kcs, seq,
                    llm_call=llm_call,
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("生成 %s 题型失败 seq=%d: %s", qtype, seq, e)
                # 兜底:造一条基础题,不阻塞后续
                pc = PilotCase(
                    eval_case=EvalCase(
                        case_id=_normalize_case_id("", course_id, qtype, seq),
                        course_id=course_id,
                        question=f"(生成失败占位) {qtype} 题 #{seq}",
                        question_type=qtype,  # type: ignore[arg-type]
                        gold_answer=("这个问题超出了" + course_title + "的范围。"),
                        gold_citations=[],
                        answerability=(qtype != "refusal"),
                    ),
                )
            cases.append(pc)
            seq += 1

    return PilotSuite(
        course_id=course_id,
        cases=cases,
        generator_model=settings.deepseek_model,
    )
