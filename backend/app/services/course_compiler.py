"""Deterministic D0 compiler for a source-pinned V2 course outline."""

from __future__ import annotations

import hashlib
from collections import OrderedDict

from app.db.sqlite_store import SqliteStore
from app.schemas.course_projection import CourseOutline, CourseOutlineSection
from app.schemas.evidence import EvidenceRef, SourceFragment
from app.schemas.knowledge_jobs import KnowledgeJob
from app.services.knowledge_worker import KnowledgeJobExecutionError


COURSE_OUTLINE_COMPILER_VERSION = "course-outline-d0"


def build_course_outline(
    fragments: list[SourceFragment],
    *,
    course_id: str,
    source_revision: str,
    knowledge_revision: str,
) -> CourseOutline:
    """Group canonical current fragments deterministically by material heading path."""
    if not fragments:
        raise ValueError("Course outline requires at least one current source fragment")
    grouped: OrderedDict[tuple[str, int, tuple[str, ...]], list[SourceFragment]] = OrderedDict()
    for fragment in fragments:
        if fragment.course_id != course_id:
            raise ValueError("Course outline received a fragment from another course")
        key = (fragment.material_id, fragment.material_revision, tuple(fragment.heading_path))
        grouped.setdefault(key, []).append(fragment)

    sections: list[CourseOutlineSection] = []
    for ordinal, ((material_id, material_revision, heading_path), members) in enumerate(grouped.items()):
        section_identity = "\x1f".join(
            [source_revision, material_id, str(material_revision), *heading_path]
        )
        section_id = f"outline_{hashlib.sha256(section_identity.encode('utf-8')).hexdigest()[:24]}"
        title = heading_path[-1] if heading_path else "未命名材料部分"
        sections.append(
            CourseOutlineSection(
                section_id=section_id,
                title=title,
                heading_path=list(heading_path),
                ordinal=ordinal,
                evidence=[EvidenceRef.from_source_fragment(fragment) for fragment in members],
            )
        )

    return CourseOutline(
        course_id=course_id,
        source_revision=source_revision,
        knowledge_revision=knowledge_revision,
        compiler_version=COURSE_OUTLINE_COMPILER_VERSION,
        sections=sections,
        fragment_count=len(fragments),
    )


class CourseCompiler:
    """Compile an immutable outline only when its source target is still current."""

    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    async def __call__(self, job: KnowledgeJob) -> None:
        if job.job_type != "compile_course" or job.material_id is not None:
            raise KnowledgeJobExecutionError(
                "Course compiler received a non-course job",
                code="invalid_course_compile_job",
                retryable=False,
            )
        if job.target_source_revision is None or job.target_knowledge_revision is None:
            raise KnowledgeJobExecutionError(
                "Course compile job is missing its explicit source/knowledge target",
                code="invalid_course_compile_target",
                retryable=False,
            )

        current_manifest = self._store.get_compilable_source_manifest(job.course_id)
        if current_manifest is None or current_manifest[0] != job.target_source_revision:
            raise KnowledgeJobExecutionError(
                "Course source revision changed or is not fully ready before compilation",
                code="stale_course_source_revision",
                retryable=False,
            )
        source_revision, manifest_json = current_manifest
        fragments = self._store.list_current_ready_source_fragments(job.course_id)
        outline = build_course_outline(
            fragments,
            course_id=job.course_id,
            source_revision=source_revision,
            knowledge_revision=job.target_knowledge_revision,
        )
        published = self._store.publish_course_compilation_if_current(
            course_id=job.course_id,
            job_id=job.job_id,
            target_source_revision=source_revision,
            target_knowledge_revision=job.target_knowledge_revision,
            outline=outline,
            source_manifest_json=manifest_json,
            compiler_version=COURSE_OUTLINE_COMPILER_VERSION,
        )
        if not published:
            raise KnowledgeJobExecutionError(
                "Course source revision changed before compilation could be published",
                code="stale_course_source_revision",
                retryable=False,
            )
