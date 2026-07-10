"""Domain terminology extraction, dedup, and retrieval.

Pipeline:
  MD texts → LLM extraction → name-based dedup/merge → embed → Qdrant(type=term)

Retrieval:
  query → embed → Qdrant filter(type=term) → [{name, definition, score}]
"""
from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.services.embedding import embed_texts
from app.services.vectorstore import QdrantStore

logger = logging.getLogger(__name__)

_client = None
_qdrant = QdrantStore()

_EXTRACT_SYSTEM = (
    "你是一个学科知识提取助手。"
    "从给定的学科文本中提取所有专有名词（包括概念、定理、方法、符号等），"
    "为每个术语给出简洁准确的定义（1-2句话）。"
    "输出纯 JSON 数组，不要有任何 markdown 包裹，格式：\n"
    '[{"name":"术语名","definition":"定义内容"}, ...]'
)

_MAX_TEXT_LEN = 3000
_CHUNK_SIZE = 3000
# Use a non-reasoning model for extraction: fast and cheap, no chain-of-thought needed
_EXTRACT_MODEL = "deepseek-v3.2"


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        api_key = settings.deepseek_api_key or "placeholder"
        _client = OpenAI(api_key=api_key, base_url=settings.deepseek_api_base, timeout=120)
    return _client


def _extract_terms_from_text(text: str) -> list[dict]:
    """Call LLM to extract terms from a single text block. Returns [{name, definition}]."""
    truncated = text[:_MAX_TEXT_LEN]
    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model=_EXTRACT_MODEL,
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": truncated},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content or ""
        raw = raw.strip()
        finish = resp.choices[0].finish_reason
        if not raw:
            logger.warning("Term extraction: empty response (finish=%s)", finish)
            return []
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        if isinstance(data, list):
            return [t for t in data if isinstance(t, dict) and t.get("name") and t.get("definition")]
        return []
    except Exception as e:
        logger.warning("Term extraction failed: %s", e)
        return []


def _merge_terms(terms: list[dict]) -> list[dict]:
    """Dedup by lowercase name. Keep longer definition; append unique content if complementary."""
    merged: dict[str, dict] = {}
    for t in terms:
        key = t["name"].lower().strip()
        if key not in merged:
            merged[key] = {"name": t["name"], "definition": t["definition"]}
        else:
            existing_def = merged[key]["definition"]
            new_def = t["definition"]
            if len(new_def) > len(existing_def):
                # New definition is longer/more detailed — prefer it but check for unique content
                if existing_def.strip() not in new_def:
                    merged[key]["definition"] = new_def + "；" + existing_def
                else:
                    merged[key]["definition"] = new_def
            else:
                # Existing is longer — append only if new has unique content
                if new_def.strip() not in existing_def:
                    merged[key]["definition"] = existing_def + "；" + new_def
    return list(merged.values())


def extract_and_upsert_terms(course_id: str, md_texts: list[str]) -> int:
    """Extract domain terms from MD texts, dedup, embed, and store in Qdrant.

    Returns number of terms stored. Safe to call multiple times (full rebuild).
    Large texts are split into _CHUNK_SIZE chunks and extracted in parallel (max 5 workers).
    """
    if not md_texts:
        return 0

    all_chunks: list[str] = []
    for text in md_texts:
        if not text or not text.strip():
            continue
        all_chunks.extend(text[i:i+_CHUNK_SIZE] for i in range(0, len(text), _CHUNK_SIZE))

    logger.info("Terminology extraction: %d chunks from %d texts", len(all_chunks), len(md_texts))

    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_raw: list[dict] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_extract_terms_from_text, chunk): i for i, chunk in enumerate(all_chunks)}
        for fut in as_completed(futures):
            result = fut.result()
            all_raw.extend(result)
            logger.info("Chunk %d done: %d terms (total so far: %d)", futures[fut], len(result), len(all_raw))

    if not all_raw:
        logger.info("No terms extracted for course %s", course_id)
        return 0

    merged = _merge_terms(all_raw)
    logger.info("After dedup: %d terms for course %s", len(merged), course_id)

    texts_to_embed = [f"{t['name']}: {t['definition']}" for t in merged]
    embeddings = embed_texts(texts_to_embed)
    if not embeddings or len(embeddings) != len(merged):
        logger.warning("Embedding count mismatch for terminology, skipping upsert")
        return 0

    _qdrant.delete_terms_by_course(course_id)
    _qdrant.upsert_terms(course_id, merged, embeddings)
    logger.info("Upserted %d terms to Qdrant for course %s", len(merged), course_id)
    return len(merged)


def search_terms(course_id: str, query: str, top_k: int = 5) -> list[dict]:
    """Search terminology dictionary for a query. Returns [{name, definition, score}]."""
    embeddings = embed_texts([query])
    if not embeddings:
        return []
    results = _qdrant.search_terms(course_id, embeddings[0], limit=top_k)
    return [
        {
            "name": r["payload"].get("term", ""),
            "definition": r["payload"].get("text", ""),
            "score": round(r["score"], 3),
            "layer": "term",
        }
        for r in results
    ]
