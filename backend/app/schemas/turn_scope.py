"""TurnScope: immutable per-turn context that fixes what evidence an Agent run may read."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ScopeMode = Literal["all_ready", "selected"]


class TurnScope(BaseModel):
    """All material/note/session IDs are server-validated and course-scoped.

    A TurnScope is resolved once at the start of an agent turn from the durable
    knowledge status and the caller's request parameters.  It is then frozen:
    downstream steps (retrieval, writer, assembly) read from this scope rather
    than re-deriving identities, so a mid-turn material upload cannot silently
    change what evidence a run is allowed to cite.
    """

    turn_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    workflow_kind: str = "quick_answer"
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    scope_mode: ScopeMode = "all_ready"
    selected_material_ids: list[str] = []
    selected_note_ids: list[str] = []
    review_context: dict[str, Any] | None = None
