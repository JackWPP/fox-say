"""Deterministic deep-dive trigger logic.

Decides whether a student question should route to :class:`DeepDiveService`
(cross-chapter analysis) instead of :class:`QuickAnswerService` (single-shot).

The trigger is **course-agnostic** and uses no model calls.  Three signals are
consulted, in priority order:

1. ``workflow_hint`` override – ``"deep_dive"`` forces deep-dive,
   ``"quick_answer"`` forces single-shot.
2. Keyword matching – the query contains cross-chapter / comparison patterns.
3. Retrieval-based trigger – ``confidence == "ambiguous"`` **and** the hits
   span ≥2 distinct ``material_id`` values (MVP proxy for multi-section).

Only one signal needs to fire for deep-dive to be selected.  The keyword list
is a module-level constant because it changes with product requirements, not
runtime configuration.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.retrieval_answer import RetrievalOutcome

# -- Trigger keywords -------------------------------------------------------
#
# Chinese keywords are matched as substrings after NFKC + casefold.
# English keywords are matched as substrings after NFKC + casefold.
# Regex patterns handle multi-word English phrases like "how are ... related".

_KEYWORDS_ZH: tuple[str, ...] = (
    # Cross-chapter relationship
    "之间", "关系", "联系", "关联", "跨章节",
    # Comparison
    "区别", "比较", "对比", "异同", "相比",
    # System / composite
    "体系", "系统", "框架", "整体", "总结",
    # How related
    "有什么关系", "如何联系", "怎样关联",
)

_KEYWORDS_EN: tuple[str, ...] = (
    # Cross-chapter relationship
    "relationship", "connection", "across chapter",
    # Comparison
    "difference", "compare", "versus", "vs",
    # System / composite
    "system", "framework", "overview", "summary",
    # How related
    "relation between",
)

_REGEX_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"how\s+are\s+.*\brelated\b", re.IGNORECASE),
)


def _normalize_query(query: str) -> str:
    """Apply Unicode NFKC normalization and casefolding."""
    return unicodedata.normalize("NFKC", query).casefold()


def _keyword_matches(normalized: str) -> bool:
    """Return True if any deep-dive keyword is present in the normalized query."""
    for keyword in _KEYWORDS_ZH:
        if keyword in normalized:
            return True
    for keyword in _KEYWORDS_EN:
        if keyword.casefold() in normalized:
            return True
    for pattern in _REGEX_PATTERNS:
        if pattern.search(normalized):
            return True
    return False


def _count_distinct_material_ids(outcome: RetrievalOutcome) -> int:
    """Count distinct material_id values among retrieval hits.

    For MVP, material diversity is used as a proxy for multi-section diversity
    (see architecture doc §4.4: "For MVP, checking material_id diversity is
    sufficient").
    """
    return len({hit.evidence.material_id for hit in outcome.hits})


def should_use_deep_dive(
    query: str,
    retrieval_outcome: RetrievalOutcome | None = None,
    workflow_hint: str = "auto",
) -> bool:
    """Decide whether a question should use the deep-dive workflow.

    Parameters
    ----------
    query:
        The student's question text.
    retrieval_outcome:
        Optional.  When provided, enables the retrieval-based trigger
        (ambiguous confidence + multi-material hits).
    workflow_hint:
        ``"auto"`` (default), ``"quick_answer"``, or ``"deep_dive"``.
        An explicit hint always overrides the server heuristic.
    """
    # 1. Explicit overrides always win.
    if workflow_hint == "deep_dive":
        return True
    if workflow_hint == "quick_answer":
        return False

    # 2. Keyword-based trigger (deterministic, no model call).
    normalized = _normalize_query(query)
    if _keyword_matches(normalized):
        return True

    # 3. Retrieval-based trigger (only when caller provides an outcome).
    if retrieval_outcome is not None:
        if (
            retrieval_outcome.confidence == "ambiguous"
            and _count_distinct_material_ids(retrieval_outcome) >= 2
        ):
            return True

    return False
