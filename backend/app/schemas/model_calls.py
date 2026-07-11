"""Persistent, privacy-preserving audit contracts for V2 model calls.

The audit stores request fingerprints rather than prompts or source material.
It supplements, but never replaces, the durable ``knowledge_jobs`` workflow
state that owns retries and publication.

A model call is owned by exactly one of:

- ``owner_type='knowledge_job'`` (``owner_id`` = ``job_id``): the legacy path,
  gated by a knowledge-job lease and the course/source-revision budget.
- ``owner_type='agent_run'`` (``owner_id`` = ``run_id``): an interactive agent
  workflow, gated by the run's own token budget and a course-level interactive
  budget.  It does NOT require a knowledge-job lease.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


ModelCallKind = Literal["text", "embedding", "vision"]
ModelCallStatus = Literal["reserved", "succeeded", "failed", "rejected"]
ModelUsageSource = Literal["provider", "estimated", "unavailable"]
ModelBudgetAvailability = Literal["available", "exhausted"]

ModelCallOwnerType = Literal["knowledge_job", "agent_run"]
ModelCallBudgetScope = Literal["knowledge_build", "interactive", "review", "artifact"]


class ModelCallReservationRequest(BaseModel):
    """The immutable identity and conservative reservation for one call.

    For backward compatibility, ``owner_type`` defaults to ``'knowledge_job'``
    and ``owner_id`` defaults to ``job_id`` when not provided.  New agent-run
    callers must set ``owner_type='agent_run'`` and ``run_id``; the store will
    set ``owner_id`` to ``run_id``.
    """

    call_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    # knowledge_job owners: required (validated by the store's lease check).
    # agent_run owners: leave None and set run_id instead.
    job_id: str | None = None
    lease_owner: str = ""
    job_attempt: int | None = Field(default=None, ge=1)
    source_revision: str = ""
    knowledge_revision: str = ""
    call_kind: ModelCallKind
    purpose: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=200)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_token_upper_bound: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    course_budget_tokens: int = Field(gt=0)

    # Owner generalisation (V2-F1).  Defaults preserve the legacy path.
    owner_type: ModelCallOwnerType = "knowledge_job"
    owner_id: str | None = None
    budget_scope: ModelCallBudgetScope = "knowledge_build"
    # agent_run owners only.
    run_id: str | None = None

    @model_validator(mode="after")
    def validate_owner(self) -> "ModelCallReservationRequest":
        if self.owner_type == "knowledge_job":
            # Legacy path requires a job to gate against.  job_attempt is also
            # required because the legacy INSERT stored NOT NULL.
            if not self.job_id:
                raise ValueError("knowledge_job owners require job_id")
            if self.job_attempt is None:
                raise ValueError("knowledge_job owners require job_attempt")
            if self.run_id is not None:
                raise ValueError("knowledge_job owners must not set run_id")
        elif self.owner_type == "agent_run":
            if not self.run_id:
                raise ValueError("agent_run owners require run_id")
            if self.job_id is not None:
                raise ValueError("agent_run owners must not set job_id")
        else:  # pragma: no cover - exhausted by the Literal type
            raise ValueError(f"unknown owner_type {self.owner_type!r}")
        return self

    @property
    def effective_owner_id(self) -> str:
        """Resolve the owner_id used to key the per-owner budget aggregate."""
        if self.owner_id is not None:
            return self.owner_id
        if self.owner_type == "knowledge_job":
            return self.job_id or ""
        return self.run_id or ""

    @property
    def reserved_tokens(self) -> int:
        return self.input_token_upper_bound + self.max_output_tokens


class ModelCallAudit(BaseModel):
    """A durable record for one attempted provider request."""

    call_id: str
    course_id: str
    job_id: str | None = None
    job_attempt: int | None = Field(default=None, ge=1)
    source_revision: str
    knowledge_revision: str
    call_kind: ModelCallKind
    purpose: str
    provider: str
    model: str
    request_fingerprint: str
    status: ModelCallStatus
    input_token_upper_bound: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    reserved_tokens: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    usage_source: ModelUsageSource
    # Counts against both course and job budgets. For unknown provider billing
    # this remains the conservative reservation rather than silently becoming 0.
    accounted_tokens: int = Field(ge=0)
    course_budget_tokens: int = Field(gt=0)
    job_budget_tokens: int | None = Field(default=None, gt=0)
    elapsed_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    error_detail: str | None = None
    started_at: str
    finished_at: str | None = None
    # V2-F1 owner generalisation.  Legacy rows migrate to
    # owner_type='knowledge_job', owner_id=job_id, budget_scope='knowledge_build'.
    owner_type: ModelCallOwnerType = "knowledge_job"
    owner_id: str | None = None
    budget_scope: ModelCallBudgetScope = "knowledge_build"
    run_id: str | None = None


class CourseModelBudget(BaseModel):
    """The course/source-revision aggregate used for visible budget gating."""

    course_id: str
    source_revision: str
    token_budget: int = Field(gt=0)
    accounted_tokens: int = Field(ge=0)
    available_tokens: int = Field(ge=0)
    status: ModelBudgetAvailability
    last_error_code: str | None = None
    last_error_detail: str | None = None
    updated_at: str


class ModelCallUsage(BaseModel):
    """Normalised provider usage for completing an existing reservation."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    usage_source: ModelUsageSource

    @model_validator(mode="after")
    def validate_provider_usage(self) -> "ModelCallUsage":
        if self.usage_source == "provider" and self.total_tokens is None:
            raise ValueError("provider usage requires total_tokens")
        return self
