"""Evidence-backed, rule-derived V2 knowledge-component contracts."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence import EvidenceRef


KC_COMPILER_VERSION = "kcs-d3a"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_knowledge_component_id(
    *, course_id: str, source_revision: str, knowledge_revision: str, term_id: str
) -> str:
    payload = json.dumps(
        {
            "course_id": course_id,
            "source_revision": source_revision,
            "knowledge_revision": knowledge_revision,
            "term_id": term_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"kc_{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class KnowledgeComponent(BaseModel):
    """One course-scoped, review-ready projection of exactly one V2 Term."""

    kc_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    term_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=160)
    kind: Literal["concept", "definition", "formula", "theorem", "procedure"]
    definition: str = Field(min_length=1, max_length=1600)
    section_id: str = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(min_length=1)
    generation_method: Literal["rule"] = "rule"
    created_at: str = Field(default_factory=_utc_now)


class KnowledgeComponentCompilation(BaseModel):
    course_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    kc_count: int = Field(ge=0)
    rejected_term_count: int = Field(ge=0)
    created_at: str = Field(default_factory=_utc_now)
