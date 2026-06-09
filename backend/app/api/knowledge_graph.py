"""Knowledge graph API (line C — MVP).

GET /courses/{course_id}/knowledge-graph
  → KnowledgeGraphResponse { course_id, nodes, edges, layout_hint }

节点来自 store.get_kcs_by_course;边优先用结构化 prerequisites
(KCPrerequisite.prerequisite_kc_id),fallback 用 prerequisites_raw
的字符串名经 store.search_kcs_by_name 模糊匹配。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import (
    KGEdge,
    KGNode,
    KnowledgeGraphResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses")


def _kc_to_node(kc) -> KGNode:
    """Importance 来自 exam_frequency;mastery 一期固定 0.0。"""
    importance = "high" if kc.exam_frequency == "high" else (
        "low" if kc.exam_frequency == "low" else "medium"
    )
    return KGNode(
        id=kc.id,
        label=kc.name,
        chapter_id=kc.chapter_id,
        mastery=0.0,
        importance=importance,
        cognitive_dimension=kc.cognitive_dimension,
    )


def _build_edges(kcs, store: SqliteStore, course_id: str) -> list[KGEdge]:
    """优先 KC.prerequisites 结构化;fallback prerequisites_raw 模糊匹配。

    跳过:自环(source == target)、跨课程(prereq 课程与当前不一致)、
    找不到的 raw 字符串。
    """
    valid_ids = {kc.id for kc in kcs}
    edges: list[KGEdge] = []
    seen: set[tuple[str, str]] = set()

    for kc in kcs:
        # 1. 优先结构化 prerequisites
        if kc.prerequisites:
            for prereq in kc.prerequisites:
                src = prereq.prerequisite_kc_id
                if src == kc.id:
                    continue  # 自环
                if src not in valid_ids:
                    continue  # 跨课程或不存在
                key = (src, kc.id)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(KGEdge(
                    source=src,
                    target=kc.id,
                    strength=prereq.dependency_strength,
                    edge_type="prerequisite",
                ))
            continue  # 已有结构化,不再走 raw fallback

        # 2. Fallback: prerequisites_raw 模糊匹配
        for raw_name in kc.prerequisites_raw:
            matches = store.search_kcs_by_name(course_id, raw_name)
            if not matches:
                continue
            prereq_kc = matches[0]
            if prereq_kc.id == kc.id:
                continue  # 自环
            if prereq_kc.id not in valid_ids:
                continue
            key = (prereq_kc.id, kc.id)
            if key in seen:
                continue
            seen.add(key)
            edges.append(KGEdge(
                source=prereq_kc.id,
                target=kc.id,
                strength=0.5,
                edge_type="prerequisite",
            ))

    return edges


@router.get("/{course_id}/knowledge-graph", response_model=KnowledgeGraphResponse)
async def get_knowledge_graph(
    course_id: str, store: SqliteStore = Depends(get_store)
) -> KnowledgeGraphResponse:
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    kcs = store.get_kcs_by_course(course_id, include_invalid=False)
    if not kcs:
        return KnowledgeGraphResponse(
            course_id=course_id, nodes=[], edges=[], layout_hint="dagre"
        )

    nodes = [_kc_to_node(kc) for kc in kcs]
    edges = _build_edges(kcs, store, course_id)

    return KnowledgeGraphResponse(
        course_id=course_id, nodes=nodes, edges=edges, layout_hint="dagre"
    )
