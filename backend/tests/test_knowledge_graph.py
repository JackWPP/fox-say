"""Knowledge graph API 单元测试。

覆盖:
- 课程不存在 → 404
- 课程存在但 KC=0 → 空 graph
- 节点来自 KCs (含 mastery=0.0, importance 来自 exam_frequency)
- 边优先用结构化 prerequisites;fallback 用 prerequisites_raw 模糊匹配
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.schemas.foxsay import KC, KCPrerequisite


# ---------------------------------------------------------------------------
# Tests (使用 conftest.py 的 client fixture,直接写 SqliteStore,不需要 mock)
# ---------------------------------------------------------------------------


def _make_kc(
    kc_id: str,
    course_id: str,
    name: str,
    exam_frequency: str = "medium",
    cognitive_dimension: str = "conceptual",
    chapter_id: str = "",
    prerequisites: list[KCPrerequisite] | None = None,
    prerequisites_raw: list[str] | None = None,
) -> KC:
    return KC(
        id=kc_id,
        course_id=course_id,
        name=name,
        exam_frequency=exam_frequency,
        cognitive_dimension=cognitive_dimension,  # type: ignore[arg-type]
        chapter_id=chapter_id,
        prerequisites=prerequisites or [],
        prerequisites_raw=prerequisites_raw or [],
    )


@pytest.mark.asyncio
async def test_kg_course_not_found(client: AsyncClient):
    """GET 未知 course_id → 404。"""
    resp = await client.get("/courses/does-not-exist/knowledge-graph")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_kg_empty_course_returns_empty_graph(client: AsyncClient):
    """课程存在但 KC=0 → nodes=[],edges=[]。"""
    create = await client.post("/courses", json={"title": "空课"})
    assert create.status_code == 200

    course_id = create.json()["id"]
    resp = await client.get(f"/courses/{course_id}/knowledge-graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_id"] == course_id
    assert data["nodes"] == []
    assert data["edges"] == []
    assert data["layout_hint"] == "dagre"


@pytest.mark.asyncio
async def test_kg_nodes_from_kcs(client: AsyncClient):
    """节点 = KCs 列表;mastery=0.0;importance 来自 exam_frequency。"""
    create = await client.post("/courses", json={"title": "线代"})
    course_id = create.json()["id"]

    from app.main import app
    store = app.state.store  # type: ignore[assignment]

    kc_hi = _make_kc(
        kc_id="kc-hi", course_id=course_id, name="矩阵乘法",
        exam_frequency="high", cognitive_dimension="procedural_skill",
        chapter_id="ch1",
    )
    kc_lo = _make_kc(
        kc_id="kc-lo", course_id=course_id, name="历史背景",
        exam_frequency="low", cognitive_dimension="factual",
        chapter_id="ch0",
    )
    store.save_kc(kc_hi)
    store.save_kc(kc_lo)

    resp = await client.get(f"/courses/{course_id}/knowledge-graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_id"] == course_id
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 0

    by_id = {n["id"]: n for n in data["nodes"]}
    assert by_id["kc-hi"]["label"] == "矩阵乘法"
    assert by_id["kc-hi"]["importance"] == "high"
    assert by_id["kc-hi"]["mastery"] == 0.0
    assert by_id["kc-hi"]["cognitive_dimension"] == "procedural_skill"
    assert by_id["kc-hi"]["chapter_id"] == "ch1"

    assert by_id["kc-lo"]["importance"] == "low"
    assert by_id["kc-lo"]["cognitive_dimension"] == "factual"
    assert by_id["kc-lo"]["chapter_id"] == "ch0"


@pytest.mark.asyncio
async def test_kg_edges_new_structure_priority(client: AsyncClient):
    """结构化 prerequisites 优先,生成 KGEdge;fallback 用 raw 模糊匹配。"""
    create = await client.post("/courses", json={"title": "高数"})
    course_id = create.json()["id"]

    from app.main import app
    store = app.state.store  # type: ignore[assignment]

    a = _make_kc(kc_id="kc-a", course_id=course_id, name="A")
    b = _make_kc(
        kc_id="kc-b", course_id=course_id, name="B",
        prerequisites=[KCPrerequisite(prerequisite_kc_id="kc-a", dependency_strength=0.8)],
    )
    x = _make_kc(kc_id="kc-x", course_id=course_id, name="X is the variable")
    c = _make_kc(
        kc_id="kc-c", course_id=course_id, name="C",
        prerequisites_raw=["X is the variable"],
    )
    # 自环:prereq 是自己
    d = _make_kc(
        kc_id="kc-d", course_id=course_id, name="D",
        prerequisites=[KCPrerequisite(prerequisite_kc_id="kc-d", dependency_strength=1.0)],
    )
    # raw 指向不存在的名字
    e = _make_kc(
        kc_id="kc-e", course_id=course_id, name="E",
        prerequisites_raw=["nonexistent-thing"],
    )

    for kc in (a, b, x, c, d, e):
        store.save_kc(kc)

    resp = await client.get(f"/courses/{course_id}/knowledge-graph")
    assert resp.status_code == 200
    data = resp.json()
    edges = data["edges"]
    edge_map = {(e["source"], e["target"]): e for e in edges}

    # 结构化边 (a -> b, strength=0.8)
    assert ("kc-a", "kc-b") in edge_map
    assert edge_map[("kc-a", "kc-b")]["strength"] == 0.8
    assert edge_map[("kc-a", "kc-b")]["edge_type"] == "prerequisite"

    # fallback 边 (x -> c, strength=0.5)
    assert ("kc-x", "kc-c") in edge_map
    assert edge_map[("kc-x", "kc-c")]["strength"] == 0.5

    # 自环被跳过
    assert ("kc-d", "kc-d") not in edge_map
    # 找不到的 raw 不产生边
    assert not any(e["source"] == "kc-e" or e["target"] == "kc-e" for e in edges)

    # 节点齐 6 个
    assert len(data["nodes"]) == 6
