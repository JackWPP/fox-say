"""Validate untrusted atom candidates against current outline evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

from app.schemas.course_projection import CourseOutline
from app.schemas.evidence import EvidenceRef, SourceFragment
from app.schemas.semantic_atoms import SemanticAtom, SemanticAtomCandidate


SEMANTIC_ATOM_COMPILER_VERSION = "semantic-atoms-d1b1"


def build_semantic_atoms(
    candidates: Iterable[SemanticAtomCandidate],
    *,
    course_id: str,
    source_revision: str,
    knowledge_revision: str,
    outline: CourseOutline,
    fragments: Iterable[SourceFragment],
) -> tuple[list[SemanticAtom], int]:
    """Rehydrate only candidates supported by one current outline section."""
    fragment_by_id = {fragment.fragment_id: fragment for fragment in fragments}
    section_fragment_ids = {
        section.section_id: {ref.fragment_id for ref in section.evidence}
        for section in outline.sections
    }
    atoms: list[SemanticAtom] = []
    seen_ids: set[str] = set()
    rejected = 0
    for candidate in candidates:
        statement = _normalise_statement(candidate.statement)
        allowed_ids = section_fragment_ids.get(candidate.section_id)
        evidence_ids = list(dict.fromkeys(candidate.evidence_fragment_ids))
        if not statement or allowed_ids is None or not evidence_ids:
            rejected += 1
            continue
        if any(
            fragment_id not in allowed_ids or fragment_id not in fragment_by_id
            for fragment_id in evidence_ids
        ):
            rejected += 1
            continue
        evidence = [EvidenceRef.from_source_fragment(fragment_by_id[fragment_id]) for fragment_id in evidence_ids]
        atom_id = build_semantic_atom_id(
            course_id=course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            section_id=candidate.section_id,
            atom_type=candidate.atom_type,
            statement=statement,
            evidence_fragment_ids=evidence_ids,
        )
        if atom_id in seen_ids:
            rejected += 1
            continue
        seen_ids.add(atom_id)
        atoms.append(
            SemanticAtom(
                atom_id=atom_id,
                course_id=course_id,
                source_revision=source_revision,
                knowledge_revision=knowledge_revision,
                section_id=candidate.section_id,
                atom_type=candidate.atom_type,
                statement=statement,
                evidence=evidence,
                model_call_id=candidate.model_call_id,
            )
        )
    return atoms, rejected


def build_semantic_atom_id(
    *,
    course_id: str,
    source_revision: str,
    knowledge_revision: str,
    section_id: str,
    atom_type: str,
    statement: str,
    evidence_fragment_ids: Iterable[str],
) -> str:
    payload = json.dumps(
        {
            "course_id": course_id,
            "source_revision": source_revision,
            "knowledge_revision": knowledge_revision,
            "section_id": section_id,
            "atom_type": atom_type,
            "statement": _normalise_statement(statement),
            "evidence_fragment_ids": sorted(set(evidence_fragment_ids)),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"sa_{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _normalise_statement(statement: str) -> str:
    return re.sub(r"\s+", " ", statement).strip()
