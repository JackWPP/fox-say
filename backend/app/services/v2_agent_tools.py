"""Small read-only tool facade for the future V2 course Agent.

This module intentionally exposes only the evidence-first V2 read boundary.
It is not wired into the legacy Agent yet: callers must supply an explicit
``course_id`` for every operation, and no method falls back to Wiki, DMAP, or
historical material revisions.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.db.sqlite_store import SqliteStore
from app.schemas.course_projection import CourseOutline
from app.schemas.evidence import EvidenceRef, SourceFragmentPreview
from app.schemas.knowledge_status import KnowledgeStatus
from app.schemas.retrieval_answer import RetrievalOutcome
from app.services.knowledge_status import build_knowledge_status
from app.services.retrieval import retrieve_current_fragments


class V2AgentTools:
    """Read-only, current-revision tools available to a course-scoped Agent.

    Search deliberately disables vector fallback in this first facade.  This
    keeps a tool invocation free of embedding/model calls; it still uses the
    canonical fragment retriever for exact and heading evidence.  A later
    Agent iteration may opt into an audited semantic retrieval path without
    weakening this boundary.
    """

    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    def search_evidence(
        self,
        course_id: str,
        query: str,
        *,
        limit: int = 5,
        selected_material_ids: Sequence[str] | None = None,
    ) -> RetrievalOutcome:
        """Search only current ready V2 source fragments for one course."""
        return retrieve_current_fragments(
            self._store,
            course_id,
            query,
            limit=limit,
            selected_material_ids=selected_material_ids,
            enable_vector=False,
        )

    def open_evidence(
        self,
        course_id: str,
        evidence: EvidenceRef,
    ) -> SourceFragmentPreview | None:
        """Open an EvidenceRef only if it is still current in ``course_id``.

        A reference is an untrusted input at this boundary.  Looking up the
        fragment by ID is insufficient: its course, material, and revision
        must still equal the supplied reference before source text is shown.
        """
        if evidence.course_id != course_id:
            raise ValueError("EvidenceRef does not belong to the requested course")
        resolved = self._store.get_current_ready_source_fragment_preview(
            course_id, evidence.fragment_id
        )
        if resolved is None:
            return None
        fragment, file_name = resolved
        if (
            fragment.course_id != evidence.course_id
            or fragment.material_id != evidence.material_id
            or fragment.material_revision != evidence.material_revision
        ):
            return None
        return SourceFragmentPreview(
            course_id=fragment.course_id,
            material_id=fragment.material_id,
            material_revision=fragment.material_revision,
            fragment_id=fragment.fragment_id,
            file_name=file_name,
            text=fragment.text,
            locator=fragment.locator(),
            heading_path=fragment.heading_path,
            page_start=fragment.page_start,
            page_end=fragment.page_end,
            slide_start=fragment.slide_start,
            slide_end=fragment.slide_end,
            char_start=fragment.char_start,
            char_end=fragment.char_end,
            kind=fragment.kind,
        )

    def get_current_outline(self, course_id: str) -> CourseOutline | None:
        """Return the current succeeded D0 outline, never a stale snapshot."""
        status = self.get_knowledge_status(course_id)
        if status.projection_status != "ready" or status.source_revision is None:
            return None
        return self._store.get_current_course_outline(course_id, status.source_revision)

    def get_knowledge_status(self, course_id: str) -> KnowledgeStatus:
        """Return the durable V2 availability snapshot for one course."""
        return build_knowledge_status(self._store, course_id)
