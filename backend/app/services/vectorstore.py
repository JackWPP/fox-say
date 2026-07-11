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
from app.schemas.evidence import SourceFragment

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


def _source_fragment_point_id(course_id: str, fragment_id: str) -> str:
    """Return the stable Qdrant UUID for one course-scoped source fragment.

    ``SourceFragment.fragment_id`` is deliberately opaque and is not itself a
    Qdrant-compatible UUID.  UUID5 keeps retries idempotent without deriving
    scope from the identifier or relying on a random point ID.
    """
    identity = "\x1f".join(("source_fragment", course_id, fragment_id))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))


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
                "index": chunk.get("index", i),
                "heading_path": chunk.get("heading_path", ""),
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

    def upsert_source_fragments(
        self,
        course_id: str,
        fragments: list[SourceFragment],
        embeddings: list[list[float]],
        *,
        file_name: str,
    ) -> None:
        """Upsert V2 source evidence with stable, retry-safe point IDs.

        This intentionally does not reuse ``upsert_chunks``: legacy chunks
        use random IDs and do not have the evidence fields required to build a
        durable citation.  A caller replacing a material should first call
        ``delete_source_fragments_by_material`` so only V2 evidence for that
        material is replaced.
        """
        if not course_id or not course_id.strip():
            raise ValueError("course_id is required")
        if len(fragments) != len(embeddings):
            raise ValueError("fragments and embeddings must have the same length")

        for fragment in fragments:
            if fragment.course_id != course_id:
                raise ValueError(
                    "SourceFragment course_id must match the requested course_id"
                )

        if not fragments:
            return

        name = _collection_name(course_id)
        client = _get_client()
        self.create_course_collection(course_id)
        points: list[PointStruct] = []
        for fragment, embedding in zip(fragments, embeddings, strict=True):
            payload = {
                "type": "source_fragment",
                "course_id": course_id,
                "fragment_id": fragment.fragment_id,
                "material_id": fragment.material_id,
                "material_revision": fragment.material_revision,
                "ordinal": fragment.ordinal,
                "text": fragment.text,
                "heading_path": list(fragment.heading_path),
                "page_start": fragment.page_start,
                "page_end": fragment.page_end,
                "slide_start": fragment.slide_start,
                "slide_end": fragment.slide_end,
                "char_start": fragment.char_start,
                "char_end": fragment.char_end,
                "kind": fragment.kind,
                "asset_id": fragment.asset_id,
                "parser_name": fragment.parser_name,
                "content_hash": fragment.content_hash,
                "file_name": file_name,
                "locator": fragment.locator(),
            }
            points.append(
                PointStruct(
                    id=_source_fragment_point_id(course_id, fragment.fragment_id),
                    vector=embedding,
                    payload=payload,
                )
            )
        client.upsert(collection_name=name, points=points)

    def delete_source_fragments_by_material(
        self,
        course_id: str,
        material_id: str,
    ) -> None:
        """Delete only V2 evidence points for one material in one course.

        The explicit type condition prevents this replacement path from
        deleting legacy chunks or note/term vectors that happen to share a
        material ID.
        """
        if not course_id or not course_id.strip():
            raise ValueError("course_id is required")
        if not material_id or not material_id.strip():
            raise ValueError("material_id is required")

        name = _collection_name(course_id)
        client = _get_client()
        if not client.collection_exists(name):
            return
        client.delete(
            collection_name=name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="type",
                        match=MatchValue(value="source_fragment"),
                    ),
                    FieldCondition(
                        key="course_id",
                        match=MatchValue(value=course_id),
                    ),
                    FieldCondition(
                        key="material_id",
                        match=MatchValue(value=material_id),
                    ),
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

    def build_source_fragment_filter(
        self,
        course_id: str,
        material_scopes: list[tuple[str, int]],
    ) -> Filter:
        """Build the course- and revision-safe filter for source evidence.

        A material ID is only meaningful together with its revision.  Keeping
        each pair in its own nested ``Filter`` under ``should`` is deliberate:
        two independent ``MatchAny`` conditions would also match a material
        from one pair with the revision from another pair.
        """
        if not course_id or not course_id.strip():
            raise ValueError("course_id is required")
        if not material_scopes:
            raise ValueError("material_scopes is required")

        scope_filters: list[Filter] = []
        for material_id, material_revision in material_scopes:
            if not isinstance(material_id, str) or not material_id.strip():
                raise ValueError("material_id is required")
            if (
                isinstance(material_revision, bool)
                or not isinstance(material_revision, int)
                or material_revision < 0
            ):
                raise ValueError("material_revision must be a non-negative integer")
            scope_filters.append(
                Filter(
                    must=[
                        FieldCondition(
                            key="material_id",
                            match=MatchValue(value=material_id),
                        ),
                        FieldCondition(
                            key="material_revision",
                            match=MatchValue(value=material_revision),
                        ),
                    ]
                )
            )

        return Filter(
            must=[
                FieldCondition(
                    key="type",
                    match=MatchValue(value="source_fragment"),
                ),
                FieldCondition(
                    key="course_id",
                    match=MatchValue(value=course_id),
                ),
            ],
            should=scope_filters,
        )

    def search_source_fragments(
        self,
        course_id: str,
        query_embedding: list[float],
        material_scopes: list[tuple[str, int]],
        limit: int = 5,
    ) -> list[dict]:
        """Search only current, explicitly scoped source-fragment evidence.

        An empty scope is intentionally an empty result, rather than an
        unfiltered search.  This lets callers safely derive scopes from the
        current-ready SQLite boundary without risking historical or unrelated
        material vectors when that boundary has no ready material.
        """
        if not material_scopes:
            return []
        return self.search(
            course_id,
            query_embedding,
            limit=limit,
            query_filter=self.build_source_fragment_filter(course_id, material_scopes),
        )

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
