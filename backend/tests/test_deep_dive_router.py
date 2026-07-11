"""Unit tests for the deep-dive trigger router.

Tests cover keyword matching (Chinese + English), workflow_hint overrides,
retrieval-based triggers (ambiguous + multi-material), and negative cases.
No model calls, no database, no network – pure function tests.
"""

from __future__ import annotations

from app.schemas.evidence import EvidenceRef
from app.schemas.foxsay import ConfidenceStatus
from app.schemas.retrieval_answer import RetrievalHit, RetrievalOutcome
from app.services.deep_dive_router import should_use_deep_dive


def _hit(fragment_id: str, material_id: str, score: float = 0.85) -> RetrievalHit:
    return RetrievalHit(
        evidence=EvidenceRef(
            course_id="c1",
            material_id=material_id,
            fragment_id=fragment_id,
            material_revision=1,
            locator=f"sec/{material_id}",
        ),
        file_name=f"{material_id}.md",
        canonical_text="some text",
        score=score,
        channels=["exact"],
    )


def _outcome(
    *,
    confidence: ConfidenceStatus = "grounded",
    hits: list[RetrievalHit] | None = None,
) -> RetrievalOutcome:
    if hits is None:
        hits = [_hit("frag-1", "mat-1")]
    return RetrievalOutcome(
        course_id="c1",
        confidence=confidence,
        relevance=0.85,
        coverage=0.5,
        hits=hits,
    )


# -- workflow_hint overrides ------------------------------------------------


def test_workflow_hint_deep_dive_forces_deep_dive() -> None:
    assert should_use_deep_dive("什么是特征值", workflow_hint="deep_dive") is True


def test_workflow_hint_quick_answer_forces_quick_answer() -> None:
    # Even with a keyword trigger, quick_answer hint wins.
    assert should_use_deep_dive("线性无关和满秩的关系", workflow_hint="quick_answer") is False


def test_workflow_hint_auto_uses_keyword_matching() -> None:
    assert should_use_deep_dive("线性无关和满秩的关系", workflow_hint="auto") is True


# -- Chinese keyword triggers ------------------------------------------------


def test_chinese_cross_chapter_keyword_triggers() -> None:
    assert should_use_deep_dive("线性无关和满秩之间是什么关系") is True


def test_chinese_comparison_keyword_triggers() -> None:
    assert should_use_deep_dive("矩阵和向量的区别是什么") is True


def test_chinese_system_keyword_triggers() -> None:
    assert should_use_deep_dive("总结一下整个体系") is True


def test_chinese_how_related_keyword_triggers() -> None:
    assert should_use_deep_dive("这两个概念有什么关系") is True


def test_chinese_contrast_keyword_triggers() -> None:
    assert should_use_deep_dive("两种方法对比一下") is True


# -- English keyword triggers ------------------------------------------------


def test_english_relationship_keyword_triggers() -> None:
    assert should_use_deep_dive("What is the relationship between A and B?") is True


def test_english_compare_keyword_triggers() -> None:
    assert should_use_deep_dive("Compare these two methods") is True


def test_english_vs_keyword_triggers() -> None:
    assert should_use_deep_dive("SVM vs Random Forest") is True


def test_english_how_are_related_regex_triggers() -> None:
    assert should_use_deep_dive("How are linear independence and rank related?") is True


def test_english_framework_keyword_triggers() -> None:
    assert should_use_deep_dive("Give me an overview of the framework") is True


# -- Negative cases (no trigger) --------------------------------------------


def test_simple_question_does_not_trigger() -> None:
    assert should_use_deep_dive("什么是特征值？") is False


def test_definition_question_does_not_trigger() -> None:
    assert should_use_deep_dive("请解释一下向量空间的概念") is False


def test_empty_query_does_not_trigger() -> None:
    assert should_use_deep_dive("") is False


# -- Retrieval-based triggers ------------------------------------------------


def test_ambiguous_with_multi_material_hits_triggers() -> None:
    outcome = _outcome(
        confidence="ambiguous",
        hits=[
            _hit("frag-1", "mat-a", score=0.62),
            _hit("frag-2", "mat-b", score=0.60),
        ],
    )
    assert should_use_deep_dive("请解释这个概念", outcome) is True


def test_ambiguous_with_single_material_does_not_trigger() -> None:
    outcome = _outcome(
        confidence="ambiguous",
        hits=[
            _hit("frag-1", "mat-a", score=0.62),
            _hit("frag-2", "mat-a", score=0.60),
        ],
    )
    assert should_use_deep_dive("请解释这个概念", outcome) is False


def test_grounded_with_multi_material_does_not_trigger_via_retrieval() -> None:
    # Grounded confidence doesn't trigger the retrieval-based path.
    outcome = _outcome(
        confidence="grounded",
        hits=[
            _hit("frag-1", "mat-a"),
            _hit("frag-2", "mat-b"),
        ],
    )
    assert should_use_deep_dive("请解释这个概念", outcome) is False


def test_out_of_scope_does_not_trigger_via_retrieval() -> None:
    outcome = RetrievalOutcome(
        course_id="c1",
        confidence="out_of_scope",
        relevance=0.3,
        coverage=0.0,
        hits=[],
    )
    assert should_use_deep_dive("请解释这个概念", outcome) is False


def test_no_retrieval_outcome_means_keyword_only() -> None:
    # Without a retrieval outcome, only keywords can trigger.
    assert should_use_deep_dive("请解释这个概念", None) is False
    assert should_use_deep_dive("A和B的关系", None) is True
