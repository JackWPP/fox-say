"""Evidence-backed SemanticAtom contracts for the V2 knowledge projection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence import EvidenceRef


SemanticAtomType = Literal[
    "concept",
    "definition",
    "formula",
    "condition",
    "theorem",
    "procedure",
    "example",
    "pitfall",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SemanticAtomCandidate(BaseModel):
    """Untrusted model candidate; IDs are rehydrated before persistence."""

    atom_type: SemanticAtomType
    statement: str = Field(min_length=1, max_length=1600)
    section_id: str = Field(min_length=1)
    evidence_fragment_ids: list[str] = Field(min_length=1, max_length=8)
    model_call_id: str = Field(min_length=1)


class SemanticAtom(BaseModel):
    """A current-evidence semantic projection, never an independent fact."""

    atom_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    atom_type: SemanticAtomType
    statement: str = Field(min_length=1, max_length=1600)
    evidence: list[EvidenceRef] = Field(min_length=1)
    model_call_id: str = Field(min_length=1)
    generation_method: Literal["model"] = "model"
    created_at: str = Field(default_factory=_utc_now)


class SemanticAtomCompilation(BaseModel):
    """Small immutable header for a source-pinned atom projection."""

    course_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    atom_count: int = Field(ge=0)
    rejected_candidate_count: int = Field(ge=0)
    model_call_count: int = Field(ge=0)
    created_at: str = Field(default_factory=_utc_now)
