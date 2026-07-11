"""Versioned, evidence-backed V2 course projection contracts.

D0 deliberately publishes only a deterministic course outline.  Semantic
atoms, terms, KCs and relations arrive only after model-accounting contracts
are available, rather than creating an ungrounded parallel knowledge source.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.schemas.evidence import EvidenceRef


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CourseOutlineSection(BaseModel):
    """One deterministic material/heading group in a V2 course outline."""

    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    heading_path: list[str] = Field(default_factory=list)
    ordinal: int = Field(ge=0)
    evidence: list[EvidenceRef] = Field(min_length=1)


class CourseOutline(BaseModel):
    """The current course-navigation projection derived from source fragments."""

    course_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    sections: list[CourseOutlineSection] = Field(default_factory=list)
    fragment_count: int = Field(ge=0)


class CourseCompilation(BaseModel):
    """Small immutable compilation header used by status reads."""

    course_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    source_manifest_json: str = Field(min_length=2)
    source_fragment_count: int = Field(ge=0)
    outline_section_count: int = Field(ge=0)
    warning_count: int = Field(ge=0, default=0)
    created_at: str = Field(default_factory=_utc_now)
