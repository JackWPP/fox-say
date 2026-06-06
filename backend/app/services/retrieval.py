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
