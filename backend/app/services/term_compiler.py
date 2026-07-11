"""Rule-only, evidence-literal Atom-to-Term seed compiler for V2."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

from app.schemas.evidence import SourceFragment
from app.schemas.semantic_atoms import SemanticAtom
from app.schemas.knowledge_jobs import KnowledgeJob
from app.schemas.terms import Term, build_term_id, normalise_term_key
from app.services.knowledge_worker import KnowledgeJobExecutionError

if TYPE_CHECKING:
    from app.db.sqlite_store import SqliteStore


_TERM_ATOM_TYPES: set[str] = {"definition", "concept", "formula", "theorem", "procedure"}
_TERM_KIND_PRIORITY: dict[str, int] = {
    "definition": 0,
    "concept": 1,
    "formula": 2,
    "theorem": 3,
    "procedure": 4,
}
_QUOTED_LITERAL = re.compile(r"[“\"「`]([^”\"」`]{1,160})[”\"」`]")
_LEADING_LITERAL = re.compile(
    r"^\s*([^，。；：:（）()]{1,160}?)(?:是指|称为|叫做|定义为|定义成|表示|满足|具有|是)"
)


def build_terms(
    atoms: Iterable[SemanticAtom],
    *,
    course_id: str,
    source_revision: str,
    knowledge_revision: str,
    fragments: Iterable[SourceFragment],
) -> tuple[list[Term], int]:
    """Build one full deterministic projection without inventing terminology.

    An Atom contributes only when a conservative literal from its own statement
    also occurs in every one of its canonical evidence fragments.  This is
    deliberately narrow: terms omitted by this seed pass can be added later by
    an audited disambiguation task, never guessed here.
    """
    fragment_by_id = {fragment.fragment_id: fragment for fragment in fragments}
    groups: dict[str, list[tuple[str, SemanticAtom]]] = defaultdict(list)
    rejected = 0
    for atom in sorted(atoms, key=lambda value: value.atom_id):
        if (
            atom.course_id != course_id
            or atom.source_revision != source_revision
            or atom.knowledge_revision != knowledge_revision
            or atom.atom_type not in _TERM_ATOM_TYPES
        ):
            rejected += 1
            continue
        literal = _literal_term_from_atom(atom, fragment_by_id)
        if literal is None:
            rejected += 1
            continue
        groups[normalise_term_key(literal)].append((literal, atom))

    terms: list[Term] = []
    for canonical_key in sorted(groups):
        contributions = groups[canonical_key]
        canonical_name = min((name for name, _ in contributions), key=lambda value: (value.casefold(), value))
        chosen_name, chosen_atom = min(
            contributions,
            key=lambda item: (_TERM_KIND_PRIORITY[item[1].atom_type], item[1].atom_id),
        )
        del chosen_name
        supporting_atoms = sorted({atom.atom_id: atom for _, atom in contributions}.values(), key=lambda atom: atom.atom_id)
        evidence_by_fragment = {
            evidence.fragment_id: evidence
            for atom in supporting_atoms
            for evidence in atom.evidence
        }
        terms.append(
            Term(
                term_id=build_term_id(
                    course_id=course_id,
                    source_revision=source_revision,
                    knowledge_revision=knowledge_revision,
                    canonical_key=canonical_key,
                ),
                course_id=course_id,
                source_revision=source_revision,
                knowledge_revision=knowledge_revision,
                canonical_name=canonical_name,
                canonical_key=canonical_key,
                term_kind=chosen_atom.atom_type,  # type: ignore[arg-type]
                definition=chosen_atom.statement,
                definition_atom_id=chosen_atom.atom_id,
                supporting_atom_ids=[atom.atom_id for atom in supporting_atoms],
                evidence=[evidence_by_fragment[key] for key in sorted(evidence_by_fragment)],
            )
        )
    return terms, rejected


def _literal_term_from_atom(
    atom: SemanticAtom,
    fragment_by_id: dict[str, SourceFragment],
) -> str | None:
    evidence_texts: list[str] = []
    for evidence in atom.evidence:
        fragment = fragment_by_id.get(evidence.fragment_id)
        if fragment is None:
            return None
        evidence_texts.append(fragment.text)
    candidates = [match.group(1).strip() for match in _QUOTED_LITERAL.finditer(atom.statement)]
    leading = _LEADING_LITERAL.match(atom.statement)
    if leading is not None:
        candidates.append(leading.group(1).strip())
    for candidate in candidates:
        if not candidate or len(candidate) > 160 or not normalise_term_key(candidate):
            continue
        if all(candidate in text for text in evidence_texts):
            return candidate
    return None


class TermCompiler:
    """Publish a zero-model Term projection only for a succeeded semantic parent."""

    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    async def __call__(self, job: KnowledgeJob) -> None:
        if job.job_type != "compile_terms" or job.material_id is not None:
            raise KnowledgeJobExecutionError(
                "Term compiler received a non-course term job",
                code="invalid_term_compile_job",
                retryable=False,
            )
        if job.target_source_revision is None or job.target_knowledge_revision is None:
            raise KnowledgeJobExecutionError(
                "Term compile job is missing its explicit source/knowledge target",
                code="invalid_term_compile_target",
                retryable=False,
            )
        if job.lease_owner is None:
            raise KnowledgeJobExecutionError(
                "Term compiler requires a claimed knowledge-job lease",
                code="invalid_term_compile_lease",
                retryable=False,
            )
        source_revision = job.target_source_revision
        knowledge_revision = job.target_knowledge_revision
        semantic = self._store.get_current_semantic_atom_compilation(job.course_id, source_revision)
        if semantic is None or semantic.knowledge_revision != knowledge_revision:
            raise KnowledgeJobExecutionError(
                "Current semantic Atom projection is absent or no longer matches this Term target",
                code="stale_semantic_atom_revision",
                retryable=False,
            )
        fragments = self._store.list_current_ready_source_fragments(job.course_id)
        atoms = self._store.get_current_semantic_atoms(job.course_id, source_revision)
        terms, rejected_atom_count = build_terms(
            atoms,
            course_id=job.course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            fragments=fragments,
        )
        published = self._store.publish_terms_if_current(
            course_id=job.course_id,
            job_id=job.job_id,
            job_attempt=job.attempt,
            lease_owner=job.lease_owner,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            terms=terms,
            rejected_atom_count=rejected_atom_count,
        )
        if not published:
            if not self._store.has_current_knowledge_job_lease(
                course_id=job.course_id,
                job_id=job.job_id,
                attempt=job.attempt,
                lease_owner=job.lease_owner,
                source_revision=source_revision,
                knowledge_revision=knowledge_revision,
            ):
                raise KnowledgeJobExecutionError(
                    "Term compiler lost its knowledge-job lease before publication",
                    code="knowledge_job_lease_lost",
                    retryable=True,
                )
            raise KnowledgeJobExecutionError(
                "Course source or semantic Atom revision changed before Terms could be published",
                code="stale_term_source_revision",
                retryable=False,
            )
