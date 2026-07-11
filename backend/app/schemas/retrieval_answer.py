"""Public, evidence-first contracts for V2 retrieval and answers.

These types deliberately describe only the boundary between retrieval and an
answering surface.  A ``RetrievalHit`` is already hydrated from a current
``SourceFragment``; it is not an untrusted Qdrant payload.  The answer
assembler can therefore turn a selected fragment ID into a citation without
accepting model-authored file names, locators, quotes, or revisions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.evidence import EvidenceRef
from app.schemas.foxsay import AnswerSource, ConfidenceStatus


RetrievalChannel = Literal["exact", "vector", "heading_neighborhood"]
RetrievalAvailability = Literal["available", "unavailable"]


class RetrievalError(BaseModel):
    """A visible retrieval failure that callers must not convert to no evidence."""

    error_code: str = Field(min_length=1)
    error_detail: str = Field(min_length=1)
    retriable: bool = False


class RetrievalWarning(BaseModel):
    """A non-fatal retrieval degradation, such as a failed vector fallback."""

    warning_code: str = Field(min_length=1)
    warning_detail: str = Field(min_length=1)


class RetrievalHit(BaseModel):
    """One canonical, course-scoped material hit allowed for this answer.

    ``canonical_text`` and every part of ``evidence`` must be hydrated from
    the current SQLite source-fragment boundary.  They are intentionally kept
    together so downstream callers cannot replace a real fragment's locator
    with a display-only value from a vector payload.
    """

    evidence: EvidenceRef
    file_name: str = Field(min_length=1)
    canonical_text: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    channels: list[RetrievalChannel] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_channels(self) -> "RetrievalHit":
        if len(self.channels) != len(set(self.channels)):
            raise ValueError("RetrievalHit channels must not contain duplicates")
        return self


class RetrievalOutcome(BaseModel):
    """The CRAG decision and canonical evidence made available to an answer.

    ``source_revision`` and ``knowledge_revision`` are opaque course-level
    revision values.  A hit's material revision remains on its ``EvidenceRef``
    so it cannot be confused with a course source-set revision.
    """

    course_id: str = Field(min_length=1)
    source_revision: str | None = None
    knowledge_revision: str | None = None
    # ``out_of_scope`` means retrieval completed and found no material
    # coverage.  ``None`` is reserved for a failed/unavailable retriever, so
    # clients never confuse an operational failure with a course boundary.
    retrieval_availability: RetrievalAvailability = "available"
    confidence: ConfidenceStatus | None = None
    relevance: float = Field(ge=0.0, le=1.0)
    coverage: float = Field(ge=0.0, le=1.0)
    hits: list[RetrievalHit] = Field(default_factory=list)
    error: RetrievalError | None = None
    warnings: list[RetrievalWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_canonical_hit_scope(self) -> "RetrievalOutcome":
        if self.retrieval_availability == "available":
            if self.confidence is None:
                raise ValueError("available RetrievalOutcome requires a confidence value")
            if self.error is not None:
                raise ValueError("available RetrievalOutcome must not contain a retrieval error")
        else:
            if self.confidence is not None:
                raise ValueError("unavailable RetrievalOutcome must set confidence to None")
            if self.error is None:
                raise ValueError("unavailable RetrievalOutcome requires a retrieval error")
            if self.hits:
                raise ValueError("unavailable RetrievalOutcome must not expose material hits")
            return self

        keys: set[tuple[str, str, str, int]] = set()
        fragment_ids: set[str] = set()
        for hit in self.hits:
            evidence = hit.evidence
            if evidence.course_id != self.course_id:
                raise ValueError("RetrievalHit evidence must belong to outcome course_id")
            if evidence.fragment_id in fragment_ids:
                raise ValueError("RetrievalOutcome hit fragment_ids must be unique")
            fragment_ids.add(evidence.fragment_id)
            key = (
                evidence.course_id,
                evidence.material_id,
                evidence.fragment_id,
                evidence.material_revision,
            )
            if key in keys:
                raise ValueError("RetrievalOutcome hits must not duplicate canonical evidence")
            keys.add(key)

        if self.confidence == "out_of_scope" and self.hits:
            raise ValueError("out_of_scope RetrievalOutcome must not expose material hits")
        if self.confidence in ("grounded", "ambiguous") and not self.hits:
            raise ValueError(
                "grounded and ambiguous RetrievalOutcome values require canonical material hits"
            )
        return self


class AnswerCitation(BaseModel):
    """A display and audit citation copied only from one canonical hit."""

    evidence: EvidenceRef
    file_name: str = Field(min_length=1)
    canonical_text: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    channels: list[RetrievalChannel] = Field(min_length=1)

    @classmethod
    def from_retrieval_hit(cls, hit: RetrievalHit) -> "AnswerCitation":
        """Create a citation without accepting model-provided evidence fields."""
        return cls(
            evidence=hit.evidence.model_copy(deep=True),
            file_name=hit.file_name,
            canonical_text=hit.canonical_text,
            score=hit.score,
            channels=list(hit.channels),
        )


class AnswerAssemblyWarning(BaseModel):
    """A non-fatal rejected citation selection retained for audit/debugging."""

    warning_code: Literal[
        "duplicate_citation_selection",
        "unknown_citation_selection",
        "fallback_to_allowed_evidence",
    ]
    fragment_id: str | None = Field(default=None, min_length=1)
    warning_detail: str = Field(min_length=1)


class AnswerEnvelope(BaseModel):
    """Server-assembled answer metadata suitable for an API response.

    Citation validity is established by ``assemble_answer_envelope``.  This
    model still protects the public contract from impossible CRAG/source
    combinations and accidental cross-course citation serialization.
    """

    course_id: str = Field(min_length=1)
    source_revision: str | None = None
    knowledge_revision: str | None = None
    answer: str
    retrieval_availability: RetrievalAvailability = "available"
    confidence_status: ConfidenceStatus | None = None
    answer_source: AnswerSource
    citations: list[AnswerCitation] = Field(default_factory=list)
    relevance: float = Field(ge=0.0, le=1.0)
    coverage: float = Field(ge=0.0, le=1.0)
    error: RetrievalError | None = None
    # Retrieval degradation (for example an unavailable vector channel) must
    # remain visible after answer assembly.  It is deliberately separate from
    # citation-selection warnings so callers can distinguish system state from
    # a model selecting an invalid fragment ID.
    retrieval_warnings: list[RetrievalWarning] = Field(default_factory=list)
    warnings: list[AnswerAssemblyWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_answer_boundary(self) -> "AnswerEnvelope":
        if self.retrieval_availability == "available":
            if self.confidence_status is None:
                raise ValueError("available AnswerEnvelope requires a confidence_status")
            if self.error is not None:
                raise ValueError("available AnswerEnvelope must not contain a retrieval error")
        else:
            if self.confidence_status is not None:
                raise ValueError("unavailable AnswerEnvelope must set confidence_status to None")
            if self.error is None:
                raise ValueError("unavailable AnswerEnvelope requires a retrieval error")
            if self.answer_source != "supplementary":
                raise ValueError("unavailable AnswerEnvelope must use answer_source='supplementary'")
            if self.citations:
                raise ValueError("unavailable AnswerEnvelope must not contain material citations")
            return self

        if self.confidence_status == "out_of_scope" and self.answer_source != "supplementary":
            raise ValueError("out_of_scope answers must use answer_source='supplementary'")
        if self.confidence_status == "out_of_scope" and self.citations:
            raise ValueError("out_of_scope answers must not contain material citations")
        if self.answer_source == "supplementary" and self.citations:
            raise ValueError("supplementary answers must not contain material citations")
        if self.answer_source == "material" and not self.citations:
            raise ValueError("material answers must contain at least one canonical citation")

        citation_keys: set[tuple[str, str, str, int]] = set()
        for citation in self.citations:
            evidence = citation.evidence
            if evidence.course_id != self.course_id:
                raise ValueError("AnswerCitation evidence must belong to envelope course_id")
            key = (
                evidence.course_id,
                evidence.material_id,
                evidence.fragment_id,
                evidence.material_revision,
            )
            if key in citation_keys:
                raise ValueError("AnswerEnvelope citations must not duplicate canonical evidence")
            citation_keys.add(key)
        return self
