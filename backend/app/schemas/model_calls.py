"""Persistent, privacy-preserving audit contracts for V2 model calls.

The audit stores request fingerprints rather than prompts or source material.
It supplements, but never replaces, the durable ``knowledge_jobs`` workflow
state that owns retries and publication.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


ModelCallKind = Literal["text", "embedding", "vision"]
ModelCallStatus = Literal["reserved", "succeeded", "failed", "rejected"]
ModelUsageSource = Literal["provider", "estimated", "unavailable"]
ModelBudgetAvailability = Literal["available", "exhausted"]


class ModelCallReservationRequest(BaseModel):
    """The immutable identity and conservative reservation for one call."""

    call_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    lease_owner: str = Field(min_length=1)
    job_attempt: int = Field(ge=1)
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    call_kind: ModelCallKind
    purpose: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=200)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_token_upper_bound: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    course_budget_tokens: int = Field(gt=0)

    @property
    def reserved_tokens(self) -> int:
        return self.input_token_upper_bound + self.max_output_tokens


class ModelCallAudit(BaseModel):
    """A durable record for one attempted provider request."""

    call_id: str
    course_id: str
    job_id: str
    job_attempt: int = Field(ge=1)
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
