"""Minimal D3b relation-candidate evidence boundary regression."""

from app.schemas.evidence import EvidenceRef, SourceFragment
from app.schemas.knowledge_components import KnowledgeComponent
from app.schemas.kc_relations import KCRelationCandidate
from app.services.kc_relation_extractor import build_kc_relations, build_relation_candidates


def _fragment() -> SourceFragment:
    return SourceFragment(
        fragment_id="fragment-1",
        course_id="linear",
        material_id="notes",
        material_revision=1,
        ordinal=0,
        text="向量空间的子空间必须满足向量空间的封闭性。",
        heading_path=["向量空间"],
        char_start=0,
        char_end=22,
        kind="paragraph",
        parser_name="test",
        content_hash="hash-1",
    )


def _component(kc_id: str, term_id: str, name: str, evidence: EvidenceRef) -> KnowledgeComponent:
    return KnowledgeComponent(
        kc_id=kc_id,
        course_id="linear",
        source_revision="src-1",
        knowledge_revision="kn-1",
        term_id=term_id,
        name=name,
        kind="concept",
        definition=f"{name} 的定义。",
        section_id="section-1",
        evidence=[evidence],
    )


def test_kc_relation_accepts_only_literal_current_cooccurrence() -> None:
    fragment = _fragment()
    evidence = EvidenceRef.from_source_fragment(fragment)
    candidates = build_relation_candidates(
        [_component("kc-space", "term-space", "向量空间", evidence), _component("kc-subspace", "term-sub", "子空间", evidence)],
        [fragment],
    )
    assert len(candidates) == 1

    relations, rejected = build_kc_relations(
        [KCRelationCandidate(
            source_kc_id="kc-space", target_kc_id="kc-subspace", relation_type="prerequisite",
            evidence_fragment_id="fragment-1", model_call_id="audit-1",
        )],
        allowed_pairs=candidates,
        course_id="linear",
        source_revision="src-1",
        knowledge_revision="kn-1",
        fragments=[fragment],
    )
    assert rejected == 0 and len(relations) == 1

    invalid, invalid_rejected = build_kc_relations(
        [KCRelationCandidate(
            source_kc_id="kc-space", target_kc_id="kc-subspace", relation_type="related",
            evidence_fragment_id="forged-fragment", model_call_id="audit-1",
        )],
        allowed_pairs=candidates,
        course_id="linear",
        source_revision="src-1",
        knowledge_revision="kn-1",
        fragments=[fragment],
    )
    assert invalid == [] and invalid_rejected == 1
