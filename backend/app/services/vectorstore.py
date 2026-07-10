import asyncio
import threading
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import settings

_client: QdrantClient | None = None
_client_lock = threading.Lock()
_write_lock = asyncio.Lock()


def _get_client() -> QdrantClient:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:  # double-check after acquiring lock
            return _client
        if settings.qdrant_url:
            _client = QdrantClient(url=settings.qdrant_url)
        else:
            from pathlib import Path
            local_path = Path(settings.qdrant_local_path)
            local_path.mkdir(parents=True, exist_ok=True)
            _client = QdrantClient(path=str(local_path))
    return _client


VECTOR_DIM = 1024


def _collection_name(course_id: str) -> str:
    return f"course_{course_id}"


class QdrantStore:
    def create_course_collection(self, course_id: str) -> None:
        name = _collection_name(course_id)
        client = _get_client()
        if not client.collection_exists(name):
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            )

    def upsert_chunks(
        self,
        course_id: str,
        chunks: list[dict],
        embeddings: list[list[float]],
        metadata: dict,
    ) -> None:
        name = _collection_name(course_id)
        client = _get_client()
        self.create_course_collection(course_id)
        points: list[PointStruct] = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            payload = {
                "text": chunk["text"],
                "index": chunk["index"],
                **metadata,
            }
            points.append(PointStruct(id=str(uuid.uuid4()), vector=embedding, payload=payload))
        client.upsert(collection_name=name, points=points)

    def delete_by_material(self, course_id: str, material_id: str) -> None:
        name = _collection_name(course_id)
        client = _get_client()
        if not client.collection_exists(name):
            return
        client.delete(
            collection_name=name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="material_id",
                        match=MatchValue(value=material_id),
                    )
                ]
            ),
        )

    def search(
        self,
        course_id: str,
        query_embedding: list[float],
        limit: int = 5,
        query_filter: Filter | None = None,
    ) -> list[dict]:
        name = _collection_name(course_id)
        client = _get_client()
        if not client.collection_exists(name):
            return []
        response = client.query_points(
            collection_name=name,
            query=query_embedding,
            limit=limit,
            with_payload=True,
            query_filter=query_filter,
        )
        return [
            {
                "score": point.score,
                "payload": point.payload or {},
            }
            for point in response.points
        ]

    def upsert_note(
        self,
        course_id: str,
        note_id: str,
        title: str,
        content: str,
        embedding: list[float],
    ) -> None:
        name = _collection_name(course_id)
        client = _get_client()
        self.create_course_collection(course_id)
        self.delete_note(course_id, note_id)
        point_id = str(uuid.uuid4())
        payload = {
            "text": content,
            "type": "note",
            "note_id": note_id,
            "title": title,
            "file_name": "笔记",
            "locator": title,
        }
        client.upsert(
            collection_name=name,
            points=[PointStruct(id=point_id, vector=embedding, payload=payload)],
        )

    def delete_note(self, course_id: str, note_id: str) -> None:
        name = _collection_name(course_id)
        client = _get_client()
        if not client.collection_exists(name):
            return
        client.delete(
            collection_name=name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="note_id",
                        match=MatchValue(value=note_id),
                    )
                ]
            ),
        )

    def build_filter(
        self,
        material_ids: list[str] | None = None,
        note_ids: list[str] | None = None,
    ) -> Filter | None:
        must: list[FieldCondition] = []
        if material_ids:
            must.append(
                FieldCondition(
                    key="material_id",
                    match=MatchAny(any=material_ids),
                )
            )
        if note_ids:
            must.append(
                FieldCondition(
                    key="note_id",
                    match=MatchAny(any=note_ids),
                )
            )
        if not must:
            return None
        return Filter(must=must)

    def upsert_terms(
        self,
        course_id: str,
        terms: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        """Upsert domain terminology into Qdrant (type=term).

        Each term dict must have 'name' and 'definition' keys.
        Point IDs are deterministic (uuid5) so re-running overwrites cleanly.
        """
        name = _collection_name(course_id)
        client = _get_client()
        self.create_course_collection(course_id)
        points: list[PointStruct] = []
        for term, embedding in zip(terms, embeddings):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{course_id}:{term['name'].lower().strip()}"))
            payload = {
                "type": "term",
                "term": term["name"],
                "text": term["definition"],
                "course_id": course_id,
            }
            points.append(PointStruct(id=point_id, vector=embedding, payload=payload))
        if points:
            client.upsert(collection_name=name, points=points)

    def delete_terms_by_course(self, course_id: str) -> None:
        name = _collection_name(course_id)
        client = _get_client()
        if not client.collection_exists(name):
            return
        client.delete(
            collection_name=name,
            points_selector=Filter(
                must=[
                    FieldCondition(key="type", match=MatchValue(value="term")),
                    FieldCondition(key="course_id", match=MatchValue(value=course_id)),
                ]
            ),
        )

    def search_terms(
        self,
        course_id: str,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[dict]:
        name = _collection_name(course_id)
        client = _get_client()
        if not client.collection_exists(name):
            return []
        term_filter = Filter(
            must=[
                FieldCondition(key="type", match=MatchValue(value="term")),
                FieldCondition(key="course_id", match=MatchValue(value=course_id)),
            ]
        )
        response = client.query_points(
            collection_name=name,
            query=query_embedding,
            limit=limit,
            with_payload=True,
            query_filter=term_filter,
        )
        return [{"score": p.score, "payload": p.payload or {}} for p in response.points]

    def get_chunk_by_index(
        self,
        course_id: str,
        material_id: str,
        chunk_index: int,
    ) -> dict | None:
        name = _collection_name(course_id)
        client = _get_client()
        if not client.collection_exists(name):
            return None
        scroll_filter = Filter(
            must=[
                FieldCondition(key="material_id", match=MatchValue(value=material_id)),
                FieldCondition(key="index", match=MatchValue(value=chunk_index)),
            ]
        )
        points, _ = client.scroll(
            collection_name=name,
            scroll_filter=scroll_filter,
            limit=1,
            with_payload=True,
        )
        if not points:
            return None
        return points[0].payload or {}
