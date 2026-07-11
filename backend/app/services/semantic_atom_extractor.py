"""Audited, evidence-constrained SemanticAtom extraction handler."""

from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import ValidationError

from app.db.sqlite_store import SqliteStore
from app.schemas.knowledge_jobs import KnowledgeJob
from app.schemas.semantic_atoms import SemanticAtomCandidate
from app.services.audited_text_model import (
    AuditedModelCallError,
    AuditedTextResult,
    build_audited_deepseek_text_model,
)
from app.services.knowledge_worker import KnowledgeJobExecutionError
from app.services.semantic_atom_compiler import build_semantic_atoms


SEMANTIC_ATOM_MAX_OUTPUT_TOKENS = 8000


class AuditedTextCompleter(Protocol):
    async def complete(
        self,
        job: KnowledgeJob,
        *,
        lease_owner: str,
        purpose: str,
        messages: list[dict[str, str]],
        max_output_tokens: int,
        temperature: float | None = None,
    ) -> AuditedTextResult: ...


class SemanticAtomExtractor:
    """Turn one explicit course job into a D1b1-pinned atom projection."""

    def __init__(self, store: SqliteStore, *, text_model: AuditedTextCompleter | None = None) -> None:
        self._store = store
        self._text_model = text_model or build_audited_deepseek_text_model(store)

    async def __call__(self, job: KnowledgeJob) -> None:
        if (
            job.job_type != "extract_semantic_atoms"
            or job.scope != "course"
            or job.target_source_revision is None
            or job.target_knowledge_revision is None
            or job.lease_owner is None
        ):
            raise KnowledgeJobExecutionError(
                "Semantic atom extractor received an invalid claimed course job",
                code="invalid_semantic_atom_job",
                retryable=False,
            )
        manifest = self._store.get_compilable_source_manifest(job.course_id)
        if manifest is None or manifest[0] != job.target_source_revision:
            raise KnowledgeJobExecutionError(
                "Course source revision changed or is not ready before semantic extraction",
                code="stale_course_source_revision",
                retryable=False,
            )
        outline = self._store.get_current_course_outline(job.course_id, manifest[0])
        if outline is None or outline.knowledge_revision != job.target_knowledge_revision:
            raise KnowledgeJobExecutionError(
                "Current D0 course outline is missing or does not match this semantic job",
                code="semantic_atom_outline_unavailable",
                retryable=False,
            )
        fragments = self._store.list_current_ready_source_fragments(job.course_id)
        try:
            result = await self._text_model.complete(
                job,
                lease_owner=job.lease_owner,
                purpose="semantic_atom_extract",
                messages=_build_messages(outline, fragments),
                max_output_tokens=SEMANTIC_ATOM_MAX_OUTPUT_TOKENS,
                temperature=0.0,
            )
        except AuditedModelCallError as exc:
            raise KnowledgeJobExecutionError(exc.detail, code=exc.code, retryable=exc.retryable) from exc

        candidates, malformed_count = _parse_candidates(result.content, result.call_id)
        atoms, rejected_count = build_semantic_atoms(
            candidates,
            course_id=job.course_id,
            source_revision=job.target_source_revision,
            knowledge_revision=job.target_knowledge_revision,
            outline=outline,
            fragments=fragments,
        )
        published = self._store.publish_semantic_atoms_if_current(
            course_id=job.course_id,
            job_id=job.job_id,
            job_attempt=job.attempt,
            lease_owner=job.lease_owner,
            source_revision=job.target_source_revision,
            knowledge_revision=job.target_knowledge_revision,
            atoms=atoms,
            rejected_candidate_count=rejected_count + malformed_count,
        )
        if not published:
            if not self._store.has_current_knowledge_job_lease(
                course_id=job.course_id,
                job_id=job.job_id,
                attempt=job.attempt,
                lease_owner=job.lease_owner,
                source_revision=job.target_source_revision,
                knowledge_revision=job.target_knowledge_revision,
            ):
                raise KnowledgeJobExecutionError(
                    "Semantic atom extractor lost its knowledge-job lease before publication",
                    code="knowledge_job_lease_lost",
                    retryable=True,
                )
            raise KnowledgeJobExecutionError(
                "Course source revision changed before semantic atoms could be published",
                code="stale_course_source_revision",
                retryable=False,
            )


def _build_messages(outline: Any, fragments: list[Any]) -> list[dict[str, str]]:
    fragments_by_id = {fragment.fragment_id: fragment for fragment in fragments}
    sections: list[dict[str, Any]] = []
    for section in outline.sections:
        allowed = [
            {"fragment_id": ref.fragment_id, "text": fragments_by_id[ref.fragment_id].text}
            for ref in section.evidence
            if ref.fragment_id in fragments_by_id
        ]
        sections.append({"section_id": section.section_id, "fragments": allowed})
    return [
        {
            "role": "system",
            "content": (
                "Extract only evidence-supported course semantic atoms. Return JSON only: "
                '{"atoms":[{"atom_type":"concept|definition|formula|condition|theorem|procedure|example|pitfall",'
                '"statement":"short material-grounded claim","section_id":"provided id",'
                '"evidence_fragment_ids":["provided id"]}]}. '
                "Every evidence_fragment_id must appear in the same supplied section."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({"sections": sections}, ensure_ascii=False, separators=(",", ":")),
        },
    ]


def _parse_candidates(content: str, model_call_id: str) -> tuple[list[SemanticAtomCandidate], int]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise KnowledgeJobExecutionError(
            "Semantic atom model response is not valid JSON",
            code="semantic_atom_output_invalid",
            retryable=True,
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("atoms"), list):
        raise KnowledgeJobExecutionError(
            "Semantic atom model response must be an object containing an atoms list",
            code="semantic_atom_output_invalid",
            retryable=True,
        )
    candidates: list[SemanticAtomCandidate] = []
    malformed_count = 0
    for item in payload["atoms"]:
        if not isinstance(item, dict):
            malformed_count += 1
            continue
        try:
            candidates.append(SemanticAtomCandidate.model_validate({**item, "model_call_id": model_call_id}))
        except ValidationError:
            malformed_count += 1
    return candidates, malformed_count
