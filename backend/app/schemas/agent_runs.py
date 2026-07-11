"""Agent-run and agent-step contracts for V2 interactive workflows.

An ``AgentRun`` is the durable, course-isolated owner of an interactive model
workflow (quick answer, deep dive, review session, study artifact, etc.).  It
is independent of ``knowledge_jobs``: it does not require a knowledge-job
lease and may own its own audited model calls.

These models deliberately persist only auditable actions, input fingerprints,
structured output references, usage and errors.  They do NOT persist hidden
chain-of-thought, full prompts, or material content.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentRunStatus = Literal[
    "accepted",
    "retrieving",
    "planning",
    "executing",
    "composing",
    "verifying",
    "completed",
    "failed",
    "interrupted",
    "cancelled",
    "stale",
]

WorkflowKind = Literal[
    "quick_answer",
    "deep_dive",
    "course_brief",
    "study_artifact",
    "review_plan",
    "review_session",
    "btw",
]

BudgetScope = Literal["knowledge_build", "interactive", "review", "artifact"]

# Non-terminal statuses: a run in any of these may still reserve model calls.
AGENT_RUN_ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        "accepted",
        "retrieving",
        "planning",
        "executing",
        "composing",
        "verifying",
    }
)


class AgentRun(BaseModel):
    """A course-scoped interactive agent workflow with its own budget."""

    run_id: str
    turn_id: str
    course_id: str
    session_id: str
    workflow_kind: WorkflowKind
    source_revision: str
    knowledge_revision: str
    status: AgentRunStatus
    scope_mode: Literal["all_ready", "selected"] = "all_ready"
    selected_material_ids: list[str] = []
    selected_note_ids: list[str] = []
    # Explicit IDs only (e.g. review_plan_id, review_session_id).  Never
    # chain-of-thought or material content.
    review_context: dict[str, Any] | None = None
    token_budget: int = Field(gt=0)
    error_code: str | None = None
    error_detail: str | None = None
    created_at: str
    updated_at: str


class AgentStep(BaseModel):
    """One auditable step within an :class:`AgentRun`.

    Only steps that made an audited provider call set ``model_call_id``; that
    id references ``model_call_audits.call_id``.  ``input_fingerprint`` is a
    SHA-256 of the step's structured inputs, not of the rendered prompt.
    """

    step_id: str
    run_id: str
    agent_role: str  # "scout", "mapper", "tutor", "verifier", "examiner", "grader", "coach"
    step_type: str  # "retrieve", "read_tools", "generate", "verify", "grade"
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    model_call_id: str | None = None
    output_type: str | None = None  # "evidence_pack", "answer_draft", "citation_list", ...
    input_fingerprint: str | None = None
    elapsed_ms: int | None = None
    error: str | None = None
    created_at: str
    completed_at: str | None = None
