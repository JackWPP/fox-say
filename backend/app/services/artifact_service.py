"""V2-F7 ArtifactService: revision-bound study artifact generation per section."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

from app.db.sqlite_store import SqliteStore
from app.schemas.agent_runs import AgentRun, AgentStep
from app.schemas.artifacts import (
    ArtifactListResult,
    BatchArtifactResult,
    StudyArtifactResult,
)
from app.services.audited_chat_writer import AuditedChatWriter
from app.services.audited_text_model import AuditedModelCallError, AuditedTextResult
from app.services.knowledge_status import build_knowledge_status
from app.services.v2_agent_tools import V2AgentTools

_NO_SOURCE_REVISION = "__no_source__"
_NO_KNOWLEDGE_REVISION = "__no_knowledge__"

MAX_ARTIFACT_KCS_PER_SECTION = 6
MAX_ARTIFACT_EVIDENCE_PER_SECTION = 5
MAX_ARTIFACT_EVIDENCE_TEXT_LEN = 1500
MAX_OUTPUT_TOKENS = 2048

STUDY_ARTIFACT_SYSTEM_PROMPT = """你是 FoxSay 学习助手的"章节编撰师"——一只擅长将单个章节提炼成清晰学习笔记的狐狸。

你会收到：
1. 一个章节的标题和内容结构
2. 该章节的核心知识点（名称、类型和完整定义）
3. 该章节的证据片段（课程材料原文摘录）

你的任务：
为这一章节生成一份结构化的"章节复习简报"，帮助学生快速回顾和掌握本节内容。

简报必须包含：
1. **summary**：2-4句话概述本节内容。说明本节的核心目标和主要学习内容。
2. **key_concepts**：2-6个核心概念。每个概念包含：
   - concept：概念名称
   - explanation：1-3句话解释
   - kc_id：从提供的知识点列表中选出对应的 KC ID（如果没有，填 null）
   - evidence_refs：支持该概念的证据引用（从提供的可引用列表中选择）
3. **examples**：0-3个典型示例或应用场景。如果本节主要是定义和理论，可以为空。
4. **common_pitfalls**：0-3个常见误区或易错点。如果本节内容简单明确，可以为空。
5. **evidence_refs**：本节所有用到的证据引用列表（去重）。

规则：
1. 只能引用提供的知识点和证据片段。不得编造章节中没有的概念或示例。
2. examples 中的场景必须严格来自课程材料，不能编造"假设有一个学生..."类的虚构场景。
3. common_pitfalls 中的误区必须能从知识点定义和证据中合理推断，不能猜测学生会犯什么错。
4. 保持狐狸的个性：清晰、有条理，像一位为你准备了完美复习笔记的学伴。
5. 所有 evidence_refs 只能从提供的可引用证据列表中选择。

请以 JSON 格式返回：
{
  "summary": "本节概述",
  "key_concepts": [
    {
      "concept": "概念名",
      "explanation": "解释",
      "kc_id": "kc_xxx",
      "evidence_refs": [{"material_id": "...", "fragment_id": "...", "heading_path": "..."}]
    }
  ],
  "examples": [
    {
      "scenario": "场景描述",
      "description": "讲解",
      "evidence_refs": [{"material_id": "...", "fragment_id": "...", "heading_path": "..."}]
    }
  ],
  "common_pitfalls": [
    {
      "pitfall": "误区描述",
      "explanation": "解释",
      "evidence_refs": [{"material_id": "...", "fragment_id": "...", "heading_path": "..."}]
    }
  ],
  "evidence_refs": [{"material_id": "...", "fragment_id": "...", "heading_path": "..."}]
}

- key_concepts 至少包含 2 个条目。
- evidence_refs（顶层）是本节所有引用的去重列表。
- 如果 examples 或 common_pitfalls 为空，返回空列表 []。"""


def _build_artifact_user_message(
    section: dict,
    section_kcs: list[dict],
    section_evidence: list[dict],
) -> str:
    parts = [f"章节：{section['title']}（第{section['ordinal'] + 1}节）"]
    if section.get("heading_path"):
        parts.append(f"路径：{' > '.join(section['heading_path'])}")

    parts.append(f"\n核心知识点（共{len(section_kcs)}个）：")
    for kc in section_kcs[:MAX_ARTIFACT_KCS_PER_SECTION]:
        parts.append(f"  [{kc['kc_id']}] {kc['name']}（{kc['kind']}）")
        parts.append(f"    定义：{kc['definition'][:300]}")

    parts.append("\n课程材料证据：")
    for i, ev in enumerate(section_evidence[:MAX_ARTIFACT_EVIDENCE_PER_SECTION]):
        parts.append(f"  --- 证据片段 {i + 1} ---")
        parts.append(f"  fragment_id: {ev['fragment_id']}")
        parts.append(f"  material_id: {ev['material_id']}")
        if ev.get("heading_path"):
            parts.append(f"  heading_path: {' > '.join(ev['heading_path'])}")
        text = ev.get("text", "")[:MAX_ARTIFACT_EVIDENCE_TEXT_LEN]
        parts.append(f"  内容：{text}")

    parts.append("\n可引用的证据引用：")
    for ev in section_evidence[:MAX_ARTIFACT_EVIDENCE_PER_SECTION]:
        heading = " > ".join(ev["heading_path"]) if ev.get("heading_path") else ""
        parts.append(f"  fragment_id={ev['fragment_id']} heading_path={heading}")

    parts.append('\n请以 JSON 格式返回章节复习简报。')
    return "\n".join(parts)


def _parse_artifact_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("{"):
        return json.loads(text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("No JSON object found in model response")


class ArtifactService:
    """Revision-bound study artifact generation per course section."""

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
        section_id: str,
        force: bool = False,
    ) -> StudyArtifactResult:
        status = build_knowledge_status(self._store, course_id)
        source_rev = status.source_revision or _NO_SOURCE_REVISION
        knowledge_rev = status.knowledge_revision or _NO_KNOWLEDGE_REVISION

        if status.projection_status != "ready" or not status.source_revision:
            return StudyArtifactResult(
                course_id=course_id, section_id=section_id,
                status="not_found",
                error_code="projection_not_ready",
                error_detail="Course projection is not ready",
            )

        outline = self._tools.get_current_outline(course_id)
        if outline is None:
            return StudyArtifactResult(
                course_id=course_id, section_id=section_id,
                status="not_found",
                error_code="no_outline",
            )

        section_info = None
        for sec in outline.sections:
            if sec.section_id == section_id:
                section_info = sec
                break
        if section_info is None:
            return StudyArtifactResult(
                course_id=course_id, section_id=section_id,
                status="not_found",
                error_code="section_not_found",
                error_detail=f"Section {section_id} not in current outline",
            )

        if not force:
            existing = self._store.get_active_study_artifact_by_section(
                course_id, section_id
            )
            if existing is not None:
                return _row_to_artifact_result(existing, source_rev, knowledge_rev)

        kcs_raw = self._tools.get_current_knowledge_components(course_id)
        section_kcs = [
            kc for kc in kcs_raw
            if hasattr(kc, 'section_id') and kc.section_id == section_id
        ]
        kcs_dicts = [
            {"kc_id": kc.kc_id, "name": kc.name, "kind": kc.kind,
             "definition": kc.definition}
            for kc in section_kcs
        ]

        section_evidence: list[dict] = []
        allowed_fragment_ids: set[str] = set()
        seen_frags: set[str] = set()
        for kc in section_kcs:
            for ev in (kc.evidence if hasattr(kc, 'evidence') else []):
                if not hasattr(ev, 'fragment_id'):
                    continue
                if ev.fragment_id in seen_frags:
                    continue
                seen_frags.add(ev.fragment_id)
                preview = self._tools.open_evidence(
                    course_id, ev
                )
                text = ""
                heading_path: list[str] = []
                if preview is not None:
                    text = preview.text if hasattr(preview, 'text') else ""
                    heading_path = preview.heading_path if hasattr(preview, 'heading_path') else []
                section_evidence.append({
                    "material_id": ev.material_id if hasattr(ev, 'material_id') else "",
                    "fragment_id": ev.fragment_id,
                    "heading_path": heading_path,
                    "text": text,
                })
                allowed_fragment_ids.add(ev.fragment_id)

        section_dict = {
            "section_id": section_info.section_id,
            "title": section_info.title,
            "ordinal": section_info.ordinal,
            "heading_path": section_info.heading_path if hasattr(section_info, 'heading_path') else [],
        }
        user_message = _build_artifact_user_message(
            section_dict, kcs_dicts, section_evidence,
        )
        messages = [
            {"role": "system", "content": STUDY_ARTIFACT_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        run_id = f"ar_{uuid.uuid4().hex[:16]}"
        step_reader_id = f"as_{uuid.uuid4().hex[:16]}"
        step_composer_id = f"as_{uuid.uuid4().hex[:16]}"
        artifact_id = f"sa_{uuid.uuid4().hex[:16]}"

        run = AgentRun(
            run_id=run_id, turn_id=turn_id, course_id=course_id,
            session_id=session_id, workflow_kind="study_artifact",
            source_revision=source_rev, knowledge_revision=knowledge_rev,
            status="accepted", token_budget=self._default_token_budget,
        )
        self._store.create_agent_run(run)

        reader_step = AgentStep(
            step_id=step_reader_id, run_id=run_id,
            agent_role="reader", step_type="read_tools",
            status="completed", output_type="bounded_knowledge",
        )
        self._store.create_agent_step(reader_step)

        composer_step = AgentStep(
            step_id=step_composer_id, run_id=run_id,
            agent_role="composer", step_type="generate",
            status="running", output_type="study_artifact",
        )
        self._store.create_agent_step(composer_step)
        self._store.update_agent_run_status(course_id, run_id, "composing")

        started = time.monotonic()
        try:
            result: AuditedTextResult = await self._writer.complete(
                run, purpose="study_artifact", messages=messages,
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
            self._store.insert_study_artifact(
                artifact_id, course_id, source_rev, knowledge_rev,
                section_id, "{}", agent_run_id=run_id,
            )
            self._store.fail_study_artifact(artifact_id, str(exc))
            return StudyArtifactResult(
                artifact_id=artifact_id, course_id=course_id,
                section_id=section_id, section_title=section_info.title,
                status="failed", source_revision=source_rev,
                knowledge_revision=knowledge_rev, agent_run_id=run_id,
                error_code="generation_failed", error_detail=str(exc),
            )

        try:
            artifact_json = _parse_artifact_json(result.content)
            self._validate_artifact_json(artifact_json, allowed_fragment_ids)
            artifact_json["metadata"] = {
                "section_id": section_id,
                "kcs_in_section": len(section_kcs),
                "fragments_in_section": len(section_evidence),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        except (ValueError, json.JSONDecodeError, KeyError) as exc:
            self._store.update_agent_step(step_composer_id, "failed", error=str(exc))
            self._store.update_agent_run_status(
                course_id, run_id, "failed",
                error_code="validation_failed", error_detail=str(exc),
            )
            self._store.insert_study_artifact(
                artifact_id, course_id, source_rev, knowledge_rev,
                section_id, "{}", agent_run_id=run_id,
            )
            self._store.fail_study_artifact(artifact_id, f"Validation failed: {exc}")
            return StudyArtifactResult(
                artifact_id=artifact_id, course_id=course_id,
                section_id=section_id, section_title=section_info.title,
                status="failed", source_revision=source_rev,
                knowledge_revision=knowledge_rev, agent_run_id=run_id,
                error_code="validation_failed", error_detail=str(exc),
            )

        self._store.update_agent_step(
            step_composer_id, "completed",
            model_call_id=result.call_id, elapsed_ms=elapsed,
        )
        self._store.update_agent_run_status(course_id, run_id, "completed")

        self._store.stale_study_artifact(course_id, section_id)
        self._store.insert_study_artifact(
            artifact_id, course_id, source_rev, knowledge_rev,
            section_id, json.dumps(artifact_json, ensure_ascii=False),
            agent_run_id=run_id, model_call_id=result.call_id,
            elapsed_ms=elapsed,
        )

        return StudyArtifactResult(
            artifact_id=artifact_id, course_id=course_id,
            section_id=section_id, section_title=section_info.title,
            status="active", artifact_json=artifact_json,
            source_revision=source_rev, knowledge_revision=knowledge_rev,
            agent_run_id=run_id, model_call_id=result.call_id,
            elapsed_ms=elapsed,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    async def generate_all(
        self,
        *,
        course_id: str,
        session_id: str,
        turn_id: str,
        force: bool = False,
    ) -> BatchArtifactResult:
        status = build_knowledge_status(self._store, course_id)
        if status.projection_status != "ready":
            return BatchArtifactResult()

        outline = self._tools.get_current_outline(course_id)
        if outline is None:
            return BatchArtifactResult()

        results: list[StudyArtifactResult] = []
        generated = 0
        failed = 0
        skipped = 0

        for section in outline.sections:
            if not force:
                existing = self._store.get_active_study_artifact_by_section(
                    course_id, section.section_id,
                )
                if existing is not None:
                    skipped += 1
                    continue

            result = await self.generate(
                course_id=course_id, session_id=session_id,
                turn_id=turn_id, section_id=section.section_id,
                force=force,
            )
            results.append(result)
            if result.status == "active":
                generated += 1
            else:
                failed += 1

        return BatchArtifactResult(
            artifacts=results,
            total_sections=len(outline.sections),
            generated=generated,
            failed=failed,
            skipped_existing=skipped,
        )

    async def get_artifact(
        self, course_id: str, artifact_id: str,
    ) -> StudyArtifactResult | None:
        status = build_knowledge_status(self._store, course_id)
        source_rev = status.source_revision or _NO_SOURCE_REVISION
        knowledge_rev = status.knowledge_revision or _NO_KNOWLEDGE_REVISION
        row = self._store.get_study_artifact(course_id, artifact_id)
        if row is None:
            return None
        return _row_to_artifact_result(row, source_rev, knowledge_rev)

    async def list_artifacts(self, course_id: str) -> ArtifactListResult:
        status = build_knowledge_status(self._store, course_id)
        source_rev = status.source_revision or _NO_SOURCE_REVISION
        knowledge_rev = status.knowledge_revision or _NO_KNOWLEDGE_REVISION

        rows = self._store.get_study_artifacts(course_id)
        artifacts: list[dict] = []
        total_active = 0
        total_stale = 0
        total_failed = 0
        any_stale = False

        for row in rows:
            result = _row_to_artifact_result(row, source_rev, knowledge_rev)
            if result.is_stale:
                any_stale = True
            entry = {
                "artifact_id": result.artifact_id,
                "section_id": result.section_id,
                "section_title": result.section_title or row.get("section_title", ""),
                "artifact_type": result.artifact_type,
                "status": result.status,
                "is_stale": result.is_stale,
                "created_at": result.created_at,
            }
            artifacts.append(entry)
            if result.status == "active" and not result.is_stale:
                total_active += 1
            elif result.is_stale or result.status == "stale":
                total_stale += 1
            elif result.status == "failed":
                total_failed += 1

        return ArtifactListResult(
            artifacts=artifacts,
            is_stale=any_stale,
            total_active=total_active,
            total_stale=total_stale,
            total_failed=total_failed,
        )

    def _validate_artifact_json(self, raw: dict, allowed_fragment_ids: set[str]) -> None:
        if "summary" not in raw or not isinstance(raw["summary"], str):
            raise ValueError("artifact_json missing 'summary' string field")
        key_concepts = raw.get("key_concepts", [])
        if not isinstance(key_concepts, list):
            raise ValueError("'key_concepts' must be a list")
        for concept in key_concepts:
            for ref in concept.get("evidence_refs", []):
                fid = ref.get("fragment_id", "")
                if fid and allowed_fragment_ids and fid not in allowed_fragment_ids:
                    raise ValueError(f"Unknown fragment_id in artifact: {fid}")

    def _check_staleness(
        self, artifact_row: dict, source_rev: str, knowledge_rev: str,
    ) -> tuple[bool, str | None]:
        reasons: list[str] = []
        if artifact_row.get("source_revision") != source_rev:
            reasons.append(
                f"Source revision changed from {artifact_row.get('source_revision')} to {source_rev}"
            )
        if artifact_row.get("knowledge_revision") != knowledge_rev:
            reasons.append(
                f"Knowledge revision changed from {artifact_row.get('knowledge_revision')} to {knowledge_rev}"
            )
        if reasons:
            return True, ". ".join(reasons)
        return False, None


def _row_to_artifact_result(
    row: dict, current_source_rev: str, current_knowledge_rev: str,
) -> StudyArtifactResult:
    artifact_json = None
    try:
        artifact_json = json.loads(row["artifact_json"]) if row.get("artifact_json") else None
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
    return StudyArtifactResult(
        artifact_id=row.get("artifact_id"),
        course_id=row.get("course_id", ""),
        section_id=row.get("section_id", ""),
        section_title=row.get("section_title", ""),
        artifact_type=row.get("artifact_type", "chapter_review_brief"),
        status="stale" if is_stale else status,
        artifact_json=artifact_json,
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
