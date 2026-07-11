"""Evidence-backed, rule-derived V2 terminology contracts."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence import EvidenceRef


TermKind = Literal["concept", "definition", "formula", "theorem", "procedure"]
TERM_COMPILER_VERSION = "terms-d2a"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_term_key(name: str) -> str:
    """Return the stable, locale-neutral key for a literal term spelling."""
    return re.sub(r"\s+", " ", name).strip().casefold()


def build_term_id(
    *,
    course_id: str,
    source_revision: str,
    knowledge_revision: str,
    canonical_key: str,
) -> str:
    payload = json.dumps(
        {
            "course_id": course_id,
            "source_revision": source_revision,
            "knowledge_revision": knowledge_revision,
            "canonical_key": canonical_key,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"term_{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class Term(BaseModel):
    """A deterministic term seed derived from current semantic Atoms only."""

    term_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1, max_length=160)
    canonical_key: str = Field(min_length=1, max_length=160)
    term_kind: TermKind
    definition: str = Field(min_length=1, max_length=1600)
    definition_atom_id: str = Field(min_length=1)
    supporting_atom_ids: list[str] = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(min_length=1)
    generation_method: Literal["rule"] = "rule"
    created_at: str = Field(default_factory=_utc_now)


class TermCompilation(BaseModel):
    """Immutable header for one full current Atom-to-Term projection."""

    course_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    knowledge_revision: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    term_count: int = Field(ge=0)
    rejected_atom_count: int = Field(ge=0)
    created_at: str = Field(default_factory=_utc_now)
