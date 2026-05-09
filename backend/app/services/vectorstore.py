from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import Settings

_settings = Settings()
_client = QdrantClient(url=_settings.qdrant_url)

VECTOR_DIM = 1536


def _collection_name(course_id: str) -> str:
    return f"course_{course_id}"


class QdrantStore:
    def create_course_collection(self, course_id: str) -> None:
        name = _collection_name(course_id)
        if not _client.collection_exists(name):
            _client.create_collection(
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
        self.create_course_collection(course_id)
        points: list[PointStruct] = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            payload = {
                "text": chunk["text"],
                "index": chunk["index"],
                **metadata,
            }
            points.append(PointStruct(id=i, vector=embedding, payload=payload))
        _client.upsert(collection_name=name, points=points)

    def search(
        self,
        course_id: str,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[dict]:
        name = _collection_name(course_id)
        if not _client.collection_exists(name):
            return []
        results = _client.search(
            collection_name=name,
            query_vector=query_embedding,
            limit=limit,
        )
        return [
            {
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in results
        ]
