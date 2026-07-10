import json
from typing import Any

from app.services.embedding import embed_texts
from app.services.vectorstore import QdrantStore

_qdrant = QdrantStore()

GROUND_THRESHOLD = 0.72
AMBIGUOUS_THRESHOLD = 0.55


def tool_search_materials(course_id: str, query: str, top_k: int = 5) -> str:
    embeddings = embed_texts([query])
    if not embeddings:
        return json.dumps({"results": [], "count": 0, "note": "embedding failed"}, ensure_ascii=False)

    results = _qdrant.search(course_id, embeddings[0], limit=top_k)
    if not results:
        return json.dumps({"results": [], "count": 0, "note": "no matching materials found"}, ensure_ascii=False)

    formatted = []
    for r in results:
        payload = r.get("payload", {})
        is_note = payload.get("type") == "note"
        if is_note:
            file_name = "笔记"
            locator = payload.get("title", "")
            source = f"笔记 · {locator}"
        else:
            file_name = payload.get("file_name", "")
            locator = f"第{payload.get('index', 0) + 1}部分"
            source = f"{file_name} · {locator}"
        formatted.append({
            "score": round(r.get("score", 0), 3),
            "text": payload.get("text", ""),
            "file_name": file_name,
            "locator": locator,
            "source": source,
        })

    return json.dumps({"results": formatted, "count": len(formatted)}, ensure_ascii=False)


def retrieve(
    course_id: str,
    query: str,
    limit: int = 5,
    store: Any = None,
    selected_material_ids: list[str] | None = None,
    selected_note_ids: list[str] | None = None,
) -> dict:
    query_embeddings = embed_texts([query])
    if not query_embeddings:
        return {"confidence": "out_of_scope", "top_score": 0.0, "results": []}

    query_embedding = query_embeddings[0]

    all_results = _search_with_filters(
        course_id, query_embedding, limit=max(limit, 10),
        selected_material_ids=selected_material_ids,
        selected_note_ids=selected_note_ids,
    )

    if not all_results:
        return {"confidence": "out_of_scope", "top_score": 0.0, "results": []}

    top_score = all_results[0]["score"]

    if top_score >= GROUND_THRESHOLD:
        formatted = _format_results("grounded", top_score, all_results[:limit])
    elif top_score >= AMBIGUOUS_THRESHOLD:
        expanded = _search_with_filters(
            course_id, query_embedding, limit=10,
            selected_material_ids=selected_material_ids,
            selected_note_ids=selected_note_ids,
        )
        formatted = _format_results("ambiguous", top_score, expanded)
    else:
        return {"confidence": "out_of_scope", "top_score": top_score, "results": []}

    return formatted


def _search_with_filters(
    course_id: str,
    query_embedding: list[float],
    limit: int = 5,
    selected_material_ids: list[str] | None = None,
    selected_note_ids: list[str] | None = None,
) -> list[dict]:
    from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

    all_results: list[dict] = []

    has_material_filter = bool(selected_material_ids)
    has_note_filter = bool(selected_note_ids)

    if not has_material_filter and not has_note_filter:
        return _qdrant.search(course_id, query_embedding, limit=limit)

    if has_material_filter:
        material_filter = Filter(
            must=[
                FieldCondition(key="material_id", match=MatchAny(any=selected_material_ids)),
            ]
        )
        material_results = _qdrant.search(
            course_id, query_embedding, limit=limit, query_filter=material_filter
        )
        all_results.extend(material_results)

    if has_note_filter:
        note_filter = Filter(
            must=[
                FieldCondition(key="type", match=MatchValue(value="note")),
                FieldCondition(key="note_id", match=MatchAny(any=selected_note_ids)),
            ]
        )
        note_results = _qdrant.search(
            course_id, query_embedding, limit=limit, query_filter=note_filter
        )
        all_results.extend(note_results)

    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

    seen_texts: set[str] = set()
    deduped: list[dict] = []
    for r in all_results:
        text = r.get("payload", {}).get("text", "")
        if text not in seen_texts:
            seen_texts.add(text)
            deduped.append(r)
    return deduped[:limit]


def _format_results(confidence: str, top_score: float, results: list[dict]) -> dict:
    formatted: list[dict] = []
    for r in results:
        payload = r.get("payload", {})
        is_note = payload.get("type") == "note"
        if is_note:
            file_name = "笔记"
            locator = payload.get("title", "")
        else:
            file_name = payload.get("file_name", "")
            locator = payload.get("locator", f"第{payload.get('index', 0) + 1}部分")
        formatted.append({
            "text": payload.get("text", ""),
            "score": r["score"],
            "metadata": {
                "file_name": file_name,
                "locator": locator,
                "is_note": is_note,
                "note_id": payload.get("note_id", ""),
            },
        })
    return {"confidence": confidence, "top_score": top_score, "results": formatted}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# 章节 embedding 缓存（避免每次查询都重新 embed 所有章节）
_chapter_embedding_cache: dict[str, list[float]] = {}


def _get_chapter_embedding(text: str) -> list[float] | None:
    """获取文本的 embedding，带内存缓存。"""
    cache_key = text[:200]
    if cache_key in _chapter_embedding_cache:
        return _chapter_embedding_cache[cache_key]
    try:
        embs = embed_texts([text])
        if embs:
            _chapter_embedding_cache[cache_key] = embs[0]
            return embs[0]
    except Exception:
        pass
    return None


def search_wiki_layer(
    course_id: str,
    query: str,
    layer: str = "all",
    top_k: int = 5,
    store: Any = None,
    selected_material_ids: list[str] | None = None,
    selected_note_ids: list[str] | None = None,
) -> list[dict]:
    results: list[dict] = []
    if store is None:
        return results

    q_emb = None
    if query:
        try:
            embs = embed_texts([query])
            if embs:
                q_emb = embs[0]
        except Exception:
            q_emb = None

    if layer in ("macro", "all"):
        chapter_wikis = store.get_chapter_wikis_by_course(course_id)
        for cw in chapter_wikis:
            text = f"{cw.title} {cw.overview} {' '.join(cw.key_concepts)}"
            ch_emb = _get_chapter_embedding(text)
            if q_emb is not None and ch_emb is not None:
                score = _cosine_similarity(q_emb, ch_emb)
            else:
                score = 0.0
            if score > 0.1:
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

    if layer in ("micro", "all"):
        kcs = store.get_kcs_by_course(course_id)

        kcs_with_emb = [kc for kc in kcs if kc.embedding is not None]
        kcs_without_emb = [kc for kc in kcs if kc.embedding is None]

        if q_emb is not None:
            for kc in kcs_with_emb:
                score = _cosine_similarity(q_emb, kc.embedding)
                if score > 0.1:
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

            # KCs without stored embeddings: compute on-demand
            for kc in kcs_without_emb:
                text = f"{kc.name} {kc.definition} {kc.formula}"
                kc_emb = _get_chapter_embedding(text)
                if kc_emb is not None:
                    score = _cosine_similarity(q_emb, kc_emb)
                    if score > 0.1:
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

        if q_emb is not None:
            q_results = _search_with_filters(
                course_id, q_emb, limit=top_k,
                selected_material_ids=selected_material_ids,
                selected_note_ids=selected_note_ids,
            )
            for r in q_results:
                payload = r.get("payload", {})
                is_note = payload.get("type") == "note"
                if is_note:
                    note_title = payload.get("title", "")
                    fname = "笔记"
                    loc = note_title
                    source_ref = f"笔记 · {loc}"
                else:
                    idx = payload.get("index", 0)
                    loc = f"第{idx + 1}部分"
                    fname = payload.get("file_name", "")
                    source_ref = f"{fname} · {loc}"
                results.append({
                    "id": payload.get("note_id", "") if is_note else "",
                    "name": note_title if is_note else "",
                    "layer": "note" if is_note else "chunk",
                    "score": r.get("score", 0),
                    "content": payload.get("text", ""),
                    "source_ref": source_ref,
                    "file_name": fname,
                    "locator": loc,
                    "is_note": is_note,
                })

    if layer == "all":
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        seen: set[tuple] = set()
        deduped = []
        for r in results:
            key = (r.get("id", ""), r.get("file_name", ""), r.get("locator", ""))
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        results = deduped

    return results[:top_k]
