"""Rule-only V2 Term-to-KnowledgeComponent projection."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from app.schemas.knowledge_components import KnowledgeComponent, build_knowledge_component_id
from app.schemas.knowledge_jobs import KnowledgeJob
from app.schemas.semantic_atoms import SemanticAtom
from app.schemas.terms import Term
from app.services.knowledge_worker import KnowledgeJobExecutionError

if TYPE_CHECKING:
    from app.db.sqlite_store import SqliteStore


def build_knowledge_components(
    terms: Iterable[Term],
    *,
    atoms: Iterable[SemanticAtom],
    course_id: str,
    source_revision: str,
    knowledge_revision: str,
) -> tuple[list[KnowledgeComponent], int]:
    """Project each valid current Term into exactly one evidence-preserving KC."""
    atom_by_id = {atom.atom_id: atom for atom in atoms}
    components: list[KnowledgeComponent] = []
    rejected = 0
    for term in sorted(terms, key=lambda value: (value.canonical_key, value.term_id)):
        if (
            term.course_id != course_id
            or term.source_revision != source_revision
            or term.knowledge_revision != knowledge_revision
        ):
            rejected += 1
            continue
        definition_atom = atom_by_id.get(term.definition_atom_id)
        if (
            definition_atom is None
            or definition_atom.course_id != course_id
            or definition_atom.source_revision != source_revision
            or definition_atom.knowledge_revision != knowledge_revision
            or definition_atom.statement != term.definition
            or definition_atom.atom_type != term.term_kind
        ):
            rejected += 1
            continue
        components.append(
            KnowledgeComponent(
                kc_id=build_knowledge_component_id(
                    course_id=course_id,
                    source_revision=source_revision,
                    knowledge_revision=knowledge_revision,
                    term_id=term.term_id,
                ),
                course_id=course_id,
                source_revision=source_revision,
                knowledge_revision=knowledge_revision,
                term_id=term.term_id,
                name=term.canonical_name,
                kind=term.term_kind,
                definition=term.definition,
                section_id=definition_atom.section_id,
                evidence=term.evidence,
            )
        )
    return components, rejected


class KnowledgeComponentCompiler:
    """Publish KCs only after the matching Term parent has succeeded."""

    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    async def __call__(self, job: KnowledgeJob) -> None:
        if job.job_type != "compile_kcs" or job.material_id is not None:
            raise KnowledgeJobExecutionError("KC compiler received a non-course KC job", code="invalid_kc_compile_job", retryable=False)
        if job.target_source_revision is None or job.target_knowledge_revision is None or job.lease_owner is None:
            raise KnowledgeJobExecutionError("KC compile job is missing target or lease", code="invalid_kc_compile_target", retryable=False)
        source_revision = job.target_source_revision
        knowledge_revision = job.target_knowledge_revision
        terms = self._store.get_current_terms(job.course_id, source_revision)
        header = self._store.get_current_term_compilation(job.course_id, source_revision)
        if header is None or header.knowledge_revision != knowledge_revision:
            raise KnowledgeJobExecutionError("Current Term projection is absent or stale", code="stale_term_revision", retryable=False)
        components, rejected = build_knowledge_components(
            terms,
            atoms=self._store.get_current_semantic_atoms(job.course_id, source_revision),
            course_id=job.course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
        )
        if not self._store.publish_knowledge_components_if_current(
            course_id=job.course_id, job_id=job.job_id, job_attempt=job.attempt,
            lease_owner=job.lease_owner, source_revision=source_revision,
            knowledge_revision=knowledge_revision, components=components,
            rejected_term_count=rejected,
        ):
            if not self._store.has_current_knowledge_job_lease(
                course_id=job.course_id, job_id=job.job_id, attempt=job.attempt,
                lease_owner=job.lease_owner, source_revision=source_revision,
                knowledge_revision=knowledge_revision,
            ):
                raise KnowledgeJobExecutionError("KC compiler lost its knowledge-job lease", code="knowledge_job_lease_lost", retryable=True)
            raise KnowledgeJobExecutionError("Course source or Term revision changed before KCs could be published", code="stale_kc_source_revision", retryable=False)
