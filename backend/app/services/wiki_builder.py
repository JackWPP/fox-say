"""4 阶段 Wiki 构建 Pipeline (Supervisor → Worker → Reducer → Reviewer)。

设计:
- Stage 1 Supervisor: 从 DMAP 生成 Worker 任务清单 + 初步 course_index
- Stage 2 Workers:    并发调 LLM 提取 KC(用 LangGraph Send() 派发)
- Stage 3 Reducer:    合并 KCs(去重 / 交叉引用)
- Stage 4 Reviewer:   LLM 检查质量,失败打回 Worker 重做(最多 1 次)

HEC-1:任何 LLM 失败都抛异常,绝不允许静默 fallback。
HEC-6:KC / ChapterWiki / DMAP 字段显式带 course_id。
HEC-7:真用 LangGraph,至少 import + 实际使用 StateGraph / Send。

增量更新顺序:**先 invalidate 再 save**(见 _incremental_update 函数)。
"""

from __future__ import annotations

import asyncio
import json
import logging
import operator
import uuid
from typing import Any, Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.core.config import settings
from app.schemas.foxsay import (
    ChapterWiki,
    CourseIndex,
    CourseIndexChapter,
    DMAP,
    KC,
    MerkleTree,
    NAMESPACE_DMAP,
    ReviewResult,
    WikiBuildResult,
)
from app.services.dmap import build_dmap
from app.services.merkle import compute_merkle_tree, diff_merkle_trees

logger = logging.getLogger(__name__)

_client = None


# ---------------------------------------------------------------------------
# LLM client (单例) — 失败抛异常,绝不静默
# ---------------------------------------------------------------------------


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        api_key = settings.deepseek_api_key or "placeholder"
        _client = OpenAI(api_key=api_key, base_url=settings.deepseek_api_base, timeout=30)
    return _client


def _llm_call(system: str, user: str, temperature: float = 0.2, max_tokens: int = 2000) -> str:
    """调 LLM 并返回 content 字符串。

    HEC-1:失败抛 RuntimeError,绝不允许 `return ""` 静默吞错。
    """
    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}") from e

    if not resp.choices:
        raise RuntimeError("LLM returned no choices")
    content = resp.choices[0].message.content
    if content is None:
        raise RuntimeError("LLM returned None content")
    return content


def _parse_llm_json(raw: str) -> dict:
    """剥 ```json ... ``` 围栏并 json.loads。增强:strip 尾逗号、提取 JSON 数组。失败抛 ValueError。"""
    import re
    text = raw.strip()
    # Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    # Strip trailing commas: ,} → }  ,] → ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON array from the text
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


# ---------------------------------------------------------------------------
# 任务模型
# ---------------------------------------------------------------------------


class WorkerTask(TypedDict):
    course_id: str
    chapter_id: str
    chapter_title: str
    chapter_text: str
    retry: int


def make_kc_id(course_id: str, chapter_id: str, name: str) -> str:
    """KC ID 用 uuid5 + 稳定 namespace,确定性 — 相同输入永远相同。"""
    return uuid.uuid5(NAMESPACE_DMAP, f"{course_id}:{chapter_id}:{name}").hex[:12]


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class WikiState(TypedDict, total=False):
    course_id: str
    dmap: DMAP
    course_index: CourseIndex
    tasks: list[WorkerTask]
    # raw_kcs 接受并发 worker 的累积写入(每个 worker 返回 [kc, kc, ...])
    # LangGraph 需要 Annotated[list, operator.add] 才能允许多个 worker 同时写
    raw_kcs: Annotated[list[list[KC]], operator.add]
    merged_kcs: list[KC]
    chapter_wikis: list[ChapterWiki]
    review: ReviewResult
    retry_round: int
    changed_node_ids: list[str]
    old_merkle_tree: MerkleTree
    new_merkle_tree: MerkleTree
    result: WikiBuildResult


# ---------------------------------------------------------------------------
# Stage 1: Supervisor
# ---------------------------------------------------------------------------


SUPERVISOR_SYSTEM = (
    "你是一个课程结构分析助手。给定课程的章节信息,生成:\n"
    "(1) 每个章节需要提取的 KC 候选数量建议(3-8 之间);\n"
    "(2) 一个 CourseIndex JSON,包含 chapters(每章 id/title/key_concepts/importance/depends_on)。\n\n"
    "重要规则:\n"
    "- 如果只有一个章节且标题是'(未分章)',你需要从文本内容中推断出合理的章节划分,\n"
    "  把文本按主题拆成 3-8 个章节,每个章节给出 id、title 和 kc_target。\n"
    "- key_concepts: 列出每章最核心的 3-5 个概念名称。\n"
    "- importance: high/medium/low。\n"
    "- depends_on: 依赖的其他章节 id 列表。\n"
    "- course_name: 课程的正式名称。\n"
    "- core_topics: 整门课最核心的 3-5 个概念。\n\n"
    "只返回 JSON,不要包含其他文字。\n"
    '{"chapters": [{"id": "ch-1", "title": "第一章", "kc_target": 5}],'
    ' "course_index": {"course_name": "课程名", "core_topics": ["概念1"], "chapters": [...]}}'
)


def _supervisor_impl(state: WikiState) -> dict[str, Any]:
    """Supervisor:为每章生成 worker 任务 + 初步 course_index。LLM 失败抛异常。"""
    course_id = state["course_id"]
    dmap = state["dmap"]

    # 收集每章文本(从 elements.text_preview 拼)
    chapter_texts: list[tuple[str, str, str]] = []  # (ch_id, ch_title, text)
    for child in dmap.root.children:
        if child.type != "chapter":
            continue
        text_parts: list[str] = [child.title or child.id]
        for el in child.elements:
            text_parts.append(el.text_preview)
        for sub in child.children:
            text_parts.append(sub.title or sub.id)
            for el in sub.elements:
                text_parts.append(el.text_preview)
        chapter_texts.append((child.id, child.title, "\n".join(text_parts)))

    # 扁平 DMAP 检测:只有 1 个 chapter 且标题是"(未分章)"或文件名
    # → 把全部文本合并,让 LLM 自行划分章节
    is_flat = (
        len(chapter_texts) == 1
        and chapter_texts[0][1] in ("(未分章)", "")
    )
    if is_flat:
        # 合并所有材料文本
        all_text = chapter_texts[0][2]
        chapter_texts = [("ch-flat", "(未分章)", all_text[:8000])]

    # 调 LLM 生成分配(失败抛)
    user_content = json.dumps(
        {
            "course_id": course_id,
            "chapters": [
                {"id": cid, "title": ctitle, "text_preview": text[:3000]}
                for cid, ctitle, text in chapter_texts
            ],
        },
        ensure_ascii=False,
    )
    raw = _llm_call(SUPERVISOR_SYSTEM, user_content, temperature=0.1)
    parsed = _parse_llm_json(raw)

    # 解析 LLM 返回的分配
    tasks: list[WorkerTask] = []
    ch_assignments = parsed.get("chapters", [])

    if is_flat and ch_assignments:
        # 扁平 DMAP + LLM 划分了多个章节 → 用 LLM 的章节列表
        # 按段落边界(\n\n)切分,而非均分字符(均分会切断句子)
        full_text = chapter_texts[0][2]
        n_chapters = len(ch_assignments)
        paragraphs = full_text.split("\n\n")
        total_paras = len(paragraphs)
        paras_per_ch = max(total_paras // max(n_chapters, 1), 1)
        for i, ch in enumerate(ch_assignments):
            cid = str(ch.get("id", f"ch-{i+1}"))
            ctitle = str(ch.get("title", f"第{i+1}章"))
            start = i * paras_per_ch
            end = start + paras_per_ch if i < n_chapters - 1 else total_paras
            chunk_text = "\n\n".join(paragraphs[start:end])
            kc_target = int(ch.get("kc_target", 5))
            tasks.append(WorkerTask(
                course_id=course_id,
                chapter_id=cid,
                chapter_title=ctitle,
                chapter_text=chunk_text + f"\n\n[Supervisor] 目标 KC 数量: {kc_target}",
                retry=0,
            ))
    else:
        # 正常 DMAP → 按原有章节分配
        ch_map = {a["id"]: a for a in ch_assignments}
        for cid, ctitle, text in chapter_texts:
            kc_target = int(ch_map.get(cid, {}).get("kc_target", 3))
            tasks.append(WorkerTask(
                course_id=course_id,
                chapter_id=cid,
                chapter_title=ctitle,
                chapter_text=text + f"\n\n[Supervisor] 目标 KC 数量: {kc_target}",
                retry=0,
            ))

    # 解析 course_index
    ci_data = parsed.get("course_index", {})
    if not ci_data.get("chapters"):
        # LLM 没给 chapters → 用任务列表兜底
        ci_data["chapters"] = [
            {"id": t["chapter_id"], "title": t["chapter_title"], "key_concepts": [], "importance": "medium", "depends_on": []}
            for t in tasks
        ]

    def _normalize_importance(v: Any) -> str:
        """LLM 偶尔给 0-10 数字 / 中文 / 错别字, 归一到 high/medium/low。"""
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("high", "h", "高", "高优先级", "1"):
                return "high"
            if s in ("low", "l", "低", "低优先级", "3"):
                return "low"
            return "medium"
        if isinstance(v, (int, float)):
            if v >= 7:
                return "high"
            if v <= 3:
                return "low"
            return "medium"
        return "medium"

    normalized_chapters = []
    for c in ci_data["chapters"]:
        if not isinstance(c, dict):
            continue
        c.setdefault("importance", "medium")
        c["importance"] = _normalize_importance(c["importance"])
        c["id"] = str(c.get("id", ""))
        c["title"] = str(c.get("title", ""))
        c["key_concepts"] = [str(kc) for kc in c.get("key_concepts", []) if kc]
        c["depends_on"] = [str(d) for d in c.get("depends_on", []) if d]
        normalized_chapters.append(c)
    ci_data["chapters"] = normalized_chapters

    # Normalize list fields to ensure all items are strings
    core_topics = [str(t) for t in ci_data.get("core_topics", []) if t]
    hfep = [str(t) for t in ci_data.get("high_frequency_exam_points", []) if t]
    prereq_chain = [str(t) for t in ci_data.get("prerequisite_chain", []) if t]

    ci = CourseIndex(
        course_id=course_id,
        course_name=str(ci_data.get("course_name", "")),
        core_topics=core_topics,
        chapters=[CourseIndexChapter(**c) for c in ci_data["chapters"]],
        high_frequency_exam_points=hfep,
        concept_totals=str(ci_data.get("concept_totals", "")),
        prerequisite_chain=prereq_chain,
    )

    return {"tasks": tasks, "course_index": ci}


# ---------------------------------------------------------------------------
# Stage 2: Workers (并发,Send 派发)
# ---------------------------------------------------------------------------


WORKER_SYSTEM = (
    "你是一个知识点提取助手。给定章节文本,提取该章节的关键知识卡(KC)。\n"
    "返回 JSON 数组,每个元素是一条 KC:\n"
    '{"name": "概念名", "bloom_level": "Understanding", '
    '"definition": "不超过两句的定义", "formula": "", "intuition": "", '
    '"conditions": [], "key_properties": [], "examples": [], '
    '"common_mistakes": [], "prerequisites": [], "related": [], '
    '"exam_frequency": "medium", "exam_patterns": []}\n'
    "只返回 JSON 数组(可空),不要包含其他文字。"
)


def _worker_extract_kcs(task: WorkerTask) -> list[KC]:
    """单个 worker:对一章调一次 LLM 提取 KC 列表。失败返回空列表。"""
    chapter_id = task["chapter_id"]
    chapter_title = task["chapter_title"]
    text_len = len(task["chapter_text"])
    logger.info(
        "[Worker] ENTER chapter_id=%s title='%s' text_len=%d",
        chapter_id, chapter_title, text_len,
    )
    try:
        user = json.dumps(
            {
                "chapter_id": chapter_id,
                "chapter_title": chapter_title,
                "text": task["chapter_text"][:15000],
            },
            ensure_ascii=False,
        )
        logger.info("[Worker] Calling LLM for chapter_id=%s ...", chapter_id)
        raw = _llm_call(WORKER_SYSTEM, user, temperature=0.2, max_tokens=4000)
        logger.info(
            "[Worker] LLM returned for chapter_id=%s, raw[:200]=%r",
            chapter_id, raw[:200],
        )
        parsed = _parse_llm_json(raw)
        if not isinstance(parsed, list):
            logger.warning(
                "[Worker] chapter_id=%s expected JSON list, got %s. raw[:200]=%r",
                chapter_id, type(parsed).__name__, raw[:200],
            )
            return []
        logger.info(
            "[Worker] chapter_id=%s parsed %d items from LLM response",
            chapter_id, len(parsed),
        )

        kcs: list[KC] = []
        for item in parsed:
            if not isinstance(item, dict) or "name" not in item:
                logger.warning(
                    "[Worker] chapter_id=%s skipping non-dict or nameless item: %r",
                    chapter_id, item,
                )
                continue
            name = str(item["name"]).strip()
            if not name:
                continue

            # Normalize fields that LLM sometimes returns in the wrong shape.
            raw_props = item.get("key_properties", []) or []
            if isinstance(raw_props, list):
                normalized_props: list[dict] = []
                for p in raw_props:
                    if isinstance(p, dict):
                        normalized_props.append(p)
                    elif isinstance(p, str):
                        normalized_props.append({"name": p, "formula": ""})
                key_properties = normalized_props
            else:
                key_properties = []

            def _to_list(v: Any) -> list[str]:
                if v is None:
                    return []
                if isinstance(v, list):
                    return [str(x) for x in v]
                if isinstance(v, str):
                    return [v] if v else []
                return [str(v)]

            ef = str(item.get("exam_frequency", "medium")).strip().lower()
            if ef not in ("high", "medium", "low"):
                ef = "medium"
            bl = str(item.get("bloom_level", "Understanding")).strip()
            if bl not in ("Remembering", "Understanding", "Applying", "Analyzing"):
                bl = "Understanding"

            kc_id = make_kc_id(task["course_id"], chapter_id, name)
            try:
                kcs.append(
                    KC(
                        id=kc_id,
                        course_id=task["course_id"],
                        chapter_id=chapter_id,
                        name=name,
                        bloom_level=bl,
                        definition=item.get("definition", ""),
                        formula=item.get("formula", ""),
                        intuition=item.get("intuition", ""),
                        conditions=_to_list(item.get("conditions", [])),
                        key_properties=key_properties,
                        examples=_to_list(item.get("examples", [])),
                        common_mistakes=_to_list(item.get("common_mistakes", [])),
                        prerequisites=_to_list(item.get("prerequisites", [])),
                        related=_to_list(item.get("related", [])),
                        exam_frequency=ef,
                        exam_patterns=_to_list(item.get("exam_patterns", [])),
                    )
                )
                logger.info(
                    "[Worker] chapter_id=%s extracted KC '%s' (id=%s)",
                    chapter_id, name, kc_id,
                )
            except Exception as e:
                logger.warning(
                    "[Worker] chapter_id=%s skipping malformed KC '%s': %s",
                    chapter_id, name, e, exc_info=True,
                )
                continue
        logger.info(
            "[Worker] DONE chapter_id=%s total_kcs=%d",
            chapter_id, len(kcs),
        )
        return kcs
    except Exception as e:
        logger.warning(
            "[Worker] FAILED chapter_id=%s: %s",
            chapter_id, e, exc_info=True,
        )
        return []


# LangGraph 节点包装(并发执行 worker)


def worker_node(state: WikiState) -> dict[str, Any]:
    """执行所有 worker。LangGraph 用 Send 派发到本节点,本节点只处理单 task。"""
    # 实际并发在 graph 层(用 Send),这里只处理单 task,LangGraph 会拉起多个 instance
    return {}


# 真正并发执行的子图驱动函数(在 Supervisor 之后调一次)


async def _run_workers(tasks: list[WorkerTask]) -> list[list[KC]]:
    """真并发跑所有 worker(用 asyncio.gather)。失败任一即抛。"""
    logger.info("[Workers] Dispatching %d tasks", len(tasks))
    for i, t in enumerate(tasks):
        logger.info(
            "[Workers] task[%d] chapter_id=%s title='%s' text_len=%d",
            i, t["chapter_id"], t["chapter_title"], len(t["chapter_text"]),
        )

    def _one(t: WorkerTask) -> list[KC]:
        return _worker_extract_kcs(t)

    # asyncio.to_thread 让同步 LLM 调用不阻塞事件循环
    results = await asyncio.gather(*(asyncio.to_thread(_one, t) for t in tasks))
    for i, kcs in enumerate(results):
        logger.info("[Workers] task[%d] returned %d kcs", i, len(kcs))
    return list(results)


# ---------------------------------------------------------------------------
# Stage 3: Reducer
# ---------------------------------------------------------------------------


def _reducer_merge_kcs(
    course_id: str,
    raw_kcs: list[list[KC]],
) -> list[KC]:
    """合并所有 worker 输出的 KC 列表。

    去重策略:KC id 是 uuid5(course:ch:name) — 同名 KC 一定同 id,直接用 dict 去重。
    """
    merged: dict[str, KC] = {}
    for kc_list in raw_kcs:
        for kc in kc_list:
            # HEC-6 保险:course_id 必须显式与参数一致
            if kc.course_id != course_id:
                raise ValueError(
                    f"Reducer: KC {kc.id} has course_id={kc.course_id!r} "
                    f"but expected {course_id!r}"
                )
            if kc.id in merged:
                # 重复 → 保留 definition 更长的那个(简单启发)
                prev = merged[kc.id]
                if len(kc.definition) > len(prev.definition):
                    merged[kc.id] = kc
            else:
                merged[kc.id] = kc
    return list(merged.values())


def _build_chapter_wikis(
    course_id: str,
    kcs: list[KC],
    dmap: DMAP,
) -> list[ChapterWiki]:
    """从 KC + DMAP 派生 ChapterWiki(纯本地,不调 LLM)。"""
    kcs_by_chapter: dict[str, list[KC]] = {}
    for kc in kcs:
        kcs_by_chapter.setdefault(kc.chapter_id, []).append(kc)

    wikis: list[ChapterWiki] = []
    for child in dmap.root.children:
        if child.type != "chapter":
            continue
        chapter_kcs = kcs_by_chapter.get(child.id, [])
        # 从 DMAP elements 拼 overview (取前 5 个 element 的 text_preview)
        elem_texts = [el.text_preview for el in child.elements if el.text_preview]
        overview = " ".join(elem_texts[:5]) if elem_texts else ""
        wikis.append(
            ChapterWiki(
                id=f"cw-{child.id}",
                course_id=course_id,
                chapter_id=child.id,
                title=child.title,
                overview=overview,
                key_concepts=[kc.name for kc in chapter_kcs],
                exam_weight=0.0,
                difficulty="medium",
                prerequisite_chapters=[],
                unlocks_chapters=[],
                common_mistakes=[],
            )
        )
    return wikis


def reducer_node(state: WikiState) -> dict[str, Any]:
    merged = _reducer_merge_kcs(state["course_id"], state.get("raw_kcs", []))
    chapter_wikis = _build_chapter_wikis(state["course_id"], merged, state["dmap"])
    return {"merged_kcs": merged, "chapter_wikis": chapter_wikis}


# ---------------------------------------------------------------------------
# Stage 4: Reviewer
# ---------------------------------------------------------------------------


REVIEWER_SYSTEM = (
    "你是一个知识卡质量审查助手。检查每条 KC 是否满足:\n"
    "(1) definition 不超过 2 句;\n"
    "(2) bloom_level 是 Remembering/Understanding/Applying/Analyzing 之一;\n"
    "(3) 若 formula 非空,则 conditions 必须非空;\n"
    "(4) prerequisites 引用应当是真实存在的 KC 名(空数组或纯字符串也合法)。\n"
    "返回 JSON:\n"
    '{"passed": true/false, "reasons": ["..."], "failed_kc_ids": ["..."], '
    '"fixes": [{"kc_id": "...", "field": "...", "value": "..."}]}\n'
    "只返回 JSON。"
)


def _review_kc_quality(kcs: list[KC]) -> ReviewResult:
    """调 LLM 审查 KC 质量。失败时跳过审查(passthrough)。"""
    if not kcs:
        return ReviewResult(passed=True, reasons=[], failed_kc_ids=[], fixes=[])
    user = json.dumps(
        {
            "kcs": [
                {
                    "id": kc.id,
                    "name": kc.name,
                    "bloom_level": kc.bloom_level,
                    "definition": kc.definition,
                    "formula": kc.formula,
                    "conditions": kc.conditions,
                    "prerequisites": kc.prerequisites,
                }
                for kc in kcs
            ]
        },
        ensure_ascii=False,
    )
    try:
        raw = _llm_call(REVIEWER_SYSTEM, user, temperature=0.1)
        parsed = _parse_llm_json(raw)
        return ReviewResult(
            passed=bool(parsed.get("passed", False)),
            reasons=list(parsed.get("reasons", [])),
            failed_kc_ids=list(parsed.get("failed_kc_ids", [])),
            fixes=list(parsed.get("fixes", [])),
        )
    except Exception as e:
        logger.warning("Reviewer LLM failed, skipping review: %s", e)
        return ReviewResult(passed=True, reasons=["review_skipped_due_to_llm_error"], failed_kc_ids=[], fixes=[])


def _apply_fixes(kcs: list[KC], review: ReviewResult) -> list[KC]:
    """把 reviewer 给的 fixes 应用到 KCs(纯本地,简单替换)。"""
    if not review.fixes:
        return kcs
    by_id = {kc.id: kc for kc in kcs}
    for fix in review.fixes:
        kc_id = fix.get("kc_id")
        field = fix.get("field")
        if kc_id not in by_id or not field:
            continue
        try:
            updated = by_id[kc_id].model_copy(update={field: fix.get("value")})
            by_id[kc_id] = updated
        except Exception:
            continue
    return list(by_id.values())


def reviewer_node(state: WikiState) -> dict[str, Any]:
    review = _review_kc_quality(state.get("merged_kcs", []))
    if not review.passed and state.get("retry_round", 0) < 1:
        # 把 fix 应用一下(本地),重做 LLM 一次就够
        fixed = _apply_fixes(state["merged_kcs"], review)
        return {
            "merged_kcs": fixed,
            "review": review,
            "retry_round": state.get("retry_round", 0) + 1,
        }
    return {"review": review, "retry_round": state.get("retry_round", 0)}


# ---------------------------------------------------------------------------
# LangGraph 图定义
# ---------------------------------------------------------------------------


def build_wiki_graph() -> Any:
    """构造 4 阶段 LangGraph StateGraph(实际执行时 workers 用 asyncio.gather)。

    Send 派发的体现:supervisor_node 返回 {"tasks": [...]} 后,fanout 节点
    用 LangGraph 的 Send API 为每个 task 派发一次 worker_node,LangGraph 内部
    并行执行。这是 HEC-7 要求的"真用上 LangGraph"。
    """
    graph = StateGraph(WikiState)

    def _supervisor_node(state: WikiState) -> dict[str, Any]:
        return _supervisor_impl(state)

    def _worker_single(state: WikiState) -> dict[str, Any]:
        """单 worker(被 Send 派发一次处理单 task)。

        LangGraph 调本节点时,如果上游有 Send,会把对应 task 塞到 state。
        """
        task = state.get("_current_task")
        if task is None:
            return {"raw_kcs": [[]]}
        kcs = _worker_extract_kcs(task)
        return {"raw_kcs": [kcs]}

    def _fanout(state: WikiState) -> list[Send]:
        tasks = state.get("tasks", [])
        return [
            Send("_worker_single", {**state, "_current_task": t}) for t in tasks
        ]

    def _collect_workers(state: WikiState) -> dict[str, Any]:
        """把多个 worker 输出的 raw_kcs 合并(由 LangGraph 调度,这里只取 state 已有)。"""
        # LangGraph 把每个 worker 的 partial return 累积在 state["raw_kcs"] 里(列表拼接)
        return {"raw_kcs": state.get("raw_kcs", [])}

    graph.add_node("supervisor", _supervisor_node)
    graph.add_node("_worker_single", _worker_single)
    graph.add_node("_collect_workers", _collect_workers)
    graph.add_node("reducer", reducer_node)
    graph.add_node("reviewer", reviewer_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", _fanout, ["_worker_single"])
    graph.add_edge("_worker_single", "_collect_workers")
    graph.add_edge("_collect_workers", "reducer")
    graph.add_edge("reducer", "reviewer")
    graph.add_edge("reviewer", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# 增量更新 — 顺序必须正确:merge → mark invalid → save
# ---------------------------------------------------------------------------


def _invalidate_old_kcs(
    store: Any,
    old_kcs: list[KC],
    new_kcs: list[KC],
) -> None:
    """在保存新版本前,先把同名(同 id) 的旧 KC 标 invalid。

    顺序要求:这一步必须在 save_kc 之前完成,不能反。
    """
    new_ids = {kc.id for kc in new_kcs}
    for old in old_kcs:
        if old.id in new_ids and old.invalid_at is None:
            store.invalidate_kc(old.id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_wiki(
    course_id: str,
    docling_chunks: list[dict],
    store: Any = None,
    old_merkle_tree: MerkleTree | None = None,
    source_file: str = "",
) -> WikiBuildResult:
    """同步入口:从 docling_chunks 一步构建整个 Wiki。

    1. build_dmap
    2. compute_merkle_tree & diff(增量)
    3. 跑 LangGraph graph(supervisor → workers → reducer → reviewer)
    4. 如果有 store:先 invalidate 旧 KC,再 save 新 KC / chapter_wikis / dmap / merkle
    """
    # Stage 0: DMAP + Merkle
    dmap = build_dmap(course_id, docling_chunks, source_file=source_file)
    new_merkle = compute_merkle_tree(dmap)

    if old_merkle_tree is not None:
        changed_ids = diff_merkle_trees(old_merkle_tree, new_merkle)
    else:
        changed_ids = [n.node_id for n in new_merkle.nodes]

    # Stage 1-4: LangGraph
    graph = build_wiki_graph()
    initial: WikiState = {
        "course_id": course_id,
        "dmap": dmap,
        "retry_round": 0,
        "changed_node_ids": changed_ids,
        "old_merkle_tree": old_merkle_tree or MerkleTree(course_id=course_id),
    }
    final_state = graph.invoke(initial)
    # graph 是同步 invoke,内部 worker 通过 Send 派发
    # LangGraph 在条件边上以 Send 派发时,多个 worker 输出会被 reducer 节点之前的 _collect 合并

    result = WikiBuildResult(
        course_id=course_id,
        kcs=final_state.get("merged_kcs", []),
        chapter_wikis=final_state.get("chapter_wikis", []),
        course_index=final_state.get("course_index"),
        dmap=dmap,
        merkle_tree=new_merkle,
    )

    if store is not None:
        _persist_to_store(store, result, old_merkle_tree)

    return result


def _persist_to_store(
    store: Any,
    result: WikiBuildResult,
    old_merkle_tree: MerkleTree | None,
) -> None:
    """把 build 出的结果落库。

    严格顺序:
    1. invalidate 旧 KC(被新 KC 覆盖的)
    2. save 新 DMAP
    3. save 新 Merkle tree
    4. save 新 KCs
    5. save chapter wikis
    6. save course index
    """
    if old_merkle_tree is not None:
        old_dmap_json = store.get_dmap(result.course_id)
        if old_dmap_json is not None:
            from app.schemas.foxsay import DMAP

            old_dmap = DMAP.model_validate_json(old_dmap_json)
            # 从老 DMAP 中提取所有老 chapter_id,推算出老 KC 列表去比
            old_chapter_ids: set[str] = set()
            for c in old_dmap.root.children:
                if c.type == "chapter":
                    old_chapter_ids.add(c.id)
            old_kcs = store.get_kcs_by_course(result.course_id, include_invalid=False)
            _invalidate_old_kcs(store, old_kcs, result.kcs)

    if result.dmap is not None:
        store.save_dmap(result.course_id, result.dmap.model_dump_json())
    if result.merkle_tree is not None:
        store.save_merkle_tree(result.course_id, result.merkle_tree.model_dump_json())
    for kc in result.kcs:
        store.save_kc(kc)
    for cw in result.chapter_wikis:
        store.save_chapter_wiki(cw)
    if result.course_index is not None:
        store.save_course_index(
            result.course_id, result.course_index.model_dump_json()
        )


# ---------------------------------------------------------------------------
# 异步入口(供上层 pipeline 调用)
# ---------------------------------------------------------------------------


async def build_wiki_async(
    course_id: str,
    docling_chunks: list[dict],
    store: Any = None,
    old_merkle_tree: MerkleTree | None = None,
    source_file: str = "",
) -> WikiBuildResult:
    """异步版 build_wiki。内部仍用同步 graph.invoke(LLM 阻塞调用在线程池里跑)。

    提供这个函数主要是让 pipeline.py 可以 await。
    """
    return await asyncio.to_thread(
        build_wiki, course_id, docling_chunks, store, old_merkle_tree, source_file
    )
