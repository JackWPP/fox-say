"""One-call, evidence-constrained D3b KC relation extractor."""

from __future__ import annotations

import json
from collections import defaultdict
from itertools import combinations
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.core.config import settings
from app.schemas.evidence import EvidenceRef, SourceFragment
from app.schemas.knowledge_components import KnowledgeComponent
from app.schemas.knowledge_jobs import KnowledgeJob
from app.schemas.kc_relations import KCRelation, KCRelationCandidate, build_kc_relation_id
from app.services.audited_text_model import AuditedModelCallError, build_audited_deepseek_text_model
from app.services.knowledge_worker import KnowledgeJobExecutionError

if TYPE_CHECKING:
    from app.db.sqlite_store import SqliteStore


def build_relation_candidates(
    components: list[KnowledgeComponent], fragments: list[SourceFragment],
) -> list[dict[str, str]]:
    """Offer only pairs whose literal KC names co-occur in a current fragment."""
    by_fragment: dict[str, list[KnowledgeComponent]] = defaultdict(list)
    for component in components:
        for evidence in component.evidence:
            by_fragment[evidence.fragment_id].append(component)
    fragment_by_id = {fragment.fragment_id: fragment for fragment in fragments}
    candidates: list[dict[str, str]] = []
    for fragment_id in sorted(by_fragment):
        fragment = fragment_by_id.get(fragment_id)
        if fragment is None:
            continue
        literal = sorted({item.kc_id: item for item in by_fragment[fragment_id]
                          if item.name in fragment.text}.values(), key=lambda item: item.kc_id)
        for source, target in combinations(literal, 2):
            candidates.append({"source_kc_id": source.kc_id, "source_name": source.name,
                               "target_kc_id": target.kc_id, "target_name": target.name,
                               "evidence_fragment_id": fragment_id, "text": fragment.text})
    return candidates


def build_kc_relations(
    candidates: list[KCRelationCandidate], *, allowed_pairs: list[dict[str, str]],
    course_id: str, source_revision: str, knowledge_revision: str,
    fragments: list[SourceFragment],
) -> tuple[list[KCRelation], int]:
    allowed = {
        (item["source_kc_id"], item["target_kc_id"], item["evidence_fragment_id"])
        for item in allowed_pairs
    }
    # A related pair is semantically undirected in this MVP, accept model output
    # in either offered order while retaining one deterministic representation.
    allowed |= {(target, source, fragment) for source, target, fragment in list(allowed)}
    fragment_by_id = {item.fragment_id: item for item in fragments}
    accepted: dict[str, KCRelation] = {}
    rejected = 0
    for candidate in candidates:
        key = (candidate.source_kc_id, candidate.target_kc_id, candidate.evidence_fragment_id)
        fragment = fragment_by_id.get(candidate.evidence_fragment_id)
        if key not in allowed or fragment is None:
            rejected += 1
            continue
        source_id, target_id = candidate.source_kc_id, candidate.target_kc_id
        if candidate.relation_type == "related" and target_id < source_id:
            source_id, target_id = target_id, source_id
        relation_id = build_kc_relation_id(
            course_id=course_id, source_revision=source_revision,
            knowledge_revision=knowledge_revision, source_kc_id=source_id,
            target_kc_id=target_id, relation_type=candidate.relation_type,
            evidence_fragment_id=fragment.fragment_id,
        )
        accepted[relation_id] = KCRelation(
            relation_id=relation_id, course_id=course_id, source_revision=source_revision,
            knowledge_revision=knowledge_revision, source_kc_id=source_id, target_kc_id=target_id,
            relation_type=candidate.relation_type, evidence=EvidenceRef.from_source_fragment(fragment),
            model_call_id=candidate.model_call_id,
        )
    return [accepted[key] for key in sorted(accepted)], rejected


class KCRelationExtractor:
    def __init__(self, store: SqliteStore, *, text_model: Any | None = None) -> None:
        self._store = store
        self._text_model = text_model or build_audited_deepseek_text_model(store)

    async def __call__(self, job: KnowledgeJob) -> None:
        if (job.job_type != "extract_kc_relations" or job.material_id is not None
            or job.target_source_revision is None or job.target_knowledge_revision is None
            or job.lease_owner is None):
            raise KnowledgeJobExecutionError("KC relation extractor received an invalid claimed course job",
                code="invalid_kc_relation_job", retryable=False)
        source_revision, knowledge_revision = job.target_source_revision, job.target_knowledge_revision
        components = self._store.get_current_knowledge_components(job.course_id, source_revision)
        candidates = build_relation_candidates(
            components, self._store.list_current_ready_source_fragments(job.course_id)
        )
        try:
            result = await self._text_model.complete(
                job, lease_owner=job.lease_owner, purpose="kc_relation_extract",
                messages=_build_messages(candidates),
                max_output_tokens=settings.knowledge_kc_relation_max_output_tokens, temperature=0.0,
            )
        except AuditedModelCallError as exc:
            raise KnowledgeJobExecutionError(exc.detail, code=exc.code, retryable=exc.retryable) from exc
        parsed, malformed = _parse_candidates(result.content, result.call_id)
        relations, rejected = build_kc_relations(
            parsed, allowed_pairs=candidates, course_id=job.course_id,
            source_revision=source_revision, knowledge_revision=knowledge_revision,
            fragments=self._store.list_current_ready_source_fragments(job.course_id),
        )
        published = self._store.publish_kc_relations_if_current(
            course_id=job.course_id, job_id=job.job_id, job_attempt=job.attempt,
            lease_owner=job.lease_owner, source_revision=source_revision,
            knowledge_revision=knowledge_revision, relations=relations,
            rejected_candidate_count=malformed + rejected,
        )
        if not published:
            if not self._store.has_current_knowledge_job_lease(course_id=job.course_id,
                job_id=job.job_id, attempt=job.attempt, lease_owner=job.lease_owner,
                source_revision=source_revision, knowledge_revision=knowledge_revision):
                raise KnowledgeJobExecutionError("KC relation extractor lost its knowledge-job lease",
                    code="knowledge_job_lease_lost", retryable=True)
            raise KnowledgeJobExecutionError("Course source or KC revision changed before relation publication",
                code="stale_kc_relation_source_revision", retryable=False)


def _build_messages(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": (
            "Choose only defensible relationships from the supplied literal co-occurrence candidates. "
            "Return JSON only: {\"relationships\":[{\"source_kc_id\":\"...\",\"target_kc_id\":\"...\","
            "\"relation_type\":\"prerequisite|related\",\"evidence_fragment_id\":\"...\"}]}. "
            "For prerequisite, source is required before target. Return [] when no relationship is explicit."
        )},
        {"role": "user", "content": json.dumps({"candidates": candidates}, ensure_ascii=False,
                                                     separators=(",", ":"))},
    ]


def _parse_candidates(content: str, model_call_id: str) -> tuple[list[KCRelationCandidate], int]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise KnowledgeJobExecutionError("KC relation model response is not valid JSON",
            code="kc_relation_output_invalid", retryable=True) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("relationships"), list):
        raise KnowledgeJobExecutionError("KC relation response must contain a relationships list",
            code="kc_relation_output_invalid", retryable=True)
    values: list[KCRelationCandidate] = []
    malformed = 0
    for item in payload["relationships"]:
        if not isinstance(item, dict):
            malformed += 1
            continue
        try:
            values.append(KCRelationCandidate.model_validate({**item, "model_call_id": model_call_id}))
        except ValidationError:
            malformed += 1
    return values, malformed
