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


def _text_overlap_score(query: str, text: str) -> float:
    """快速文本重叠评分(0~1),用于 macro/micro 层,避免逐条调 embedding API。

    算法:query 字符集与 text 字符集的 Jaccard 相似度。
    对中文效果好(单字即 token),零 API 调用。
    """
    if not query or not text:
        return 0.0
    q_chars = set(query.lower())
    t_chars = set(text.lower())
    if not q_chars or not t_chars:
        return 0.0
    intersection = q_chars & t_chars
    union = q_chars | t_chars
    return len(intersection) / len(union) if union else 0.0


def search_wiki_layer(
    course_id: str,
    query: str,
    layer: str = "all",
    top_k: int = 5,
    store: Any = None,
) -> list[dict]:
    """三层混合检索统一入口(阶段 3 引入)。

    layer:
      - macro: 在 ChapterWiki 标题 + overview + key_concepts 里搜(文本匹配)
      - micro: 在 KC 卡片 name + definition + formula 里搜(文本匹配)
      - chunk: 在 Qdrant 向量库搜(向量检索)
      - all:   三层合并排序去重

    macro/micro 用文本匹配而非逐条 embed,避免 N 次 API 调用。
    chunk 层用 Qdrant 已有向量,只 embed query 一次。
    """
    results: list[dict] = []
    if store is None:
        return results

    # Macro 层:章节级(文本匹配,零 API 调用)
    if layer in ("macro", "all"):
        chapter_wikis = store.get_chapter_wikis_by_course(course_id)
        for cw in chapter_wikis:
            text = f"{cw.title} {cw.overview} {' '.join(cw.key_concepts)}"
            score = _text_overlap_score(query, text)
            if score > 0:
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

    # Micro 层:KC 卡(文本匹配) + Qdrant chunks(向量检索)
    if layer in ("micro", "all"):
        kcs = store.get_kcs_by_course(course_id)
        for kc in kcs:
            text = f"{kc.name} {kc.definition} {kc.formula}"
            score = _text_overlap_score(query, text)
            if score > 0:
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
        # Chunk 层:Qdrant 向量检索(只 embed query 一次)
        q_emb = embed_texts([query])[0] if query else None
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
