from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import settings

_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url)
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
            points.append(PointStruct(id=i, vector=embedding, payload=payload))
        client.upsert(collection_name=name, points=points)

    def search(
        self,
        course_id: str,
        query_embedding: list[float],
        limit: int = 5,
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
        )
        return [
            {
                "score": point.score,
                "payload": point.payload or {},
            }
            for point in response.points
        ]
