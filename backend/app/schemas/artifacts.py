"""V2-F7 Course Brief and Study Artifact result dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class CourseBriefResult:
    brief_id: str | None = None
    course_id: str = ""
    status: Literal["active", "stale", "failed", "not_found"] = "not_found"
    brief_json: dict | None = None
    source_revision: str = ""
    knowledge_revision: str = ""
    is_stale: bool = False
    stale_reason: str | None = None
    agent_run_id: str | None = None
    model_call_id: str | None = None
    input_token_count: int | None = None
    output_token_count: int | None = None
    elapsed_ms: int | None = None
    error_code: str | None = None
    error_detail: str | None = None
    created_at: str = ""


@dataclass(frozen=True)
class StudyArtifactResult:
    artifact_id: str | None = None
    course_id: str = ""
    section_id: str = ""
    section_title: str = ""
    artifact_type: str = "chapter_review_brief"
    status: Literal["active", "stale", "failed", "not_found"] = "not_found"
    artifact_json: dict | None = None
    source_revision: str = ""
    knowledge_revision: str = ""
    is_stale: bool = False
    stale_reason: str | None = None
    agent_run_id: str | None = None
    model_call_id: str | None = None
    input_token_count: int | None = None
    output_token_count: int | None = None
    elapsed_ms: int | None = None
    error_code: str | None = None
    error_detail: str | None = None
    created_at: str = ""


@dataclass(frozen=True)
class BatchArtifactResult:
    artifacts: list[StudyArtifactResult] = field(default_factory=list)
    total_sections: int = 0
    generated: int = 0
    failed: int = 0
    skipped_existing: int = 0


@dataclass(frozen=True)
class ArtifactListResult:
    artifacts: list[dict] = field(default_factory=list)
    is_stale: bool = False
    total_active: int = 0
    total_stale: int = 0
    total_failed: int = 0
