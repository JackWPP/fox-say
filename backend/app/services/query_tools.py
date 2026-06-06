"""Wiki 查询工具集。

每个函数都是 (course_id, ...) -> JSON 字符串, 供 LLM 工具调用。

HEC-6:所有入参都显式接收 course_id, 禁止反推。
HEC-1:出错时返回 JSON note, 不抛异常(LLM 需要看到结构化反馈)。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.schemas.foxsay import DMAP

logger = logging.getLogger(__name__)


def get_course_map(course_id: str, store: Any) -> str:
    """返回 course_index 全文(JSON 字符串)。course_index 是一段 markdown 摘要。"""
    content = store.get_course_index(course_id) if store else None
    if not content:
        return json.dumps({"note": "课程索引尚未生成"}, ensure_ascii=False)
    return content  # 已经是 markdown 字符串


def search_wiki(
    course_id: str,
    query: str,
    layer: str = "all",
    top_k: int = 5,
    store: Any = None,
) -> str:
    """三层混合检索统一入口。layer: macro/micro/all。"""
    if store is None:
        return json.dumps({"results": [], "count": 0, "note": "store not provided"}, ensure_ascii=False)
    # 本地 import 避免 retrieval -> query_tools 反向依赖
    from app.services.retrieval import search_wiki_layer
    results = search_wiki_layer(course_id, query, layer, top_k, store)
    return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False)


def get_concept(course_id: str, concept_id: str, store: Any) -> str:
    """根据 KC ID 拿完整知识卡内容。"""
    if store is None:
        return json.dumps({"note": "store not provided"}, ensure_ascii=False)
    kc = store.get_kc(concept_id)
    if kc is None:
        return json.dumps({"note": f"未找到概念 {concept_id}"}, ensure_ascii=False)
    # ★ 显式 course_id 校验 (HEC-6)
    if kc.course_id != course_id:
        return json.dumps({"note": f"概念 {concept_id} 不属于课程 {course_id}"}, ensure_ascii=False)
    return json.dumps(kc.model_dump(), ensure_ascii=False)


def get_chapter_outline(course_id: str, chapter_id: str, store: Any) -> str:
    """返回章节摘要。"""
    if store is None:
        return json.dumps({"note": "store not provided"}, ensure_ascii=False)
    cw = store.get_chapter_wiki(chapter_id)
    if cw is None:
        return json.dumps({"note": f"未找到章节 {chapter_id}"}, ensure_ascii=False)
    if cw.course_id != course_id:
        return json.dumps({"note": f"章节 {chapter_id} 不属于课程 {course_id}"}, ensure_ascii=False)
    return json.dumps(cw.model_dump(), ensure_ascii=False)


def follow_prerequisite(
    course_id: str,
    concept_id: str,
    depth: int = 2,
    store: Any = None,
) -> str:
    """沿 KC.prerequisites 链向上回溯。

    算法:BFS, 沿 KC.prerequisites 名字模糊搜同课程内的 KC, 防止 cycle。
    """
    if store is None:
        return json.dumps({"prerequisites": []}, ensure_ascii=False)
    visited: set[str] = {concept_id}
    queue: list[tuple[str, int]] = [(concept_id, 0)]
    found: list[dict] = []
    while queue:
        current_id, d = queue.pop(0)
        if d >= depth:
            continue
        current = store.get_kc(current_id)
        if current is None:
            continue
        for prereq_name in current.prerequisites:
            candidates = store.search_kcs_by_name(course_id, prereq_name)
            for c in candidates[:1]:
                if c.id not in visited and c.course_id == course_id:
                    visited.add(c.id)
                    found.append(c.model_dump())
                    queue.append((c.id, d + 1))
                    break
    return json.dumps({"prerequisites": found}, ensure_ascii=False)


def get_source_content(course_id: str, dmap_id: str, store: Any) -> str:
    """通过 DMAP 节点 / 元素 ID 拿原始材料片段。"""
    if store is None:
        return json.dumps({"note": "store not provided"}, ensure_ascii=False)
    dmap_json = store.get_dmap(course_id)
    if not dmap_json:
        return json.dumps({"note": "DMAP 未找到"}, ensure_ascii=False)
    try:
        dmap = DMAP.model_validate_json(dmap_json)
    except Exception:
        return json.dumps({"note": "DMAP 解析失败"}, ensure_ascii=False)
    # dmap.py 提供的按 ID 查找辅助
    from app.services.dmap import get_dmap_node_by_id, get_dmap_element_by_id
    node = get_dmap_node_by_id(dmap, dmap_id)
    if node:
        parts = [node.title] + [e.text_preview for e in node.elements]
        return json.dumps(
            {"dmap_id": dmap_id, "content": "\n".join(parts), "type": "node"},
            ensure_ascii=False,
        )
    elem = get_dmap_element_by_id(dmap, dmap_id)
    if elem:
        return json.dumps(
            {"dmap_id": dmap_id, "content": elem.text_preview, "type": elem.type},
            ensure_ascii=False,
        )
    return json.dumps({"note": f"DMAP 节点 {dmap_id} 未找到"}, ensure_ascii=False)
