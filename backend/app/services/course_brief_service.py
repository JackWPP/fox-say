"""V2-F7 CourseBriefService: revision-bound course brief generation."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.sqlite_store import SqliteStore
from app.schemas.agent_runs import AgentRun, AgentStep
from app.schemas.artifacts import CourseBriefResult
from app.services.audited_chat_writer import AuditedChatWriter
from app.services.audited_text_model import AuditedModelCallError, AuditedTextResult
from app.services.knowledge_status import build_knowledge_status
from app.services.v2_agent_tools import V2AgentTools

_NO_SOURCE_REVISION = "__no_source__"
_NO_KNOWLEDGE_REVISION = "__no_knowledge__"

MAX_BRIEF_KCS = 30
MAX_BRIEF_SECTIONS = 20
MAX_BRIEF_EVIDENCE_REFS = 40
MAX_BRIEF_REFS_PER_SECTION = 5
MAX_OUTPUT_TOKENS = 2048

# System prompt from architecture doc section 3.1
COURSE_BRIEF_SYSTEM_PROMPT = """你是 FoxSay 学习助手的"课程编撰师"——一只擅长从课程材料中提炼出清晰学习地图的狐狸。

你会收到：
1. 课程的章节大纲（章节标题和顺序）
2. 课程的核心知识点列表（名称和简短定义）
3. 知识点之间的关系数量（不列出具体关系）
4. 课程的碎片总数

你的任务：
生成一份简洁的"课程简报"，帮助学生在深入学习之前快速了解这门课的全局结构。

简报必须包含：
1. **overview**：2-5句话概述课程整体内容。说明这门课要讲什么、为什么要学它。
2. **key_topics**：3-8个核心主题。每个主题包含：
   - topic：主题名称
   - description：1-3句话说明该主题的内容
   - kcs_involved：从提供的知识点列表中选出属于该主题的 KC ID 列表
   - evidence_refs：从提供的证据引用列表中选择与该主题相关的引用
3. **study_suggestions**：2-5条学习建议。说明推荐的章节学习顺序、重点注意哪些内容、容易混淆的概念等。
4. **difficulty_areas**：0-3个需要注意的难点区域。如果课程相对简单或均匀，此列表可以为空。

规则：
1. 只能引用提供的章节标题、知识点名称和证据引用。不得编造课程中不存在的内容。
2. 学习建议必须基于课程的实际结构，不要给出泛泛的"多做习题"类通用建议。
3. 难点区域的判断基于知识点之间的先修关系深度和概念复杂度，而不是假装知道学生会觉得什么难。
4. 保持狐狸的个性：聪明、有条理，像一位对课程了如指掌的学伴。
5. 所有 evidence_refs 只能从提供的可引用证据列表中选择。每个 key_topic 必须至少附带一个 evidence_ref。

请以 JSON 格式返回：
{
  "overview": "课程概述文本",
  "key_topics": [
    {
      "topic": "主题名",
      "description": "主题描述",
      "kcs_involved": ["kc_id1", "kc_id2"],
      "evidence_refs": [{"material_id": "...", "fragment_id": "...", "heading_path": "..."}]
    }
  ],
  "study_suggestions": [
    {"suggestion": "建议文本", "rationale": "理由"}
  ],
  "difficulty_areas": [
    {"area": "难点名称", "description": "描述", "prerequisite_kcs": ["kc_id1"]}
  ],
  "metadata": {
    "sections_count": 0,
    "kcs_count": 0,
    "relations_count": 0,
    "fragment_count": 0
  }
}

- metadata 中的数值请从提供的数字中直接填入，不要猜测。
- study_suggestions 和 difficulty_areas 如果为空，返回空列表 []。"""


def _build_course_brief_user_message(
    outline: Any,
    kcs: list[dict],
    relations_count: int,
    evidence_map: dict[str, list[dict]],
    fragment_count: int,
) -> str:
    parts = [f"课程大纲（共{len(outline.sections)}节）："]
    for sec in outline.sections[:MAX_BRIEF_SECTIONS]:
        parts.append(
            f"  [{sec.section_id}] {sec.title}"
            f"（第{sec.ordinal + 1}节, {len(evidence_map.get(sec.section_id, []))}个碎片）"
        )

    parts.append(f"\n核心知识点（共{len(kcs)}个）：")
    for kc in kcs[:MAX_BRIEF_KCS]:
        parts.append(f"  [{kc['kc_id']}] {kc['name']}（{kc['kind']}）：{kc['definition'][:120]}")

    parts.append(f"\n知识点关系数量：{relations_count}")

    parts.append("\n可引用的证据引用（按章节组织）：")
    total_refs = 0
    for sec in outline.sections[:MAX_BRIEF_SECTIONS]:
        refs = evidence_map.get(sec.section_id, [])[:MAX_BRIEF_REFS_PER_SECTION]
        if refs:
            parts.append(f"  [{sec.section_id}] {sec.title}：")
            for ref in refs:
                heading = " > ".join(ref["heading_path"]) if ref.get("heading_path") else ""
                parts.append(f"    · fragment_id={ref['fragment_id']} heading_path={heading}")
                total_refs += 1
                if total_refs >= MAX_BRIEF_EVIDENCE_REFS:
                    break
        if total_refs >= MAX_BRIEF_EVIDENCE_REFS:
            break

    parts.append(f"\n碎片总数：{fragment_count}")
    parts.append('\n请以 JSON 格式返回课程简报。')
    return "\n".join(parts)


def _parse_brief_json(content: str) -> dict:
    """Extract JSON from model response, with substring fallback."""
    text = content.strip()
    if text.startswith("{"):
        return json.loads(text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("No JSON object found in model response")


class CourseBriefService:
    """Revision-bound course brief generation from V2 knowledge projection."""

    def __init__(
        self,
        store: SqliteStore,
        writer: AuditedChatWriter,
        tools: V2AgentTools,
        *,
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        temperature: float | None = 0.3,
        default_token_budget: int = 12000,
    ) -> None:
        self._store = store
        self._writer = writer
        self._tools = tools
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._default_token_budget = default_token_budget

    async def generate(
        self,
        *,
        course_id: str,
        session_id: str,
        turn_id: str,
        force: bool = False,
    ) -> CourseBriefResult:
        status = build_knowledge_status(self._store, course_id)
        source_rev = status.source_revision or _NO_SOURCE_REVISION
        knowledge_rev = status.knowledge_revision or _NO_KNOWLEDGE_REVISION

        if status.projection_status != "ready" or not status.source_revision:
            return CourseBriefResult(
                course_id=course_id, status="not_found",
                error_code="projection_not_ready",
                error_detail="Course projection is not ready; outline and KCs required",
            )

        if not force:
            existing = self._store.get_active_course_brief(course_id)
            if existing is not None:
                return _row_to_brief_result(existing, source_rev, knowledge_rev)

        outline = self._tools.get_current_outline(course_id)
        kcs_raw = self._tools.get_current_knowledge_components(course_id)
        relations = self._tools.get_current_kc_relations(course_id)

        if outline is None or not kcs_raw:
            return CourseBriefResult(
                course_id=course_id, status="not_found",
                error_code="no_knowledge_components",
                error_detail="No outline or knowledge components available",
            )

        kcs = [{"kc_id": kc.kc_id, "name": kc.name, "kind": kc.kind,
                 "definition": kc.definition} for kc in kcs_raw]

        evidence_map: dict[str, list[dict]] = {}
        allowed_fragment_ids: set[str] = set()
        for sec in outline.sections:
            sec_refs: list[dict] = []
            for kc in kcs_raw:
                if hasattr(kc, 'section_id') and kc.section_id == sec.section_id:
                    for ev in (kc.evidence if hasattr(kc, 'evidence') else []):
                        if hasattr(ev, 'fragment_id'):
                            ref = {
                                "material_id": ev.material_id if hasattr(ev, 'material_id') else "",
                                "fragment_id": ev.fragment_id,
                                "heading_path": ev.heading_path if hasattr(ev, 'heading_path') else [],
                            }
                            sec_refs.append(ref)
                            allowed_fragment_ids.add(ev.fragment_id)
            evidence_map[sec.section_id] = sec_refs

        run_id = f"ar_{uuid.uuid4().hex[:16]}"
        step_reader_id = f"as_{uuid.uuid4().hex[:16]}"
        step_composer_id = f"as_{uuid.uuid4().hex[:16]}"
        brief_id = f"cb_{uuid.uuid4().hex[:16]}"

        run = AgentRun(
            run_id=run_id,
            turn_id=turn_id,
            course_id=course_id,
            session_id=session_id,
            workflow_kind="course_brief",
            source_revision=source_rev,
            knowledge_revision=knowledge_rev,
            status="accepted",
            token_budget=self._default_token_budget,
        )
        self._store.create_agent_run(run)

        reader_step = AgentStep(
            step_id=step_reader_id, run_id=run_id,
            agent_role="reader", step_type="read_tools",
            status="completed", output_type="bounded_knowledge",
        )
        self._store.create_agent_step(reader_step)

        user_message = _build_course_brief_user_message(
            outline, kcs, len(relations), evidence_map,
            fragment_count=sum(len(v) for v in evidence_map.values()),
        )
        messages = [
            {"role": "system", "content": COURSE_BRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        composer_step = AgentStep(
            step_id=step_composer_id, run_id=run_id,
            agent_role="composer", step_type="generate",
            status="running", output_type="course_brief",
        )
        self._store.create_agent_step(composer_step)
        self._store.update_agent_run_status(course_id, run_id, "composing")

        started = time.monotonic()
        try:
            result: AuditedTextResult = await self._writer.complete(
                run, purpose="course_brief", messages=messages,
                max_output_tokens=self._max_output_tokens,
                temperature=self._temperature,
                budget_scope="artifact",
            )
            elapsed = int((time.monotonic() - started) * 1000)
        except AuditedModelCallError as exc:
            self._store.update_agent_step(step_composer_id, "failed", error=str(exc))
            self._store.update_agent_run_status(
                course_id, run_id, "failed",
                error_code="generation_failed", error_detail=str(exc),
            )
            self._store.insert_course_brief(
                brief_id, course_id, source_rev, knowledge_rev, "{}",
                agent_run_id=run_id,
            )
            self._store.fail_course_brief(brief_id, str(exc))
            return CourseBriefResult(
                brief_id=brief_id, course_id=course_id, status="failed",
                source_revision=source_rev, knowledge_revision=knowledge_rev,
                agent_run_id=run_id, error_code="generation_failed",
                error_detail=str(exc),
            )

        try:
            brief_json = _parse_brief_json(result.content)
            self._validate_brief_json(brief_json, allowed_fragment_ids)
            brief_json["metadata"] = {
                "sections_count": len(outline.sections),
                "kcs_count": len(kcs),
                "relations_count": len(relations),
                "fragment_count": sum(len(v) for v in evidence_map.values()),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        except (ValueError, json.JSONDecodeError, KeyError) as exc:
            self._store.update_agent_step(step_composer_id, "failed", error=str(exc))
            self._store.update_agent_run_status(
                course_id, run_id, "failed",
                error_code="validation_failed", error_detail=str(exc),
            )
            self._store.insert_course_brief(
                brief_id, course_id, source_rev, knowledge_rev, "{}",
                agent_run_id=run_id,
            )
            self._store.fail_course_brief(brief_id, f"Validation failed: {exc}")
            return CourseBriefResult(
                brief_id=brief_id, course_id=course_id, status="failed",
                source_revision=source_rev, knowledge_revision=knowledge_rev,
                agent_run_id=run_id, error_code="validation_failed",
                error_detail=str(exc),
            )

        self._store.update_agent_step(
            step_composer_id, "completed",
            model_call_id=result.call_id, elapsed_ms=elapsed,
        )
        self._store.update_agent_run_status(course_id, run_id, "completed")

        self._store.stale_course_briefs(course_id)
        self._store.insert_course_brief(
            brief_id, course_id, source_rev, knowledge_rev,
            json.dumps(brief_json, ensure_ascii=False),
            agent_run_id=run_id, model_call_id=result.call_id,
            elapsed_ms=elapsed,
        )

        return CourseBriefResult(
            brief_id=brief_id, course_id=course_id, status="active",
            brief_json=brief_json, source_revision=source_rev,
            knowledge_revision=knowledge_rev, agent_run_id=run_id,
            model_call_id=result.call_id, elapsed_ms=elapsed,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    async def get_current(self, course_id: str) -> CourseBriefResult | None:
        status = build_knowledge_status(self._store, course_id)
        source_rev = status.source_revision or _NO_SOURCE_REVISION
        knowledge_rev = status.knowledge_revision or _NO_KNOWLEDGE_REVISION

        row = self._store.get_active_course_brief(course_id)
        if row is None:
            return None
        return _row_to_brief_result(row, source_rev, knowledge_rev)

    def _validate_brief_json(self, raw: dict, allowed_fragment_ids: set[str]) -> None:
        if "overview" not in raw or not isinstance(raw["overview"], str):
            raise ValueError("brief_json missing 'overview' string field")
        key_topics = raw.get("key_topics", [])
        if not isinstance(key_topics, list):
            raise ValueError("brief_json 'key_topics' must be a list")
        for topic in key_topics:
            for ref in topic.get("evidence_refs", []):
                fid = ref.get("fragment_id", "")
                if fid and allowed_fragment_ids and fid not in allowed_fragment_ids:
                    raise ValueError(f"Unknown fragment_id in brief: {fid}")

    def _check_staleness(self, brief_row: dict, source_rev: str, knowledge_rev: str) -> tuple[bool, str | None]:
        reasons: list[str] = []
        if brief_row.get("source_revision") != source_rev:
            reasons.append(
                f"Source revision changed from {brief_row.get('source_revision')} to {source_rev}"
            )
        if brief_row.get("knowledge_revision") != knowledge_rev:
            reasons.append(
                f"Knowledge revision changed from {brief_row.get('knowledge_revision')} to {knowledge_rev}"
            )
        if reasons:
            return True, ". ".join(reasons)
        return False, None


def _row_to_brief_result(
    row: dict, current_source_rev: str, current_knowledge_rev: str,
) -> CourseBriefResult:
    brief_json = None
    try:
        brief_json = json.loads(row["brief_json"]) if row.get("brief_json") else None
    except (json.JSONDecodeError, TypeError):
        pass
    is_stale = False
    stale_reason = None
    status = row.get("status", "active")
    if status == "active":
        if row.get("source_revision") != current_source_rev:
            is_stale = True
            stale_reason = f"Source revision changed from {row.get('source_revision')} to {current_source_rev}"
        elif row.get("knowledge_revision") != current_knowledge_rev:
            is_stale = True
            stale_reason = f"Knowledge revision changed from {row.get('knowledge_revision')} to {current_knowledge_rev}"
    return CourseBriefResult(
        brief_id=row.get("brief_id"),
        course_id=row.get("course_id", ""),
        status="stale" if is_stale else status,
        brief_json=brief_json,
        source_revision=row.get("source_revision", ""),
        knowledge_revision=row.get("knowledge_revision", ""),
        is_stale=is_stale,
        stale_reason=stale_reason,
        agent_run_id=row.get("agent_run_id"),
        model_call_id=row.get("model_call_id"),
        input_token_count=row.get("input_token_count"),
        output_token_count=row.get("output_token_count"),
        elapsed_ms=row.get("elapsed_ms"),
        error_detail=row.get("error_detail"),
        created_at=row.get("created_at", ""),
    )
