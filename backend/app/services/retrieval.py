import json
from typing import Any

from app.services.embedding import embed_texts
from app.services.vectorstore import QdrantStore

_qdrant = QdrantStore()

GROUND_THRESHOLD = 0.72
AMBIGUOUS_THRESHOLD = 0.55


def tool_search_materials(course_id: str, query: str, top_k: int = 5) -> str:
    """Tool: semantic search over course materials. Returns JSON string for LLM consumption.
    No score thresholds — the LLM evaluates relevance itself."""
    embeddings = embed_texts([query])
    if not embeddings:
        return json.dumps({"results": [], "count": 0, "note": "embedding failed"}, ensure_ascii=False)

    results = _qdrant.search(course_id, embeddings[0], limit=top_k)
    if not results:
        return json.dumps({"results": [], "count": 0, "note": "no matching materials found"}, ensure_ascii=False)

    formatted = []
    for r in results:
        payload = r.get("payload", {})
        file_name = payload.get("file_name", "")
        locator = f"第{payload.get('index', 0) + 1}部分"
        formatted.append({
            "score": round(r.get("score", 0), 3),
            "text": payload.get("text", ""),
            "file_name": file_name,
            "locator": locator,
            "source": f"{file_name} · {locator}",
        })

    return json.dumps({"results": formatted, "count": len(formatted)}, ensure_ascii=False)


def retrieve(
    course_id: str,
    query: str,
    limit: int = 5,
    store: Any = None,
) -> dict:
    query_embeddings = embed_texts([query])
    if not query_embeddings:
        return {"confidence": "out_of_scope", "top_score": 0.0, "results": []}

    query_embedding = query_embeddings[0]
    results = _qdrant.search(course_id, query_embedding, limit=limit)

    if not results:
        return {"confidence": "out_of_scope", "top_score": 0.0, "results": []}

    top_score = results[0]["score"]

    if top_score >= GROUND_THRESHOLD:
        formatted = _format_results("grounded", top_score, results)
    elif top_score >= AMBIGUOUS_THRESHOLD:
        expanded = _qdrant.search(course_id, query_embedding, limit=10)
        formatted = _format_results("ambiguous", top_score, expanded)
    else:
        return {"confidence": "out_of_scope", "top_score": top_score, "results": []}

    return formatted


def _format_results(confidence: str, top_score: float, results: list[dict]) -> dict:
    formatted: list[dict] = []
    for r in results:
        payload = r.get("payload", {})
        formatted.append({
            "text": payload.get("text", ""),
            "score": r["score"],
            "metadata": {
                "file_name": payload.get("file_name", ""),
                "locator": payload.get("locator", f"第{payload.get('index', 0) + 1}部分"),
            },
        })
    return {"confidence": confidence, "top_score": top_score, "results": formatted}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """手算 cosine,避免依赖 numpy;空向量返回 0。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_wiki_layer(
    course_id: str,
    query: str,
    layer: str = "all",
    top_k: int = 5,
    store: Any = None,
) -> list[dict]:
    """三层混合检索统一入口(阶段 3 引入)。

    layer:
      - macro: 在 ChapterWiki 标题 + overview + key_concepts 里搜
      - micro: 在 KC 卡片 name + definition + formula 里搜(向量检索)
      - all:   三层合并排序去重
    """
    results: list[dict] = []
    if store is None:
        return results

    q_emb = embed_texts([query])[0] if query else None

    # Macro 层:章节级
    if layer in ("macro", "all"):
        chapter_wikis = store.get_chapter_wikis_by_course(course_id)
        for cw in chapter_wikis:
            text = f"{cw.title} {cw.overview} {' '.join(cw.key_concepts)}"
            emb = embed_texts([text])[0] if text else None
            if emb and q_emb:
                score = _cosine_similarity(q_emb, emb)
                results.append({
                    "id": cw.id,
                    "name": cw.title,
                    "layer": "macro",
                    "score": score,
                    "content": cw.overview,
                    "source_ref": f"[{cw.title}]",
                    "file_name": "",
                    "locator": cw.title,
                })

    # Micro 层:KC 卡 + Qdrant chunks
    if layer in ("micro", "all"):
        kcs = store.get_kcs_by_course(course_id)
        for kc in kcs:
            text = f"{kc.name} {kc.definition} {kc.formula}"
            emb = embed_texts([text])[0] if text else None
            if emb and q_emb:
                score = _cosine_similarity(q_emb, emb)
                results.append({
                    "id": kc.id,
                    "name": kc.name,
                    "layer": kc.layer,
                    "score": score,
                    "content": kc.definition,
                    "source_ref": kc.source_refs[0].file if kc.source_refs else "",
                    "file_name": kc.source_refs[0].file if kc.source_refs else "",
                    "locator": kc.chapter_id,
                })
        if q_emb:
            q_results = _qdrant.search(course_id, q_emb, limit=top_k)
            for r in q_results:
                payload = r.get("payload", {})
                idx = payload.get("index", 0)
                loc = f"第{idx + 1}部分"
                fname = payload.get("file_name", "")
                results.append({
                    "id": "",
                    "name": "",
                    "layer": "chunk",
                    "score": r.get("score", 0),
                    "content": payload.get("text", ""),
                    "source_ref": f"{fname} · {loc}",
                    "file_name": fname,
                    "locator": loc,
                })

    if layer == "all":
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        # 去重 (同 id + 同 file_name + 同 locator 视为重复)
        seen: set[tuple] = set()
        deduped = []
        for r in results:
            key = (r.get("id", ""), r.get("file_name", ""), r.get("locator", ""))
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        results = deduped

    return results[:top_k]
