"""V2 material indexing handler for the durable knowledge-job worker.

This is deliberately narrower than the legacy pipeline: it turns one current
material revision into normalized Markdown, traceable source fragments and a
stable fragment vector index.  Course-level knowledge compilation is a later
job and is not triggered here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from app.db.sqlite_store import SqliteStore
from app.schemas.knowledge_jobs import KnowledgeJob
from app.services.embedding import embed_texts
from app.services.knowledge_worker import KnowledgeJobExecutionError
from app.services.normalizer import NormalizationEngine
from app.services.parser_interface import DocumentParsingException, UnifiedParserOutput
from app.services.parsing import parse_document_full
from app.services.source_fragments import build_source_fragments
from app.services.vectorstore import QdrantStore

ParseDocument = Callable[[str, str], UnifiedParserOutput]
EmbedTexts = Callable[[list[str]], list[list[float]]]


class MaterialIndexer:
    """Index exactly one material revision with explicit stale-write guards."""

    def __init__(
        self,
        store: SqliteStore,
        *,
        vector_store: QdrantStore | None = None,
        parse_document: ParseDocument = parse_document_full,
        embed: EmbedTexts = embed_texts,
    ) -> None:
        self._store = store
        self._vector_store = vector_store or QdrantStore()
        self._parse_document = parse_document
        self._embed = embed

    async def __call__(self, job: KnowledgeJob) -> None:
        if job.job_type != "index_material" or job.material_id is None:
            raise KnowledgeJobExecutionError(
                "Material index handler received a non-material job",
                code="invalid_material_index_job",
                retryable=False,
            )

        material = self._store.get_material(job.course_id, job.material_id)
        if material is None:
            raise KnowledgeJobExecutionError(
                "Material no longer exists in this course",
                code="material_not_found",
                retryable=False,
            )
        if material.revision != job.revision:
            raise self._stale_revision_error(job, material.revision)

        file_path = self._store.get_material_file_path(job.course_id, job.material_id)
        if not file_path or not Path(file_path).is_file():
            await self._mark_failed_if_current(job)
            raise KnowledgeJobExecutionError(
                "Original material file is not available for indexing",
                code="material_file_not_found",
                retryable=False,
            )

        try:
            parser_output = await asyncio.to_thread(
                self._parse_document, file_path, material.kind
            )
            normalized = NormalizationEngine().normalize(
                parser_output.markdown_content,
                parser_output.raw_input_type,
                parser_output.extracted_assets,
            )
            markdown = normalized.markdown_content
            if not markdown.strip():
                raise ValueError("Parser produced empty normalized Markdown")
            fragments = build_source_fragments(
                markdown,
                course_id=job.course_id,
                material_id=job.material_id,
                material_revision=job.revision,
                parser_name=parser_output.parser_name or "unknown-parser",
            )
            embeddings = await asyncio.to_thread(
                self._embed, [fragment.text for fragment in fragments]
            )
            if len(embeddings) != len(fragments):
                raise RuntimeError(
                    "Embedding provider returned a different number of vectors than source fragments"
                )
        except DocumentParsingException as exc:
            await self._mark_failed_if_current(job)
            raise KnowledgeJobExecutionError(
                str(exc),
                code="material_parse_failed",
                retryable=exc.original_error is not None,
            ) from exc
        except ValueError as exc:
            await self._mark_failed_if_current(job)
            raise KnowledgeJobExecutionError(
                str(exc), code="material_index_input_invalid", retryable=False
            ) from exc
        except Exception as exc:
            await self._mark_failed_if_current(job)
            raise KnowledgeJobExecutionError(
                f"Material indexing infrastructure failed: {exc}",
                code="material_index_infrastructure_failed",
                retryable=True,
            ) from exc

        current_material = self._store.get_material(job.course_id, job.material_id)
        if current_material is None or current_material.revision != job.revision:
            raise self._stale_revision_error(
                job, current_material.revision if current_material is not None else None
            )

        if not await asyncio.to_thread(
            self._store.save_parsed_text_if_revision,
            job.course_id,
            job.material_id,
            job.revision,
            markdown,
        ):
            raise self._stale_revision_error(job, None)

        asset_rows = [asset.model_dump() for asset in parser_output.extracted_assets]

        def publish_assets() -> None:
            self._store.replace_extracted_assets(
                asset_rows,
                job.course_id,
                job.material_id,
                parser_output.document_id,
            )

        def publish_vectors() -> None:
            self._vector_store.delete_source_fragments_by_material(
                job.course_id,
                job.material_id,
            )
            self._vector_store.upsert_source_fragments(
                job.course_id,
                fragments,
                embeddings,
                file_name=material.filename,
            )

        try:
            published = await asyncio.to_thread(
                self._store.publish_material_index_if_current,
                job.course_id,
                job.material_id,
                job.revision,
                fragments,
                publish_vectors,
                publish_assets,
            )
        except Exception as exc:
            await self._mark_failed_if_current(job)
            raise KnowledgeJobExecutionError(
                f"Source evidence index write failed: {exc}",
                code="source_fragment_index_failed",
                retryable=True,
            ) from exc

        if not published:
            raise self._stale_revision_error(job, None)

    async def _mark_failed_if_current(self, job: KnowledgeJob) -> None:
        if job.material_id is None:
            return
        await asyncio.to_thread(
            self._store.update_material_status_if_revision,
            job.course_id,
            job.material_id,
            job.revision,
            "failed",
        )

    @staticmethod
    def _stale_revision_error(
        job: KnowledgeJob, current_revision: int | None
    ) -> KnowledgeJobExecutionError:
        current = "missing" if current_revision is None else str(current_revision)
        return KnowledgeJobExecutionError(
            f"Material index job revision {job.revision} is stale; current revision is {current}",
            code="stale_material_revision",
            retryable=False,
        )


def build_material_index_handlers(store: SqliteStore) -> dict[str, MaterialIndexer]:
    """Return the V2 worker handler mapping without creating background work."""
    return {"index_material": MaterialIndexer(store)}
