"""Explicit contracts for persistent V2 knowledge-build jobs.

These models deliberately describe queue state only.  They do not start a
worker or define how parsing, embedding, or compilation is executed.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


KnowledgeJobType = Literal["index_material", "compile_course"]
KnowledgeJobScope = Literal["material", "course"]
KnowledgeJobStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "retryable",
    "failed",
]


class KnowledgeJobCreate(BaseModel):
    """Immutable identity and budget inputs required to enqueue a job."""

    job_id: str
    course_id: str = Field(min_length=1)
    material_id: str | None = None
    job_type: KnowledgeJobType
    revision: int = Field(ge=0)
    scope: KnowledgeJobScope
    idempotency_key: str = Field(min_length=1)
    token_budget: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_scope(self) -> "KnowledgeJobCreate":
        expected_scope: KnowledgeJobScope = (
            "material" if self.job_type == "index_material" else "course"
        )
        if self.scope != expected_scope:
            raise ValueError(
                f"job_type={self.job_type!r} requires scope={expected_scope!r}"
            )
        if self.scope == "material" and not self.material_id:
            raise ValueError("material-scoped knowledge jobs require material_id")
        if self.scope == "course" and self.material_id is not None:
            raise ValueError("course-scoped knowledge jobs must not include material_id")
        return self


class KnowledgeJob(BaseModel):
    """Persisted job state returned by the SQLite queue."""

    job_id: str
    course_id: str
    material_id: str | None = None
    job_type: KnowledgeJobType
    revision: int = Field(ge=0)
    scope: KnowledgeJobScope
    status: KnowledgeJobStatus
    attempt: int = Field(ge=0)
    idempotency_key: str
    token_budget: int | None = Field(default=None, gt=0)
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    error_at: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
