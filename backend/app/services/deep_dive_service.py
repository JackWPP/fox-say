"""Bounded deep-dive multi-agent service: Scout -> Mapper -> Tutor -> Verifier.

Cross-chapter questions ("what's the relationship between linear independence,
full rank, and invertibility?") span multiple sections and knowledge-component
relationships.  A single-shot retrieval + writer call is insufficient because
the writer cannot reason about KC/relation topology without loading the entire
course.

The :class:`DeepDiveService` adds exactly **one** pre-writer text call (the
Mapper) to the existing quick-answer flow.  The total is **2 text model calls**
(Mapper + Tutor).  Scout retrieval is not a text call.  Verifier is
server-side only.

Design principles enforced here:

- **Hard 2-call limit**: Mapper + Tutor only.  Scout is retrieval, Verifier is
  server-side.
- **Bounded mapper input**: never dump the full course.  Use deterministic
  token-overlap selection (no embeddings for mapper input selection).
- **Graceful degradation**: mapper failure -> tutor with evidence only
  (quick-answer style).  Not fatal.
- **Skip mapper when projection not ready**: if no Terms/KCs/Relations exist,
  mapper input is empty -> skip mapper, use quick-answer style.
- **Course-agnostic prompts**: no hardcoded subject names or math-specific fields.
- **Audited**: every model call goes through ``AuditedChatWriter`` with
  ``max_retries=0``.
- **Four honest states**: grounded / ambiguous (material), out_of_scope
  (supplementary), unavailable (error).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.db.sqlite_store import SqliteStore
from app.schemas.agent_runs import AgentRun, AgentStep
from app.schemas.course_projection import CourseOutline
from app.schemas.evidence_pack import EvidencePack
from app.schemas.kc_relations import KCRelation
from app.schemas.knowledge_components import KnowledgeComponent
from app.schemas.retrieval_answer import AnswerEnvelope, RetrievalError, RetrievalOutcome
from app.schemas.terms import Term
from app.schemas.turn_scope import TurnScope
from app.services.answer_envelope import assemble_answer_envelope
from app.services.audited_chat_writer import AuditedChatWriter
from app.services.audited_text_model import AuditedModelCallError
from app.services.knowledge_status import build_knowledge_status
from app.services.quick_answer_service import _build_evidence_pack, _parse_writer_response
from app.services.retrieval import retrieve_current_fragments
from app.services.v2_agent_tools import V2AgentTools

# Sentinels mirroring QuickAnswerService.
_NO_SOURCE_REVISION = "__no_source__"
_NO_KNOWLEDGE_REVISION = "__no_knowledge__"

_UNAVAILABLE_ANSWER_TEXT = (
    "无法检索当前课程材料，请稍后重试或检查课程材料状态。"
    "（以下为补充说明，非课程材料内容）"
)

_OUT_OF_SCOPE_ANSWER_TEXT = (
    "课程材料中未覆盖此内容，以下为通用理解，建议对照教材确认。"
    "如需更深入的分析，可以尝试上传相关课程材料后再次提问。"
)

_MAPPER_DEGRADATION_WARNING = (
    "Mapper phase failed, degraded to single-shot quick answer. "
    "Answer may lack cross-chapter synthesis."
)

# -- Token budget caps (module-level constants, §7.1) -----------------------

MAPPER_MAX_INPUT_TOKENS = 8000
MAPPER_MAX_OUTPUT_TOKENS = 1500
TUTOR_MAX_INPUT_TOKENS = 8000
TUTOR_MAX_OUTPUT_TOKENS = 1500
MAX_BOUNDED_ITEMS = 10
MAX_OUTLINE_SECTIONS = 20
MAX_SCOUT_HITS = 8


# -- Mapper system prompt (§5.1) --------------------------------------------

_MAPPER_SYSTEM_PROMPT = """\
你是 FoxSay 学习助手的"课程地图师"--一只擅长理清知识脉络的狐狸。

你会收到：
1. 一个学生的跨章节问题
2. 课程的大纲结构（章节标题和顺序）
3. 一小部分与问题可能相关的术语和知识点（最多各10条）
4. 一小部分知识点之间的关系（最多10条）

你的任务：
1. 识别问题涉及哪些章节（从大纲中选择）
2. 从提供的术语/知识点列表中选出真正相关的，并说明它们扮演的角色
3. 基于提供的知识点关系，描述它们之间的联系
4. 用2-3句话构建一个"叙事桥梁"，说明这些概念如何关联

规则：
- 只能引用提供的大纲章节、术语、知识点和关系，不得编造不存在的章节、概念或关系
- 如果提供的知识点关系中缺少某些联系，在 key_relationships 中标记 evidence_supported=false
- 如果知识点列表中缺少关键概念，在 relevant_kcs 中依然可以提及，但无法给出 kc_id
- 保持简洁：每个 relevance_reason 不超过一句话
- 保持狐狸的个性：聪明、有条理，但不要变成无个性的数据分析师

请以 JSON 格式返回：
{
  "relevant_sections": [
    {"section_id": "...", "title": "...", "relevance_reason": "..."}
  ],
  "relevant_kcs": [
    {"kc_id": "...", "name": "...", "role": "source_concept|target_concept|bridge_concept|context"}
  ],
  "key_relationships": [
    {
      "description": "...",
      "involved_kc_ids": ["...", "..."],
      "evidence_supported": true
    }
  ],
  "narrative_bridge": "..."
}"""


# -- Tutor system prompt (§5.3) ---------------------------------------------

_TUTOR_SYSTEM_PROMPT = """\
你是 FoxSay 学习助手--一只聪明、有点狡黠但靠谱的课程学习伙伴。

你会收到：
1. 一个学生的跨章节问题
2. 课程材料中的证据片段（Scout 检索结果）
3. 课程地图师的分析结果（识别了相关章节、知识点和关系）

请综合证据和地图分析，给学生一个结构化的回答。

规则：
1. 优先基于提供的课程材料证据回答。
2. 对比多个概念时，先分别解释每个概念，再说明它们的关系。
3. 每个来自课程材料的事实性声明，必须提供来源引用（使用提供的片段 ID）。
4. 只能引用提供的片段 ID（allowed_fragment_ids），不得编造片段 ID、文件名或定位信息。
5. 地图师的叙事桥梁提供了概念关系的方向，但事实依据必须来自证据片段。
6. 如果没有证据片段，说明课程材料未覆盖此内容，以下为通用理解，建议对照教材确认。
7. 保持狐狸的个性：聪明、有点小狡黠，但真诚有帮助，不要变成无个性的通用助手。

请以 JSON 格式返回回答：
{"answer": "你的回答文本", "citation_fragment_ids": ["片段ID1", "片段ID2"]}

- answer：你的回答文本。建议结构：先分别解释概念，再分析关系，最后总结。
- citation_fragment_ids：你引用的片段 ID 列表，只能从提供的可引用片段 ID 中选择。\
如果没有证据或不需要引用，返回空列表。"""


# -- Result dataclass (§8) --------------------------------------------------


@dataclass(frozen=True)
class DeepDiveResult:
    """The complete outcome of one deep-dive turn."""

    run_id: str
    envelope: AnswerEnvelope
    evidence: EvidencePack
    mapper_ran: bool
    mapper_call_id: str | None = None
    tutor_call_id: str | None = None
    run_status: str = "completed"
    error_code: str | None = None
    error_detail: str | None = None
    warnings: list[str] = field(default_factory=list)


# -- Service class ----------------------------------------------------------


class DeepDiveService:
    """Bounded deep-dive workflow: Scout -> Mapper -> Tutor -> Verifier."""

    def __init__(
        self,
        store: SqliteStore,
        writer: AuditedChatWriter,
        tools: V2AgentTools,
        *,
        max_scout_hits: int = MAX_SCOUT_HITS,
        max_bounded_items: int = MAX_BOUNDED_ITEMS,
        mapper_max_input_tokens: int = MAPPER_MAX_INPUT_TOKENS,
        mapper_max_output_tokens: int = MAPPER_MAX_OUTPUT_TOKENS,
        tutor_max_input_tokens: int = TUTOR_MAX_INPUT_TOKENS,
        tutor_max_output_tokens: int = TUTOR_MAX_OUTPUT_TOKENS,
        temperature: float | None = 0.3,
        mapper_temperature: float | None = 0.1,
        default_token_budget: int = 20000,
    ) -> None:
        self._store = store
        self._writer = writer
        self._tools = tools
        self._max_scout_hits = max_scout_hits
        self._max_bounded_items = max_bounded_items
        self._mapper_max_input_tokens = mapper_max_input_tokens
        self._mapper_max_output_tokens = mapper_max_output_tokens
        self._tutor_max_input_tokens = tutor_max_input_tokens
        self._tutor_max_output_tokens = tutor_max_output_tokens
        self._temperature = temperature
        self._mapper_temperature = mapper_temperature
        self._default_token_budget = default_token_budget

    async def answer(
        self,
        *,
        course_id: str,
        session_id: str,
        turn_id: str,
        query: str,
        selected_material_ids: list[str] | None = None,
        selected_note_ids: list[str] | None = None,
        review_context: dict[str, Any] | None = None,
        token_budget: int | None = None,
        qdrant_store: Any | None = None,
        embed_query: Any | None = None,
        enable_vector: bool = False,
    ) -> DeepDiveResult:
        """Produce one server-assembled deep-dive answer envelope."""
        budget = token_budget or self._default_token_budget

        # 1. Resolve current revisions and build the immutable TurnScope.
        scope = self._build_turn_scope(
            course_id=course_id,
            session_id=session_id,
            turn_id=turn_id,
            selected_material_ids=selected_material_ids,
            selected_note_ids=selected_note_ids,
            review_context=review_context,
        )

        # 2. Create the AgentRun (workflow_kind="deep_dive").
        run = self._create_run(scope, token_budget=budget)
        self._store.create_agent_run(run)

        # 3. PHASE: Scout (retrieval, no model call).
        self._store.update_agent_run_status(course_id, run.run_id, "retrieving")
        scout_step = self._create_step(
            run.run_id, agent_role="scout", step_type="retrieve"
        )
        retrieval_selected = (
            list(scope.selected_material_ids)
            if scope.scope_mode == "selected"
            else None
        )
        outcome = retrieve_current_fragments(
            self._store,
            course_id,
            query,
            limit=self._max_scout_hits,
            selected_material_ids=retrieval_selected,
            qdrant_store=qdrant_store,
            embed_query=embed_query,
            enable_vector=enable_vector,
        )
        self._complete_step(
            scout_step.step_id,
            output_type="evidence_pack",
            input_fingerprint=_fingerprint(query, str(retrieval_selected)),
        )

        evidence = _build_evidence_pack(outcome, self._max_scout_hits)

        # 4. Unavailable retrieval -> error envelope, no model calls.
        if outcome.retrieval_availability == "unavailable":
            envelope = assemble_answer_envelope(
                outcome, answer=_UNAVAILABLE_ANSWER_TEXT
            )
            self._store.update_agent_run_status(
                course_id, run.run_id, "completed"
            )
            return DeepDiveResult(
                run_id=run.run_id,
                envelope=envelope,
                evidence=evidence,
                mapper_ran=False,
                run_status="completed",
            )

        # 5. Out-of-scope retrieval -> skip mapper and tutor, return
        #    supplementary answer (no model calls).
        if outcome.confidence == "out_of_scope":
            return self._handle_out_of_scope(run, outcome, evidence)

        # 6. PHASE: Mapper (1 text model call, or skipped).
        self._store.update_agent_run_status(course_id, run.run_id, "planning")
        mapper_output, mapper_ran, mapper_warning, mapper_call_id = (
            await self._run_mapper_phase(run, query, outcome, evidence)
        )

        warnings: list[str] = []
        if mapper_warning:
            warnings.append(mapper_warning)

        # 7. PHASE: Tutor (1 text model call).
        self._store.update_agent_run_status(course_id, run.run_id, "composing")
        tutor_result = await self._run_tutor_phase(
            run, query, evidence, mapper_output
        )

        # Tutor failure -> unavailable envelope (double failure).
        if isinstance(tutor_result, AuditedModelCallError):
            exc = tutor_result
            envelope = _build_unavailable_envelope(
                outcome,
                answer=f"无法生成回答：{exc.detail}",
                error_code=exc.code,
                error_detail=exc.detail,
            )
            self._store.update_agent_run_status(
                course_id,
                run.run_id,
                "failed",
                error_code=exc.code,
                error_detail=exc.detail,
            )
            return DeepDiveResult(
                run_id=run.run_id,
                envelope=envelope,
                evidence=evidence,
                mapper_ran=mapper_ran,
                run_status="failed",
                error_code=exc.code,
                error_detail=exc.detail,
                warnings=warnings,
            )

        answer_text, citation_ids, tutor_call_id, parse_warning = tutor_result
        if parse_warning:
            warnings.append(parse_warning)

        # 8. PHASE: Verifier (server-side, no model call).
        self._store.update_agent_run_status(course_id, run.run_id, "verifying")
        verifier_step = self._create_step(
            run.run_id, agent_role="verifier", step_type="verify"
        )
        answer_source = (
            "supplementary"
            if outcome.confidence == "out_of_scope"
            else None
        )
        envelope = assemble_answer_envelope(
            outcome,
            answer=answer_text,
            citation_fragment_ids=citation_ids,
            answer_source=answer_source,
        )
        self._complete_step(
            verifier_step.step_id,
            output_type="answer_envelope",
            input_fingerprint=_fingerprint(answer_text, str(citation_ids)),
        )

        # 9. Check for stale source revision.
        current_status = build_knowledge_status(self._store, course_id)
        is_stale = current_status.source_revision != scope.source_revision

        # 10. Finalize run status.
        if is_stale:
            self._store.update_agent_run_status(
                course_id,
                run.run_id,
                "stale",
                error_code="stale_source_revision",
                error_detail=(
                    "Course source revision changed during the answer turn; "
                    "the evidence may no longer be current"
                ),
            )
            warnings.append(
                "Course source revision changed during the call; "
                "the answer was assembled from the revision captured at turn start"
            )
            final_status = "stale"
        else:
            self._store.update_agent_run_status(course_id, run.run_id, "completed")
            final_status = "completed"

        return DeepDiveResult(
            run_id=run.run_id,
            envelope=envelope,
            evidence=evidence,
            mapper_ran=mapper_ran,
            mapper_call_id=mapper_call_id,
            tutor_call_id=tutor_call_id,
            run_status=final_status,
            warnings=warnings,
        )

    # -- Mapper phase --------------------------------------------------------

    async def _run_mapper_phase(
        self,
        run: AgentRun,
        query: str,
        outcome: RetrievalOutcome,
        evidence: EvidencePack,
    ) -> tuple[dict[str, Any] | None, bool, str | None, str | None]:
        """Execute the mapper phase.

        Returns ``(mapper_output, mapper_ran, warning, mapper_call_id)``.

        - If projection is not ready: mapper is skipped (``mapper_ran=False``,
          ``mapper_output=None``, no warning, ``mapper_call_id=None``).
        - If the mapper model call fails or JSON is invalid: degradation
          (``mapper_ran=False``, ``mapper_output=None``, warning set,
          ``mapper_call_id=None``).
        - On success: ``mapper_ran=True``, ``mapper_output`` is the parsed
          dict, no warning, ``mapper_call_id`` is the audited call ID.
        """
        mapper_step = self._create_step(
            run.run_id, agent_role="mapper", step_type="generate"
        )

        # Read bounded projection data.
        outline = self._tools.get_current_outline(run.course_id)
        terms = self._tools.get_current_terms(run.course_id)
        kcs = self._tools.get_current_knowledge_components(run.course_id)
        relations = self._tools.get_current_kc_relations(run.course_id)

        # If projection is not ready (no outline/terms/KCs/relations), skip.
        if outline is None and not terms and not kcs and not relations:
            self._skip_step(
                mapper_step.step_id,
                reason=(
                    "Course projection not ready; no Terms/KCs/Relations "
                    "available for deep-dive mapping"
                ),
            )
            return None, False, None, None

        # Build bounded selection and mapper messages.
        bounded = _select_bounded_items(query, outline, terms, kcs, relations)
        messages = _build_mapper_messages(query, bounded)

        try:
            mapper_result = await self._writer.complete(
                run,
                purpose="deep_dive_mapper",
                messages=messages,
                max_output_tokens=self._mapper_max_output_tokens,
                temperature=self._mapper_temperature,
            )
        except AuditedModelCallError as exc:
            self._fail_step(mapper_step.step_id, error=str(exc))
            return None, False, _MAPPER_DEGRADATION_WARNING, None

        self._complete_step(
            mapper_step.step_id,
            model_call_id=mapper_result.call_id,
            output_type="course_map",
            input_fingerprint=_fingerprint(query, str(bounded)),
        )

        mapper_output, parse_warning = _parse_mapper_response(mapper_result.content)
        if mapper_output is None:
            # JSON parse failure -> degrade but don't fail the run.
            return None, False, parse_warning or _MAPPER_DEGRADATION_WARNING, None

        return mapper_output, True, None, mapper_result.call_id

    # -- Tutor phase ---------------------------------------------------------

    async def _run_tutor_phase(
        self,
        run: AgentRun,
        query: str,
        evidence: EvidencePack,
        mapper_output: dict[str, Any] | None,
    ) -> tuple[str, list[str], str, str | None] | AuditedModelCallError:
        """Execute the tutor phase.

        Returns ``(answer_text, citation_ids, tutor_call_id, parse_warning)``
        on success, or an ``AuditedModelCallError`` on failure (caller
        returns unavailable envelope with the actual error code).
        """
        tutor_step = self._create_step(
            run.run_id, agent_role="tutor", step_type="generate"
        )
        messages = _build_tutor_messages(query, evidence, mapper_output)

        try:
            tutor_result = await self._writer.complete(
                run,
                purpose="deep_dive_tutor",
                messages=messages,
                max_output_tokens=self._tutor_max_output_tokens,
                temperature=self._temperature,
            )
        except AuditedModelCallError as exc:
            self._fail_step(tutor_step.step_id, error=str(exc))
            return exc

        self._complete_step(
            tutor_step.step_id,
            model_call_id=tutor_result.call_id,
            output_type="answer_draft",
            input_fingerprint=_fingerprint(evidence.context_text, query),
        )

        answer_text, citation_ids, parse_warning = _parse_writer_response(
            tutor_result.content
        )
        return answer_text, citation_ids, tutor_result.call_id, parse_warning

    # -- Out-of-scope handler ------------------------------------------------

    def _handle_out_of_scope(
        self,
        run: AgentRun,
        outcome: RetrievalOutcome,
        evidence: EvidencePack,
    ) -> DeepDiveResult:
        """Handle out-of-scope retrieval: skip mapper and tutor, return supplementary."""
        # Mapper skipped (out_of_scope_no_evidence).
        mapper_step = self._create_step(
            run.run_id, agent_role="mapper", step_type="generate"
        )
        self._skip_step(
            mapper_step.step_id,
            reason="out_of_scope_no_evidence",
        )

        # Tutor skipped.
        tutor_step = self._create_step(
            run.run_id, agent_role="tutor", step_type="generate"
        )
        self._skip_step(
            tutor_step.step_id,
            reason="out_of_scope_no_evidence",
        )

        # Verifier: assemble supplementary envelope.
        self._store.update_agent_run_status(
            run.course_id, run.run_id, "verifying"
        )
        verifier_step = self._create_step(
            run.run_id, agent_role="verifier", step_type="verify"
        )
        envelope = assemble_answer_envelope(
            outcome,
            answer=_OUT_OF_SCOPE_ANSWER_TEXT,
            answer_source="supplementary",
        )
        self._complete_step(
            verifier_step.step_id,
            output_type="answer_envelope",
            input_fingerprint=_fingerprint(_OUT_OF_SCOPE_ANSWER_TEXT),
        )

        self._store.update_agent_run_status(
            run.course_id, run.run_id, "completed"
        )
        return DeepDiveResult(
            run_id=run.run_id,
            envelope=envelope,
            evidence=evidence,
            mapper_ran=False,
            run_status="completed",
        )

    # -- TurnScope / AgentRun / AgentStep helpers ----------------------------

    def _build_turn_scope(
        self,
        *,
        course_id: str,
        session_id: str,
        turn_id: str,
        selected_material_ids: list[str] | None,
        selected_note_ids: list[str] | None,
        review_context: dict[str, Any] | None,
    ) -> TurnScope:
        status = build_knowledge_status(self._store, course_id)
        source_revision = status.source_revision or _NO_SOURCE_REVISION
        knowledge_revision = status.knowledge_revision or _NO_KNOWLEDGE_REVISION
        scope_mode = "selected" if selected_material_ids is not None else "all_ready"
        return TurnScope(
            turn_id=turn_id,
            course_id=course_id,
            session_id=session_id,
            workflow_kind="deep_dive",
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            scope_mode=scope_mode,
            selected_material_ids=(
                list(selected_material_ids) if selected_material_ids is not None else []
            ),
            selected_note_ids=(
                list(selected_note_ids) if selected_note_ids is not None else []
            ),
            review_context=review_context,
        )

    def _create_run(self, scope: TurnScope, *, token_budget: int) -> AgentRun:
        now = _now_str()
        return AgentRun(
            run_id=str(uuid.uuid4()),
            turn_id=scope.turn_id,
            course_id=scope.course_id,
            session_id=scope.session_id,
            workflow_kind="deep_dive",
            source_revision=scope.source_revision,
            knowledge_revision=scope.knowledge_revision,
            status="accepted",
            scope_mode=scope.scope_mode,
            selected_material_ids=scope.selected_material_ids,
            selected_note_ids=scope.selected_note_ids,
            review_context=scope.review_context,
            token_budget=token_budget,
            created_at=now,
            updated_at=now,
        )

    def _create_step(
        self, run_id: str, *, agent_role: str, step_type: str
    ) -> AgentStep:
        step = AgentStep(
            step_id=str(uuid.uuid4()),
            run_id=run_id,
            agent_role=agent_role,
            step_type=step_type,
            status="running",
            created_at=_now_str(),
        )
        self._store.create_agent_step(step)
        return step

    def _complete_step(
        self,
        step_id: str,
        *,
        output_type: str | None = None,
        model_call_id: str | None = None,
        input_fingerprint: str | None = None,
    ) -> None:
        self._store.update_agent_step(
            step_id,
            "completed",
            output_type=output_type,
            model_call_id=model_call_id,
            input_fingerprint=input_fingerprint,
        )

    def _fail_step(self, step_id: str, *, error: str) -> None:
        self._store.update_agent_step(step_id, "failed", error=error)

    def _skip_step(self, step_id: str, *, reason: str) -> None:
        self._store.update_agent_step(step_id, "skipped", error=reason)


# -- Module-level helpers ---------------------------------------------------


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_text(text: str) -> str:
    """NFKC + casefold for deterministic token-overlap matching."""
    import unicodedata

    return unicodedata.normalize("NFKC", text).casefold()


def _has_token_overlap(query_norm: str, field_norm: str) -> bool:
    """Check if any 2-character substring of the query appears in the field.

    This is a deterministic, zero-cost pruning heuristic (no embeddings).
    Works for both Chinese (character-level) and English (word-level via
    2-gram overlap).
    """
    if len(query_norm) < 2:
        return query_norm in field_norm
    for i in range(len(query_norm) - 1):
        if query_norm[i : i + 2] in field_norm:
            return True
    return False


def _select_bounded_items(
    query: str,
    outline: CourseOutline | None,
    terms: list[Term],
    kcs: list[KnowledgeComponent],
    relations: list[KCRelation],
) -> dict[str, list[dict[str, Any]]]:
    """Select bounded Term/KC/Relation/Outline items for the mapper prompt.

    Uses deterministic token-overlap selection (no embeddings).  Each list is
    capped at ``MAX_BOUNDED_ITEMS`` (10).  Outline is capped at
    ``MAX_OUTLINE_SECTIONS`` (20).
    """
    query_norm = _normalize_text(query)

    # Outline sections: take first MAX_OUTLINE_SECTIONS by ordinal.
    outline_sections: list[dict[str, Any]] = []
    if outline is not None:
        sorted_sections = sorted(outline.sections, key=lambda s: s.ordinal)
        for sec in sorted_sections[:MAX_OUTLINE_SECTIONS]:
            outline_sections.append(
                {
                    "section_id": sec.section_id,
                    "title": sec.title,
                    "heading_path": list(sec.heading_path),
                    "ordinal": sec.ordinal,
                }
            )

    # Terms: filter by token overlap, sort by canonical_name, cap at 10.
    matching_terms = [
        term
        for term in terms
        if _has_token_overlap(query_norm, _normalize_text(term.canonical_name))
        or _has_token_overlap(query_norm, _normalize_text(term.definition))
    ]
    matching_terms.sort(key=lambda t: t.canonical_name)
    bounded_terms: list[dict[str, Any]] = []
    for term in matching_terms[:MAX_BOUNDED_ITEMS]:
        bounded_terms.append(
            {
                "term_id": term.term_id,
                "canonical_name": term.canonical_name,
                "term_kind": term.term_kind,
                "definition": term.definition,
            }
        )

    # KCs: filter by token overlap, sort by (section_id, name), cap at 10.
    matching_kcs = [
        kc
        for kc in kcs
        if _has_token_overlap(query_norm, _normalize_text(kc.name))
        or _has_token_overlap(query_norm, _normalize_text(kc.definition))
    ]
    matching_kcs.sort(key=lambda k: (k.section_id, k.name))
    bounded_kcs: list[dict[str, Any]] = []
    selected_kc_ids: set[str] = set()
    for kc in matching_kcs[:MAX_BOUNDED_ITEMS]:
        bounded_kcs.append(
            {
                "kc_id": kc.kc_id,
                "name": kc.name,
                "kind": kc.kind,
                "definition": kc.definition,
                "section_id": kc.section_id,
            }
        )
        selected_kc_ids.add(kc.kc_id)

    # Relations: only relations where both endpoints are in selected KCs.
    # Prioritize prerequisite over related.  Cap at 10.
    matching_relations = [
        rel
        for rel in relations
        if rel.source_kc_id in selected_kc_ids
        and rel.target_kc_id in selected_kc_ids
    ]
    matching_relations.sort(
        key=lambda r: (0 if r.relation_type == "prerequisite" else 1, r.source_kc_id)
    )
    bounded_relations: list[dict[str, Any]] = []
    for rel in matching_relations[:MAX_BOUNDED_ITEMS]:
        bounded_relations.append(
            {
                "relation_id": rel.relation_id,
                "source_kc_id": rel.source_kc_id,
                "target_kc_id": rel.target_kc_id,
                "relation_type": rel.relation_type,
            }
        )

    return {
        "outline_sections": outline_sections,
        "terms": bounded_terms,
        "kcs": bounded_kcs,
        "relations": bounded_relations,
    }


def _build_mapper_messages(
    query: str, bounded: dict[str, list[dict[str, Any]]]
) -> list[dict[str, str]]:
    """Build the mapper prompt (system + user) from bounded selection."""
    return [
        {"role": "system", "content": _MAPPER_SYSTEM_PROMPT},
        {"role": "user", "content": _build_mapper_user_message(query, bounded)},
    ]


def _build_mapper_user_message(
    query: str, bounded: dict[str, list[dict[str, Any]]]
) -> str:
    """Build the mapper user message from bounded selection (§5.2 template)."""
    outline_sections = bounded["outline_sections"]
    bounded_terms = bounded["terms"]
    bounded_kcs = bounded["kcs"]
    bounded_relations = bounded["relations"]

    parts: list[str] = [f"学生问题：{query}"]

    if outline_sections:
        parts.append(f"\n课程大纲（共{len(outline_sections)}节）：")
        for sec in outline_sections[:MAX_OUTLINE_SECTIONS]:
            parts.append(
                f"  · [{sec['section_id']}] {sec['title']} (第{sec['ordinal'] + 1}节)"
            )

    if bounded_terms:
        parts.append(f"\n相关术语（共{len(bounded_terms)}条）：")
        for term in bounded_terms:
            parts.append(
                f"  · [{term['term_id']}] {term['canonical_name']}"
                f"（{term['term_kind']}）：{term['definition'][:120]}"
            )

    if bounded_kcs:
        parts.append(f"\n相关知识点（共{len(bounded_kcs)}条）：")
        for kc in bounded_kcs:
            parts.append(
                f"  · [{kc['kc_id']}] {kc['name']}"
                f"（{kc['kind']}）：{kc['definition'][:120]}"
            )

    if bounded_relations:
        parts.append(f"\n知识点关系（共{len(bounded_relations)}条）：")
        for rel in bounded_relations:
            parts.append(
                f"  · {rel['source_kc_id']} --[{rel['relation_type']}]--> "
                f"{rel['target_kc_id']}"
            )

    parts.append("\n请以 JSON 格式返回课程地图分析。")
    return "\n".join(parts)


def _build_tutor_messages(
    query: str,
    evidence: EvidencePack,
    mapper_output: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Build the tutor prompt (system + user) from evidence and mapper output."""
    return [
        {"role": "system", "content": _TUTOR_SYSTEM_PROMPT},
        {"role": "user", "content": _build_tutor_user_message(query, evidence, mapper_output)},
    ]


def _build_tutor_user_message(
    query: str,
    evidence: EvidencePack,
    mapper_output: dict[str, Any] | None,
) -> str:
    """Build the tutor user message from evidence and mapper output (§5.4 template)."""
    parts: list[str] = [f"学生问题：{query}"]

    # Evidence section (same as quick_answer).
    if evidence.context_text:
        parts.append(f"\n课程材料证据：\n{evidence.context_text}")
    else:
        parts.append("\n课程材料证据：\n（本课程材料未覆盖此内容）")

    # Mapper output section (deep-dive specific).
    if mapper_output:
        parts.append("\n课程地图分析：")
        narrative = mapper_output.get("narrative_bridge", "")
        if narrative:
            # Truncate narrative to 500 chars (§7.3).
            if len(narrative) > 500:
                narrative = narrative[:500] + "..."
            parts.append(f"  概念关系概述：{narrative}")

        sections = mapper_output.get("relevant_sections", [])
        if sections:
            sec_names = [s.get("title", "?") for s in sections]
            parts.append(f"  相关章节：{', '.join(sec_names)}")

        kcs = mapper_output.get("relevant_kcs", [])
        if kcs:
            kc_names = [k.get("name", "?") for k in kcs]
            parts.append(f"  相关知识点：{', '.join(kc_names)}")

        rels = mapper_output.get("key_relationships", [])
        if rels:
            # Truncate to 5 relationships (§7.3).
            parts.append("  知识点关系：")
            for rel in rels[:5]:
                desc = rel.get("description", "")
                supported = (
                    "（有证据支撑）" if rel.get("evidence_supported") else "（推论）"
                )
                parts.append(f"    · {desc} {supported}")

    # Allowed fragment IDs.
    if evidence.allowed_fragment_ids:
        ids_str = ", ".join(evidence.allowed_fragment_ids)
        parts.append(f"\n可引用的片段 ID：{ids_str}")
    else:
        parts.append("\n可引用的片段 ID：（无）")

    parts.append(
        '\n请以 JSON 格式返回：{"answer": "...", "citation_fragment_ids": [...]}'
    )
    return "\n".join(parts)


def _parse_mapper_response(content: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse the mapper's JSON response.

    Returns ``(parsed_dict, warning)``.  If the JSON is malformed, returns
    ``(None, warning_message)``.  Attempts to find a JSON substring before
    giving up (§11.4 edge case 2).
    """
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data, None
        return None, "mapper response JSON was not an object; mapper output discarded"
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object substring (§11.4 edge case 2).
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(content[start : end + 1])
            if isinstance(data, dict):
                return data, None
        except json.JSONDecodeError:
            pass

    return None, "mapper response was not valid JSON; mapper output discarded"


def _build_unavailable_envelope(
    outcome: RetrievalOutcome,
    *,
    answer: str,
    error_code: str,
    error_detail: str,
) -> AnswerEnvelope:
    """Build an unavailable envelope when the tutor model call fails.

    The retrieval may have succeeded, but the system could not produce an
    answer.  The envelope is marked ``unavailable`` so the student sees a
    clear system error rather than a misleading "available" state.
    """
    return AnswerEnvelope(
        course_id=outcome.course_id,
        source_revision=outcome.source_revision,
        knowledge_revision=outcome.knowledge_revision,
        answer=answer,
        retrieval_availability="unavailable",
        confidence_status=None,
        answer_source="supplementary",
        citations=[],
        relevance=outcome.relevance,
        coverage=outcome.coverage,
        error=RetrievalError(
            error_code=error_code,
            error_detail=error_detail,
            retriable=True,
        ),
        retrieval_warnings=list(outcome.warnings),
        warnings=[],
    )
