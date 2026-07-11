"""Audited, evidence-pinned V2 relations between current knowledge components."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence import EvidenceRef


KC_RELATION_COMPILER_VERSION = "kc-relations-d3b"
KCRelationType = Literal["prerequisite", "related"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_kc_relation_id(*, course_id: str, source_revision: str, knowledge_revision: str,
                         source_kc_id: str, target_kc_id: str, relation_type: KCRelationType,
                         evidence_fragment_id: str) -> str:
    payload = json.dumps({"course_id": course_id, "source_revision": source_revision,
        "knowledge_revision": knowledge_revision, "source_kc_id": source_kc_id,
        "target_kc_id": target_kc_id, "relation_type": relation_type,
        "evidence_fragment_id": evidence_fragment_id}, ensure_ascii=False,
        separators=(",", ":"), sort_keys=True)
    return f"kcr_{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class KCRelationCandidate(BaseModel):
    source_kc_id: str = Field(min_length=1)
    target_kc_id: str = Field(min_length=1)
    relation_type: KCRelationType
    evidence_fragment_id: str = Field(min_length=1)
    model_call_id: str = Field(min_length=1)


class KCRelation(BaseModel):
    relation_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    source_kc_id: str = Field(min_length=1)
    target_kc_id: str = Field(min_length=1)
    relation_type: KCRelationType
    evidence: EvidenceRef
    model_call_id: str = Field(min_length=1)
    generation_method: Literal["model"] = "model"
    created_at: str = Field(default_factory=_utc_now)


class KCRelationCompilation(BaseModel):
    course_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    relation_count: int = Field(ge=0)
    rejected_candidate_count: int = Field(ge=0)
    model_call_count: int = Field(ge=1)
    created_at: str = Field(default_factory=_utc_now)
