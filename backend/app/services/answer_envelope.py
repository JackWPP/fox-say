"""Pure server-side assembly of V2 answer citations.

This module intentionally does not call a model, a database, a vector store,
or a network service.  Retrieval has already hydrated canonical hits from the
current source-fragment boundary.  The only citation input accepted here is a
fragment ID selected from that bounded set.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.schemas.foxsay import AnswerSource
from app.schemas.retrieval_answer import (
    AnswerAssemblyWarning,
    AnswerCitation,
    AnswerEnvelope,
    RetrievalOutcome,
)


def assemble_answer_envelope(
    outcome: RetrievalOutcome,
    *,
    answer: str,
    citation_fragment_ids: Iterable[object] | None = (),
    answer_source: AnswerSource | None = None,
) -> AnswerEnvelope:
    """Build an answer envelope using only canonical evidence from ``outcome``.

    Unknown, duplicate, stale, cross-course, or otherwise forged selections
    cannot enter the output because callers submit opaque fragment IDs only.
    They are discarded rather than failing the whole answer, while a
    structured warning retains the reason for audit.  If a material answer
    has no valid selection left, the full allowed evidence pack is used so a
    grounded/ambiguous answer never becomes an uncited material claim.
    ``out_of_scope`` and supplementary answers always omit material citations.
    """

    resolved_source = answer_source or _default_answer_source(outcome)
    if (
        outcome.retrieval_availability == "unavailable"
        or outcome.confidence == "out_of_scope"
    ):
        resolved_source = "supplementary"

    if resolved_source == "supplementary":
        return _build_envelope(
            outcome,
            answer=answer,
            answer_source=resolved_source,
            citations=[],
            warnings=[],
        )

    allowed_by_fragment_id = {
        hit.evidence.fragment_id: hit
        for hit in outcome.hits
    }
    citations: list[AnswerCitation] = []
    warnings: list[AnswerAssemblyWarning] = []
    selected_ids: set[str] = set()

    for raw_fragment_id in _iter_citation_selections(citation_fragment_ids):
        fragment_id = _normalize_fragment_id(raw_fragment_id)
        if fragment_id is None:
            warnings.append(
                AnswerAssemblyWarning(
                    warning_code="unknown_citation_selection",
                    warning_detail="Citation selection must be a non-blank string fragment ID",
                )
            )
            continue
        if fragment_id in selected_ids:
            warnings.append(
                AnswerAssemblyWarning(
                    warning_code="duplicate_citation_selection",
                    fragment_id=fragment_id,
                    warning_detail="Duplicate citation selection was discarded",
                )
            )
            continue
        selected_ids.add(fragment_id)

        hit = allowed_by_fragment_id.get(fragment_id)
        if hit is None:
            warnings.append(
                AnswerAssemblyWarning(
                    warning_code="unknown_citation_selection",
                    fragment_id=fragment_id,
                    warning_detail=(
                        "Citation selection is not an allowed canonical hit for this outcome"
                    ),
                )
            )
            continue
        citations.append(AnswerCitation.from_retrieval_hit(hit))

    if not citations:
        if not outcome.hits:
            raise ValueError(
                "material answer assembly requires at least one allowed canonical RetrievalHit"
            )
        citations = [AnswerCitation.from_retrieval_hit(hit) for hit in outcome.hits]
        warnings.append(
            AnswerAssemblyWarning(
                warning_code="fallback_to_allowed_evidence",
                warning_detail=(
                    "No valid citation selection remained; all allowed canonical evidence was used"
                ),
            )
        )

    return _build_envelope(
        outcome,
        answer=answer,
        answer_source=resolved_source,
        citations=citations,
        warnings=warnings,
    )


def _default_answer_source(outcome: RetrievalOutcome) -> AnswerSource:
    if outcome.retrieval_availability == "unavailable" or outcome.confidence == "out_of_scope":
        return "supplementary"
    return "material"


def _iter_citation_selections(
    selections: Iterable[object] | None,
) -> Iterable[object]:
    """Treat malformed selection containers as one rejected selection.

    An LLM integration can accidentally provide ``None``, a scalar, or a raw
    string instead of a JSON list.  Keeping this boundary defensive ensures a
    single malformed citation request cannot fail an otherwise valid answer.
    """
    if selections is None:
        return ()
    if isinstance(selections, str):
        return (selections,)
    try:
        iter(selections)
    except TypeError:
        return (selections,)
    return selections


def _normalize_fragment_id(selection: object) -> str | None:
    """Return an opaque usable fragment ID, or ``None`` for invalid input."""
    if not isinstance(selection, str):
        return None
    normalized = selection.strip()
    return normalized or None


def _build_envelope(
    outcome: RetrievalOutcome,
    *,
    answer: str,
    answer_source: AnswerSource,
    citations: list[AnswerCitation],
    warnings: list[AnswerAssemblyWarning],
) -> AnswerEnvelope:
    return AnswerEnvelope(
        course_id=outcome.course_id,
        source_revision=outcome.source_revision,
        knowledge_revision=outcome.knowledge_revision,
        answer=answer,
        retrieval_availability=outcome.retrieval_availability,
        confidence_status=outcome.confidence,
        answer_source=answer_source,
        citations=citations,
        relevance=outcome.relevance,
        coverage=outcome.coverage,
        error=outcome.error,
        retrieval_warnings=list(outcome.warnings),
        warnings=warnings,
    )
