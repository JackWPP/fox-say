import re
from typing import Any

from app.services.knowledge_graph import KnowledgeGraph


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
    """Post-answer guard: check if answer entities overlap with course knowledge.

    Returns {in_scope: bool, overlap_count: int, warning: str|None}.
    This is a safety net, not a primary gate — it only flags clear violations.
    """
    entities = _extract_entities(answer)
    if not entities:
        return {"in_scope": True, "overlap_count": 0, "warning": None}

    kg = KnowledgeGraph.for_course(course_id, store=store)
    if kg.get_concept_count() == 0:
        # No graph built yet, can't verify — allow through
        return {"in_scope": True, "overlap_count": 0, "warning": None}

    # Check overlap with knowledge graph concepts
    graph_concepts: set[str] = set()
    for node_id in kg._graph.nodes:
        label = str(kg._graph.nodes[node_id].get("label", node_id)).lower()
        graph_concepts.add(label)

    overlap = 0
    for entity in entities:
        entity_lower = entity.lower()
        for gc in graph_concepts:
            if entity_lower in gc or gc in entity_lower:
                overlap += 1
                break

    # If zero overlap and answer is substantial, flag it
    if overlap == 0 and len(entities) >= 3:
        return {
            "in_scope": False,
            "overlap_count": 0,
            "warning": "答案中的关键概念未在课程知识图谱中找到匹配，可能超出课程范围",
        }

    return {"in_scope": True, "overlap_count": overlap, "warning": None}
