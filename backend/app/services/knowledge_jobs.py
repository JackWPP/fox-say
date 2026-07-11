"""Enqueue helpers for persistent V2 knowledge jobs.

This module intentionally has no worker loop.  Web/API code may enqueue an
immutable job, while a future controlled worker will claim it from SQLite.
"""

from __future__ import annotations

import uuid

from app.core.config import settings
from app.db.sqlite_store import SqliteStore
from app.schemas.knowledge_jobs import (
    KnowledgeJob,
    KnowledgeJobCreate,
    KnowledgeJobScope,
    KnowledgeJobType,
)
from app.services.source_revision import build_knowledge_revision


def build_knowledge_job_idempotency_key(
    *,
    course_id: str,
    material_id: str | None,
    job_type: KnowledgeJobType,
    revision: int | None,
    target_source_revision: str | None = None,
) -> str:
    """Build the stable identity used to deduplicate a logical V2 job."""
    if material_id is None:
        if target_source_revision is None:
            raise ValueError("course knowledge jobs require target_source_revision")
        return f"knowledge:{job_type}:{course_id}:source:{target_source_revision}"
    if revision is None:
        raise ValueError("material knowledge jobs require revision")
    return f"knowledge:{job_type}:{course_id}:{material_id}:r{revision}"


def enqueue_material_index_job(
    store: SqliteStore,
    *,
    course_id: str,
    material_id: str,
    revision: int,
    token_budget: int | None = None,
) -> KnowledgeJob:
    """Persist one idempotent material indexing job for a source revision."""
    return _enqueue(
        store,
        course_id=course_id,
        material_id=material_id,
        job_type="index_material",
        revision=revision,
        scope="material",
        token_budget=token_budget,
    )


def enqueue_course_compile_job(
    store: SqliteStore,
    *,
    course_id: str,
    source_revision: str,
    token_budget: int | None = None,
) -> KnowledgeJob:
    """Persist one idempotent course compiler job for a course revision."""
    return _enqueue(
        store,
        course_id=course_id,
        material_id=None,
        job_type="compile_course",
        revision=None,
        scope="course",
        target_source_revision=source_revision,
        target_knowledge_revision=build_knowledge_revision(
            source_revision=source_revision,
            compiler_version="course-outline-d0",
        ),
        token_budget=(
            settings.knowledge_job_default_token_budget
            if token_budget is None
            else token_budget
        ),
    )


def _enqueue(
    store: SqliteStore,
    *,
    course_id: str,
    material_id: str | None,
    job_type: KnowledgeJobType,
    revision: int | None,
    scope: KnowledgeJobScope,
    token_budget: int | None,
    target_source_revision: str | None = None,
    target_knowledge_revision: str | None = None,
) -> KnowledgeJob:
    idempotency_key = build_knowledge_job_idempotency_key(
        course_id=course_id,
        material_id=material_id,
        job_type=job_type,
        revision=revision,
        target_source_revision=target_source_revision,
    )
    job = KnowledgeJobCreate(
        job_id=str(uuid.uuid4()),
        course_id=course_id,
        material_id=material_id,
        job_type=job_type,
        revision=revision,
        scope=scope,
        idempotency_key=idempotency_key,
        token_budget=token_budget,
        target_source_revision=target_source_revision,
        target_knowledge_revision=target_knowledge_revision,
    )
    return store.enqueue_knowledge_job(job)
