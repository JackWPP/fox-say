"""Quick-answer service: retrieve -> CRAG decision -> audited writer -> assembled envelope.

This service is the V2 replacement for the legacy CRAG chat path that
produced refusals when evidence was insufficient.  Instead, ``out_of_scope``
retrieval produces a transparent supplementary answer: the writer is called
with empty context and the envelope is marked
``answer_source='supplementary'`` so the student can see that the answer
comes from general knowledge rather than course material.

Design principles enforced here:

- **Model cannot skip retrieval**: ``retrieve_current_fragments`` is always
  called first, even when the answer seems obvious.
- **Model cannot forge citations**: only fragment IDs from the
  ``RetrievalOutcome``'s hits are valid; ``assemble_answer_envelope`` is the
  only path that produces citations.
- **Server assembles citations**: the writer returns opaque fragment IDs;
  the server validates them against the allowed set.
- **No legacy mixing**: this service reads only from V2 source fragments.
- **Course-agnostic**: no hardcoded subject names, chapter names, or
  math-specific fields.
- **Audited**: every model call goes through ``reserve_agent_run_model_call``
  with ``max_retries=0``.
- **Four honest states**: grounded / ambiguous / out_of_scope+supplementary /
  unavailable.
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
from app.schemas.evidence_pack import EvidencePack
from app.schemas.retrieval_answer import AnswerEnvelope, RetrievalOutcome
from app.schemas.turn_scope import TurnScope
from app.services.answer_envelope import assemble_answer_envelope
from app.services.audited_chat_writer import AuditedChatWriter
from app.services.audited_text_model import AuditedModelCallError
from app.services.knowledge_status import build_knowledge_status
from app.services.retrieval import retrieve_current_fragments

# Sentinels for courses that have no durable source revision yet (e.g. an
# empty course with zero materials).  They let an AgentRun satisfy its
# non-empty source_revision requirement without pretending real evidence
# exists.
_NO_SOURCE_REVISION = "__no_source__"
_NO_KNOWLEDGE_REVISION = "__no_knowledge__"

_UNAVAILABLE_ANSWER_TEXT = (
    "无法检索当前课程材料，请稍后重试或检查课程材料状态。"
    "（以下为补充说明，非课程材料内容）"
)

_WRITER_SYSTEM_PROMPT = """\
你是 FoxSay 学习助手——一只聪明、有点狡黠但靠谱的课程学习伙伴。

你会收到课程材料中的证据片段和一个学生的问题。请基于证据回答问题。

规则：
1. 优先基于提供的课程材料证据回答。
2. 如果证据不足以完整回答，诚实说明哪些部分有材料支撑、哪些是通用知识补充。
3. 只能引用提供的片段 ID（allowed_fragment_ids），不得编造片段 ID、文件名或定位信息。
4. 如果没有提供证据片段，说明课程材料未覆盖此内容，以下为通用理解，建议对照教材确认。
5. 保持狐狸的个性：聪明、有点小狡黠，但真诚有帮助，不要变成无个性的通用助手。

请以 JSON 格式返回回答：
{"answer": "你的回答文本", "citation_fragment_ids": ["片段ID1", "片段ID2"]}

- answer：你的回答文本。
- citation_fragment_ids：你引用的片段 ID 列表，只能从提供的可引用片段 ID 中选择。\
如果没有证据或不需要引用，返回空列表。"""


@dataclass(frozen=True)
class QuickAnswerResult:
    """The complete outcome of one quick-answer turn."""

    run_id: str
    envelope: AnswerEnvelope
    evidence: EvidencePack
    writer_call_id: str | None = None
    run_status: str = "completed"
    error_code: str | None = None
    error_detail: str | None = None
    warnings: list[str] = field(default_factory=list)


class QuickAnswerService:
    """Server-assembled quick-answer workflow with CRAG boundary control."""

    def __init__(
        self,
        store: SqliteStore,
        writer: AuditedChatWriter,
        *,
        max_hits: int = 5,
        max_output_tokens: int = 1024,
        temperature: float | None = 0.3,
        default_token_budget: int = 10000,
    ) -> None:
        self._store = store
        self._writer = writer
        self._max_hits = max_hits
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
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
        max_hits: int | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
        # Injection points for tests / production DI.
        qdrant_store: Any | None = None,
        embed_query: Any | None = None,
        enable_vector: bool = False,
    ) -> QuickAnswerResult:
        """Produce one server-assembled answer envelope for a student question.

        ``selected_material_ids`` is passed directly to the retriever.  An
        explicit empty list means an empty material scope (no evidence), not
        all materials.  ``None`` means all current-ready materials.
        """
        hits_limit = max_hits or self._max_hits
        out_tokens = max_output_tokens or self._max_output_tokens
        temp = temperature if temperature is not None else self._temperature
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

        # 2. Create the AgentRun.  store.create_agent_run validates that the
        #    session belongs to the course (raises ValueError otherwise).
        run = self._create_run(scope, token_budget=budget)
        self._store.create_agent_run(run)

        # 3. Retrieval step.
        self._store.update_agent_run_status(course_id, run.run_id, "retrieving")
        retrieval_step = self._create_step(
            run.run_id, agent_role="scout", step_type="retrieve",
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
            limit=hits_limit,
            selected_material_ids=retrieval_selected,
            qdrant_store=qdrant_store,
            embed_query=embed_query,
            enable_vector=enable_vector,
        )
        self._complete_step(
            retrieval_step.step_id,
            output_type="evidence_pack",
            input_fingerprint=_fingerprint(query, str(retrieval_selected)),
        )

        # 4. Build the bounded EvidencePack from the outcome.
        evidence = _build_evidence_pack(outcome, hits_limit)

        # 5. Unavailable retrieval -> error envelope, no model call.
        if outcome.retrieval_availability == "unavailable":
            envelope = assemble_answer_envelope(
                outcome, answer=_UNAVAILABLE_ANSWER_TEXT
            )
            self._store.update_agent_run_status(course_id, run.run_id, "completed")
            return QuickAnswerResult(
                run_id=run.run_id,
                envelope=envelope,
                evidence=evidence,
                run_status="completed",
            )

        # 6. Writer call.
        self._store.update_agent_run_status(course_id, run.run_id, "composing")
        writer_step = self._create_step(
            run.run_id, agent_role="tutor", step_type="generate",
        )
        messages = _build_writer_messages(query, evidence)

        try:
            writer_result = await self._writer.complete(
                run,
                purpose="quick_answer",
                messages=messages,
                max_output_tokens=out_tokens,
                temperature=temp,
            )
        except AuditedModelCallError as exc:
            self._fail_step(writer_step.step_id, error=str(exc))
            self._store.update_agent_run_status(
                course_id, run.run_id, "failed",
                error_code=exc.code, error_detail=exc.detail,
            )
            envelope = assemble_answer_envelope(
                outcome,
                answer=f"无法生成回答：{exc.detail}",
                answer_source="supplementary",
            )
            return QuickAnswerResult(
                run_id=run.run_id,
                envelope=envelope,
                evidence=evidence,
                run_status="failed",
                error_code=exc.code,
                error_detail=exc.detail,
            )

        self._complete_step(
            writer_step.step_id,
            model_call_id=writer_result.call_id,
            output_type="answer_draft",
            input_fingerprint=_fingerprint(evidence.context_text, query),
        )

        # 7. Parse the writer's structured JSON response.
        answer_text, citation_ids, parse_warning = _parse_writer_response(
            writer_result.content
        )

        # 8. Check for stale source revision (the source set changed during
        #    the call).
        current_status = build_knowledge_status(self._store, course_id)
        is_stale = current_status.source_revision != scope.source_revision

        # 9. Assemble the AnswerEnvelope.  The server validates that all
        #    cited fragment IDs are from the allowed set.
        self._store.update_agent_run_status(course_id, run.run_id, "verifying")
        assembly_step = self._create_step(
            run.run_id, agent_role="verifier", step_type="verify",
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
            assembly_step.step_id,
            output_type="answer_envelope",
            input_fingerprint=_fingerprint(answer_text, str(citation_ids)),
        )

        # 10. Finalize run status.
        warnings: list[str] = []
        if parse_warning:
            warnings.append(parse_warning)

        if is_stale:
            self._store.update_agent_run_status(
                course_id, run.run_id, "stale",
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

        return QuickAnswerResult(
            run_id=run.run_id,
            envelope=envelope,
            evidence=evidence,
            writer_call_id=writer_result.call_id,
            run_status=final_status,
            warnings=warnings,
        )

    # -- TurnScope / AgentRun / AgentStep helpers ---------------------------

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
            workflow_kind="quick_answer",
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            scope_mode=scope_mode,
            selected_material_ids=list(selected_material_ids) if selected_material_ids is not None else [],
            selected_note_ids=list(selected_note_ids) if selected_note_ids is not None else [],
            review_context=review_context,
        )

    def _create_run(self, scope: TurnScope, *, token_budget: int) -> AgentRun:
        now = _now_str()
        return AgentRun(
            run_id=str(uuid.uuid4()),
            turn_id=scope.turn_id,
            course_id=scope.course_id,
            session_id=scope.session_id,
            workflow_kind="quick_answer",
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


# -- Module-level helpers --------------------------------------------------


def _build_evidence_pack(outcome: RetrievalOutcome, max_hits: int) -> EvidencePack:
    """Select, bound, and render the evidence for one writer call."""
    if not outcome.hits:
        return EvidencePack(outcome=outcome)

    selected = list(outcome.hits[:max_hits])
    lines: list[str] = []
    for index, hit in enumerate(selected, 1):
        lines.append(f"[片段{index}] {hit.file_name} · {hit.evidence.locator}")
        lines.append(hit.canonical_text)
        lines.append("")
    context_text = "\n".join(lines).strip()
    allowed = [hit.evidence.fragment_id for hit in selected]
    return EvidencePack(
        outcome=outcome,
        selected_hits=selected,
        context_text=context_text,
        allowed_fragment_ids=allowed,
    )


def _build_writer_messages(
    query: str, evidence: EvidencePack
) -> list[dict[str, str]]:
    """Build the course-agnostic writer prompt (system + user)."""
    parts: list[str] = [f"学生问题：{query}"]

    if evidence.context_text:
        parts.append(f"\n课程材料证据：\n{evidence.context_text}")
    else:
        parts.append("\n课程材料证据：\n（本课程材料未覆盖此内容）")

    if evidence.allowed_fragment_ids:
        ids_str = ", ".join(evidence.allowed_fragment_ids)
        parts.append(f"\n可引用的片段 ID：{ids_str}")
    else:
        parts.append("\n可引用的片段 ID：（无）")

    parts.append(
        '\n请以 JSON 格式返回：{"answer": "...", "citation_fragment_ids": [...]}'
    )

    return [
        {"role": "system", "content": _WRITER_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]


def _parse_writer_response(
    content: str,
) -> tuple[str, list[str], str | None]:
    """Parse the writer's JSON response into answer text and citation IDs.

    Returns ``(answer, citation_fragment_ids, warning)``.  If the JSON is
    malformed or the ``answer`` field is missing, the raw content is used as
    the answer with no citations and a warning is returned.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return (
            content,
            [],
            "writer response was not valid JSON; raw text used as answer",
        )

    if not isinstance(data, dict):
        return (
            content,
            [],
            "writer response JSON was not an object; raw text used as answer",
        )

    answer = data.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return (
            content,
            [],
            "writer response had no valid answer field; raw text used as answer",
        )

    raw_ids = data.get("citation_fragment_ids", [])
    if not isinstance(raw_ids, list):
        return (
            answer,
            [],
            "writer response citation_fragment_ids was not a list; no citations used",
        )

    citation_ids: list[str] = []
    invalid_count = 0
    for item in raw_ids:
        if isinstance(item, str) and item.strip():
            citation_ids.append(item.strip())
        else:
            invalid_count += 1

    warning: str | None = None
    if invalid_count:
        warning = (
            f"{invalid_count} citation_fragment_ids were not valid strings "
            "and were dropped"
        )
    return answer, citation_ids, warning


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
