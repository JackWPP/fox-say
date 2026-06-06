import re
from typing import Any


def _extract_entities(text: str) -> set[str]:
    """Extract potential concept entities from answer text."""
    # Match Chinese/English terms: 2-8 Chinese chars, or 2+ word English terms
    entities: set[str] = set()
    # Chinese concepts: 2-8 consecutive Chinese chars
    for match in re.finditer(r"[一-鿿]{2,8}", text):
        entities.add(match.group())
    # English terms: 1+ word sequences (letters only, at least 3 chars)
    for match in re.finditer(r"[A-Za-z]{3,}", text):
        entities.add(match.group().lower())
    return entities


def check_answer_in_scope(answer: str, course_id: str, store: Any) -> dict:
    """Post-answer guard: no-op in MVP (knowledge graph removed).

    Returns {in_scope: bool, overlap_count: int, warning: str|None}.
    Without a knowledge graph, there is nothing to compare entities against,
    so we cannot flag out-of-scope answers here. Primary in-scope gating
    happens upstream in the CRAG layer (retrieve() thresholds).
    """
    return {"in_scope": True, "overlap_count": 0, "warning": None}
