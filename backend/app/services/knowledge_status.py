"""Build durable V2 knowledge availability snapshots without model calls."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.db.sqlite_store import SqliteStore
from app.schemas.knowledge_status import (
    KnowledgeCoverage,
    KnowledgeLifecycleStatus,
    KnowledgeStatus,
    MaterialEvidenceState,
    MaterialEvidenceStatus,
    ProjectionStatus,
    SourceEvidenceStatus,
)
from app.schemas.course_projection import CourseCompilation
from app.services.source_revision import build_source_revision


def build_knowledge_status(store: SqliteStore, course_id: str) -> KnowledgeStatus:
    """Return one statement-consistent, current-revision availability snapshot.

    ``source_revision`` describes current material inputs only.  C1 has no
    course compiler yet, so source-ready evidence is intentionally still a
    ``partial`` course rather than a misleading fully ``ready`` knowledge map.
    """
    rows = store.get_knowledge_status_snapshot(course_id)
    if not rows:
        return KnowledgeStatus(
            course_id=course_id,
            status="empty",
            source_status="empty",
            projection_status="not_started",
            coverage=KnowledgeCoverage(
                total_materials=0,
                ready_materials=0,
                processing_materials=0,
                retryable_materials=0,
                failed_materials=0,
                fragment_count=0,
            ),
        )

    material_statuses = [_build_material_status(row) for row in rows]
    ready_materials = sum(item.status == "ready" for item in material_statuses)
    processing_materials = sum(item.status == "processing" for item in material_statuses)
    retryable_materials = sum(item.status == "retryable" for item in material_statuses)
    failed_materials = sum(
        item.status in {"failed", "missing_evidence"} for item in material_statuses
    )
    source_status = _source_status(
        ready_materials=ready_materials,
        processing_materials=processing_materials,
        retryable_materials=retryable_materials,
        failed_materials=failed_materials,
    )
    source_revision = _source_revision(rows)
    projection_status, compilation = _projection_status(
        store,
        course_id=course_id,
        source_status=source_status,
        source_revision=source_revision,
    )
    return KnowledgeStatus(
        course_id=course_id,
        status=_overall_status(source_status, projection_status),
        source_status=source_status,
        projection_status=projection_status,
        source_revision=source_revision,
        knowledge_revision=compilation.knowledge_revision if compilation is not None else None,
        compiled_from_source_revision=(
            compilation.source_revision if compilation is not None else None
        ),
        coverage=KnowledgeCoverage(
            total_materials=len(material_statuses),
            ready_materials=ready_materials,
            processing_materials=processing_materials,
            retryable_materials=retryable_materials,
            failed_materials=failed_materials,
            fragment_count=sum(item.fragment_count for item in material_statuses),
        ),
        materials=material_statuses,
    )


def _build_material_status(row: Mapping[str, Any]) -> MaterialEvidenceStatus:
    material_status = row["material_status"]
    fragment_count = int(row["fragment_count"])
    job_status = row["job_status"]
    error_code = row["error_code"]
    error_detail = row["error_detail"]

    state: MaterialEvidenceState
    if not row["content_hash"]:
        state = "missing_evidence"
        error_code = "legacy_material_requires_reindex"
        error_detail = "Current material revision has no content hash and cannot be V2 evidence"
    elif job_status in {"queued", "running"}:
        state = "processing"
    elif job_status == "retryable":
        state = "retryable"
    elif job_status == "failed":
        state = "failed"
    elif job_status is None:
        state = "missing_evidence"
        error_code = "current_index_job_missing"
        error_detail = "Current material revision has no durable index job"
    elif job_status == "succeeded" and material_status == "ready" and fragment_count > 0:
        state = "ready"
        error_code = None
        error_detail = None
    elif job_status == "succeeded" and material_status != "ready":
        state = "missing_evidence"
        error_code = "material_not_ready_after_index"
        error_detail = "Index job succeeded but current material is not marked ready"
    else:
        state = "missing_evidence"
        error_code = "source_fragments_missing"
        error_detail = "Index job succeeded but current material has no source fragments"

    return MaterialEvidenceStatus(
        material_id=row["material_id"],
        filename=row["filename"],
        material_revision=row["material_revision"],
        status=state,
        fragment_count=fragment_count,
        job_status=job_status,
        error_code=error_code,
        error_detail=error_detail,
    )


def _source_status(
    *,
    ready_materials: int,
    processing_materials: int,
    retryable_materials: int,
    failed_materials: int,
) -> SourceEvidenceStatus:
    total = ready_materials + processing_materials + retryable_materials + failed_materials
    if total == 0:
        return "empty"
    if ready_materials == total:
        return "ready"
    if ready_materials > 0:
        return "partial"
    if processing_materials > 0:
        return "processing"
    return "failed"


def _projection_status(
    store: SqliteStore,
    *,
    course_id: str,
    source_status: SourceEvidenceStatus,
    source_revision: str | None,
) -> tuple[ProjectionStatus, CourseCompilation | None]:
    if source_revision is None:
        return "not_started", None
    current = store.get_current_course_compilation(course_id, source_revision)
    if source_status == "ready" and current is not None:
        return "ready", current
    job = store.get_course_compile_job_for_source(course_id, source_revision)
    if job is not None:
        if job.status in {"queued", "running"}:
            return "processing", None
        if job.status in {"retryable", "failed"}:
            return "failed", None
    latest = store.get_latest_course_compilation(course_id)
    if latest is not None and latest.source_revision != source_revision:
        return "stale", latest
    return "not_started", None


def _overall_status(
    source_status: SourceEvidenceStatus,
    projection_status: str,
) -> KnowledgeLifecycleStatus:
    if projection_status == "ready":
        return "ready"
    if projection_status == "stale":
        return "stale"
    if source_status == "empty":
        return "empty"
    if source_status == "processing":
        return "processing"
    if source_status == "failed":
        return "failed"
    return "partial"


def _source_revision(rows: Sequence[Mapping[str, Any]]) -> str | None:
    if any(not row["content_hash"] for row in rows):
        return None
    return build_source_revision(rows)[0]
