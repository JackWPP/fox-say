from app.services.embedding import embed_texts
from app.services.vectorstore import QdrantStore

_qdrant = QdrantStore()

GROUND_THRESHOLD = 0.72
AMBIGUOUS_THRESHOLD = 0.55


def retrieve(
    course_id: str,
    query: str,
    limit: int = 5,
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
        return _format_results("grounded", top_score, results)

    if top_score >= AMBIGUOUS_THRESHOLD:
        expanded = _qdrant.search(course_id, query_embedding, limit=10)
        return _format_results("ambiguous", top_score, expanded)

    return {"confidence": "out_of_scope", "top_score": top_score, "results": []}


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
