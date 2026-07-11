"""V2 answer-envelope contract tests.

The tests use synthetic linear-algebra evidence only.  They intentionally
exercise the pure assembler rather than an LLM, Qdrant, or SQLite.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.evidence import EvidenceRef
from app.schemas.retrieval_answer import (
    AnswerCitation,
    AnswerEnvelope,
    RetrievalHit,
    RetrievalOutcome,
    RetrievalWarning,
)
from app.services.answer_envelope import assemble_answer_envelope


def _hit(
    *,
    course_id: str = "linear-algebra",
    material_id: str = "lecture-01",
    fragment_id: str = "la-r2-eigenvalue-definition",
    material_revision: int = 2,
) -> RetrievalHit:
    return RetrievalHit(
        evidence=EvidenceRef(
            course_id=course_id,
            material_id=material_id,
            fragment_id=fragment_id,
            material_revision=material_revision,
            locator="第二章 > 特征值；p.12",
        ),
        file_name="线性代数讲义.pdf",
        canonical_text="若 Av = λv 且 v 非零，则 λ 是 A 的特征值。",
        score=0.91,
        channels=["exact", "vector"],
    )


def _outcome(*, hits: list[RetrievalHit] | None = None) -> RetrievalOutcome:
    return RetrievalOutcome(
        course_id="linear-algebra",
        source_revision="source-r2",
        knowledge_revision=None,
        confidence="grounded",
        relevance=0.91,
        coverage=0.5,
        hits=hits if hits is not None else [_hit()],
    )


def test_assembler_rehydrates_only_allowed_canonical_hits_and_drops_forged_selection():
    outcome = _outcome()

    envelope = assemble_answer_envelope(
        outcome,
        answer="特征值由方程 Av = λv（v 非零）定义。",
        citation_fragment_ids=["la-r2-eigenvalue-definition", "forged-fragment-r999"],
    )

    assert envelope.answer_source == "material"
    assert len(envelope.citations) == 1
    citation = envelope.citations[0]
    assert citation.evidence.fragment_id == "la-r2-eigenvalue-definition"
    assert citation.evidence.material_revision == 2
    assert citation.file_name == "线性代数讲义.pdf"
    assert citation.canonical_text == "若 Av = λv 且 v 非零，则 λ 是 A 的特征值。"
    assert [warning.fragment_id for warning in envelope.warnings] == ["forged-fragment-r999"]
    assert envelope.warnings[0].warning_code == "unknown_citation_selection"


def test_out_of_scope_and_supplementary_answers_force_no_material_citations():
    outcome = RetrievalOutcome(
        course_id="linear-algebra",
        source_revision="source-r2",
        knowledge_revision=None,
        confidence="out_of_scope",
        relevance=0.12,
        coverage=0.0,
    )

    envelope = assemble_answer_envelope(
        outcome,
        answer="课程材料没有覆盖这个概念；以下是通用理解。",
        citation_fragment_ids=["forged-fragment-r999"],
        answer_source="material",
    )

    assert envelope.confidence_status == "out_of_scope"
    assert envelope.answer_source == "supplementary"
    assert envelope.citations == []
    assert envelope.warnings == []

    supplementary = assemble_answer_envelope(
        _outcome(),
        answer="这是与课程材料分开的补充说明。",
        citation_fragment_ids=["la-r2-eigenvalue-definition"],
        answer_source="supplementary",
    )
    assert supplementary.citations == []

    with pytest.raises(ValidationError, match="supplementary answers must not contain material citations"):
        AnswerEnvelope(
            course_id="linear-algebra",
            source_revision="source-r2",
            knowledge_revision=None,
            answer="不应有材料引用",
            confidence_status="grounded",
            answer_source="supplementary",
            citations=[AnswerCitation.from_retrieval_hit(_hit())],
            relevance=0.9,
            coverage=0.5,
        )

    with pytest.raises(ValidationError, match="must contain at least one canonical citation"):
        AnswerEnvelope(
            course_id="linear-algebra",
            source_revision="source-r2",
            knowledge_revision=None,
            answer="材料回答不能无引用。",
            confidence_status="grounded",
            answer_source="material",
            relevance=0.9,
            coverage=0.5,
        )


def test_outcome_and_envelope_reject_cross_course_evidence():
    with pytest.raises(ValidationError, match="must belong to outcome course_id"):
        _outcome(hits=[_hit(course_id="calculus")])

    with pytest.raises(ValidationError, match="must belong to envelope course_id"):
        AnswerEnvelope(
            course_id="linear-algebra",
            source_revision="source-r2",
            knowledge_revision=None,
            answer="跨课程引用必须拒绝。",
            confidence_status="grounded",
            answer_source="material",
            citations=[AnswerCitation.from_retrieval_hit(_hit(course_id="calculus"))],
            relevance=0.9,
            coverage=0.5,
        )


def test_revision_scoped_selection_uses_current_canonical_hit_and_rejects_old_fragment():
    current = _hit(fragment_id="la-r2-eigenvalue-definition", material_revision=2)
    outcome = _outcome(hits=[current])

    envelope = assemble_answer_envelope(
        outcome,
        answer="当前 revision 的定义。",
        citation_fragment_ids=["la-r1-eigenvalue-definition", "la-r2-eigenvalue-definition"],
    )

    assert [citation.evidence.material_revision for citation in envelope.citations] == [2]
    assert [citation.evidence.fragment_id for citation in envelope.citations] == [
        "la-r2-eigenvalue-definition"
    ]
    assert envelope.warnings[0].warning_code == "unknown_citation_selection"
    assert envelope.warnings[0].fragment_id == "la-r1-eigenvalue-definition"


def test_invalid_material_selection_falls_back_to_the_allowed_evidence_pack():
    envelope = assemble_answer_envelope(
        _outcome(),
        answer="特征值定义见课程材料。",
        citation_fragment_ids=["forged-fragment-r999"],
    )

    assert [citation.evidence.fragment_id for citation in envelope.citations] == [
        "la-r2-eigenvalue-definition"
    ]
    assert [warning.warning_code for warning in envelope.warnings] == [
        "unknown_citation_selection",
        "fallback_to_allowed_evidence",
    ]


def test_blank_and_non_string_selections_are_dropped_without_failing_the_answer():
    envelope = assemble_answer_envelope(
        _outcome(),
        answer="特征值定义见课程材料。",
        citation_fragment_ids=["", "  ", None, 7, " la-r2-eigenvalue-definition "],
    )

    assert [citation.evidence.fragment_id for citation in envelope.citations] == [
        "la-r2-eigenvalue-definition"
    ]
    assert [warning.warning_code for warning in envelope.warnings] == [
        "unknown_citation_selection",
        "unknown_citation_selection",
        "unknown_citation_selection",
        "unknown_citation_selection",
    ]
    assert [warning.fragment_id for warning in envelope.warnings] == [None, None, None, None]


def test_all_invalid_selections_fall_back_without_raising():
    envelope = assemble_answer_envelope(
        _outcome(),
        answer="特征值定义见课程材料。",
        citation_fragment_ids=["", None, 7],
    )

    assert [citation.evidence.fragment_id for citation in envelope.citations] == [
        "la-r2-eigenvalue-definition"
    ]
    assert [warning.warning_code for warning in envelope.warnings] == [
        "unknown_citation_selection",
        "unknown_citation_selection",
        "unknown_citation_selection",
        "fallback_to_allowed_evidence",
    ]
    assert envelope.warnings[-1].fragment_id is None


def test_assembler_preserves_retrieval_degradation_warnings_separately():
    outcome = _outcome()
    outcome.warnings = [
        RetrievalWarning(
            warning_code="vector_unavailable",
            warning_detail="Exact retrieval succeeded but vector search timed out",
        )
    ]

    envelope = assemble_answer_envelope(
        outcome,
        answer="特征值定义见课程材料。",
        citation_fragment_ids=["la-r2-eigenvalue-definition"],
    )

    assert envelope.warnings == []
    assert envelope.retrieval_warnings == outcome.warnings
    assert envelope.retrieval_warnings[0].warning_code == "vector_unavailable"


@pytest.mark.parametrize("confidence", ["grounded", "ambiguous"])
def test_high_confidence_outcomes_require_canonical_hits(confidence: str):
    with pytest.raises(ValidationError, match="require canonical material hits"):
        RetrievalOutcome(
            course_id="linear-algebra",
            source_revision="source-r2",
            knowledge_revision=None,
            confidence=confidence,
            relevance=0.8,
            coverage=0.5,
        )


def test_out_of_scope_outcome_cannot_expose_material_hits():
    with pytest.raises(ValidationError, match="must not expose material hits"):
        RetrievalOutcome(
            course_id="linear-algebra",
            source_revision="source-r2",
            knowledge_revision=None,
            confidence="out_of_scope",
            relevance=0.1,
            coverage=0.0,
            hits=[_hit()],
        )
