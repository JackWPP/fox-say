"""Read-only V2 knowledge availability contracts.

The overall course status deliberately differs from a material's parsing
status.  A course with all source fragments ready but no course compiler yet
is ``partial``: source-grounded questions can work, while the course map and
derived knowledge projections are still unavailable.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.model_calls import CourseModelBudget


KnowledgeLifecycleStatus = Literal[
    "empty",
    "processing",
    "partial",
    "ready",
    "stale",
    "failed",
]
SourceEvidenceStatus = Literal["empty", "processing", "partial", "ready", "failed"]
ProjectionStatus = Literal["not_started", "processing", "ready", "stale", "failed"]
MaterialEvidenceState = Literal[
    "processing",
    "ready",
    "retryable",
    "failed",
    "missing_evidence",
]
PersistedKnowledgeJobStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "retryable",
    "failed",
]


class KnowledgeCoverage(BaseModel):
    """Counts calculated from current material revisions only."""

    total_materials: int = Field(ge=0)
    ready_materials: int = Field(ge=0)
    processing_materials: int = Field(ge=0)
    retryable_materials: int = Field(ge=0)
    failed_materials: int = Field(ge=0)
    fragment_count: int = Field(ge=0)


class MaterialEvidenceStatus(BaseModel):
    """Availability of one current material revision for V2 retrieval."""

    material_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    material_revision: int = Field(ge=0)
    status: MaterialEvidenceState
    fragment_count: int = Field(ge=0)
    job_status: PersistedKnowledgeJobStatus | None = None
    error_code: str | None = None
    error_detail: str | None = None


class KnowledgeStatus(BaseModel):
    """A durable snapshot for course knowledge availability and coverage."""

    course_id: str = Field(min_length=1)
    status: KnowledgeLifecycleStatus
    source_status: SourceEvidenceStatus
    projection_status: ProjectionStatus
    source_revision: str | None = None
    knowledge_revision: str | None = None
    # V2-D writes this only after a successful course-level compiler snapshot.
    # Keeping it explicit prevents a bare integer job revision from being
    # mistaken for a material-set revision when stale detection arrives.
    compiled_from_source_revision: str | None = None
    # Only present after a V2 audited model call has established a durable
    # course/source budget. It never reports legacy model usage.
    model_budget: CourseModelBudget | None = None
    coverage: KnowledgeCoverage
    materials: list[MaterialEvidenceStatus] = Field(default_factory=list)
