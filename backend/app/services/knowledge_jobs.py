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


def build_knowledge_job_idempotency_key(
    *,
    course_id: str,
    material_id: str | None,
    job_type: KnowledgeJobType,
    revision: int,
) -> str:
    """Build the stable identity used to deduplicate a logical V2 job."""
    target = material_id if material_id is not None else "course"
    return f"knowledge:{job_type}:{course_id}:{target}:r{revision}"


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
    revision: int,
    token_budget: int | None = None,
) -> KnowledgeJob:
    """Persist one idempotent course compiler job for a course revision."""
    return _enqueue(
        store,
        course_id=course_id,
        material_id=None,
        job_type="compile_course",
        revision=revision,
        scope="course",
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
    revision: int,
    scope: KnowledgeJobScope,
    token_budget: int | None,
) -> KnowledgeJob:
    idempotency_key = build_knowledge_job_idempotency_key(
        course_id=course_id,
        material_id=material_id,
        job_type=job_type,
        revision=revision,
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
    )
    return store.enqueue_knowledge_job(job)
