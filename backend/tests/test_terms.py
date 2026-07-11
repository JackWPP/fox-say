"""D2a rule-derived Term projection regressions (zero network/model calls)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.evidence import SourceFragment
from app.schemas.foxsay import Course, Material
from app.schemas.semantic_atoms import SemanticAtomCandidate
from app.services.course_compiler import CourseCompiler
from app.services.knowledge_jobs import (
    enqueue_course_compile_job,
    enqueue_material_index_job,
    enqueue_semantic_atom_extraction_job,
    enqueue_term_compile_job,
)
from app.services.knowledge_worker import KnowledgeJobWorker
from app.services.semantic_atom_compiler import build_semantic_atoms
from app.services.term_compiler import TermCompiler, build_terms
from app.services.kc_compiler import KnowledgeComponentCompiler


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    result = SqliteStore(tmp_path / "terms.db")
    result.create_course(Course(id="linear", title="线性代数", status="empty"))
    result.create_material(
        Material(
            id="vectors",
            course_id="linear",
            filename="vectors.md",
            kind="text_note",
            status="ready",
            revision=1,
            content_hash="vectors-hash",
        )
    )
    fragment = SourceFragment(
        fragment_id="linear-vectors-0",
        course_id="linear",
        material_id="vectors",
        material_revision=1,
        ordinal=0,
        text="向量空间是对线性组合封闭的集合。",
        heading_path=["向量空间"],
        char_start=0,
        char_end=16,
        kind="paragraph",
        parser_name="synthetic-d2a",
        content_hash="vectors-hash",
    )
    result.replace_source_fragments("linear", "vectors", 1, [fragment])
    index = enqueue_material_index_job(result, course_id="linear", material_id="vectors", revision=1)
    claimed = result.claim_next_knowledge_job("seed-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == index.job_id
    result.complete_knowledge_job("linear", index.job_id, "seed-worker")
    yield result
    result.close()


async def _publish_current_semantic(store: SqliteStore, statement: str):
    manifest = store.get_compilable_source_manifest("linear")
    assert manifest is not None
    outline_job = enqueue_course_compile_job(store, course_id="linear", source_revision=manifest[0])
    outline_worker = KnowledgeJobWorker(
        store, worker_id="outline-worker", handlers={"compile_course": CourseCompiler(store)}
    )
    completed_outline = await outline_worker.run_once()
    assert completed_outline is not None and completed_outline.job_id == outline_job.job_id
    outline = store.get_current_course_outline("linear", manifest[0])
    assert outline is not None
    semantic_job = enqueue_semantic_atom_extraction_job(
        store,
        course_id="linear",
        source_revision=manifest[0],
        knowledge_revision=outline.knowledge_revision,
    )
    semantic = store.claim_next_knowledge_job("semantic-worker", lease_seconds=60)
    assert semantic is not None and semantic.job_id == semantic_job.job_id
    store._conn.execute(
        """
        INSERT INTO model_call_audits (
            call_id, course_id, job_id, job_attempt, source_revision, knowledge_revision,
            call_kind, purpose, provider, model, request_fingerprint, status,
            input_token_upper_bound, max_output_tokens, reserved_tokens, usage_source,
            accounted_tokens, course_budget_tokens, job_budget_tokens, total_tokens, finished_at
        ) VALUES ('audit-terms', 'linear', ?, ?, ?, ?, 'text', 'semantic_atom_extract',
                  'fake', 'fake-model', ?, 'succeeded', 1, 1, 2, 'provider', 2, 100, 100, 2,
                  datetime('now'))
        """,
        (semantic.job_id, semantic.attempt, manifest[0], outline.knowledge_revision, "a" * 64),
    )
    store._conn.commit()
    fragments = store.list_current_ready_source_fragments("linear")
    atoms, rejected = build_semantic_atoms(
        [
            SemanticAtomCandidate(
                atom_type="definition",
                statement=statement,
                section_id=outline.sections[0].section_id,
                evidence_fragment_ids=[fragments[0].fragment_id],
                model_call_id="audit-terms",
            )
        ],
        course_id="linear",
        source_revision=manifest[0],
        knowledge_revision=outline.knowledge_revision,
        outline=outline,
        fragments=fragments,
    )
    assert store.publish_semantic_atoms_if_current(
        course_id="linear",
        job_id=semantic.job_id,
        job_attempt=semantic.attempt,
        lease_owner="semantic-worker",
        source_revision=manifest[0],
        knowledge_revision=outline.knowledge_revision,
        atoms=atoms,
        rejected_candidate_count=rejected,
    )
    return semantic, manifest[0], outline.knowledge_revision, atoms, fragments


async def test_term_child_waits_for_semantic_success_then_publishes_current_terms(
    store: SqliteStore,
) -> None:
    semantic, source_revision, knowledge_revision, _, _ = await _publish_current_semantic(
        store, "向量空间是对线性组合封闭的集合。"
    )
    term_jobs = [job for job in store.list_knowledge_jobs("linear") if job.job_type == "compile_terms"]
    assert len(term_jobs) == 1 and store.claim_next_knowledge_job("term-worker", 60) is None

    store.complete_knowledge_job("linear", semantic.job_id, "semantic-worker")
    term = store.claim_next_knowledge_job("term-worker", 60)
    assert term is not None and term.job_type == "compile_terms"
    await TermCompiler(store)(term)
    assert store.get_current_terms("linear", source_revision) == []
    assert store.claim_next_knowledge_job("kc-worker", 60) is None
    store.complete_knowledge_job("linear", term.job_id, "term-worker")

    terms = store.get_current_terms("linear", source_revision)
    assert len(terms) == 1
    assert terms[0].canonical_name == "向量空间"
    assert terms[0].definition == "向量空间是对线性组合封闭的集合。"
    assert terms[0].knowledge_revision == knowledge_revision
    assert terms[0].evidence[0].fragment_id == "linear-vectors-0"
    assert store.get_current_term_compilation("linear", source_revision) is not None
    assert store._conn.execute("SELECT COUNT(*) FROM term_atom_links").fetchone()[0] == 1

    kc_job = store.claim_next_knowledge_job("kc-worker", 60)
    assert kc_job is not None and kc_job.job_type == "compile_kcs"
    await KnowledgeComponentCompiler(store)(kc_job)
    assert store.get_current_knowledge_components("linear", source_revision) == []
    store.complete_knowledge_job("linear", kc_job.job_id, "kc-worker")
    components = store.get_current_knowledge_components("linear", source_revision)
    assert len(components) == 1
    assert components[0].term_id == terms[0].term_id
    assert components[0].definition == terms[0].definition


async def test_terms_are_deterministic_and_require_literal_current_evidence(store: SqliteStore) -> None:
    semantic, source_revision, knowledge_revision, atoms, fragments = await _publish_current_semantic(
        store, "向量空间是对线性组合封闭的集合。"
    )
    first, rejected = build_terms(
        atoms,
        course_id="linear",
        source_revision=source_revision,
        knowledge_revision=knowledge_revision,
        fragments=fragments,
    )
    second, second_rejected = build_terms(
        list(reversed(atoms)),
        course_id="linear",
        source_revision=source_revision,
        knowledge_revision=knowledge_revision,
        fragments=list(reversed(fragments)),
    )
    assert rejected == second_rejected == 0
    assert [term.model_dump(exclude={"created_at"}) for term in first] == [
        term.model_dump(exclude={"created_at"}) for term in second
    ]

    invalid, invalid_rejected = build_terms(
        [atoms[0].model_copy(update={"statement": "特征值是矩阵的性质。"})],
        course_id="linear",
        source_revision=source_revision,
        knowledge_revision=knowledge_revision,
        fragments=fragments,
    )
    assert invalid == [] and invalid_rejected == 1
    store.complete_knowledge_job("linear", semantic.job_id, "semantic-worker")


@pytest.mark.parametrize("failure", ["expired_lease", "stale_source"])
async def test_term_publication_fence_writes_nothing_when_target_is_invalid(
    store: SqliteStore, failure: str
) -> None:
    semantic, source_revision, knowledge_revision, atoms, fragments = await _publish_current_semantic(
        store, "向量空间是对线性组合封闭的集合。"
    )
    store.complete_knowledge_job("linear", semantic.job_id, "semantic-worker")
    term_job = store.claim_next_knowledge_job("term-worker", 60)
    assert term_job is not None
    terms, rejected = build_terms(
        atoms,
        course_id="linear",
        source_revision=source_revision,
        knowledge_revision=knowledge_revision,
        fragments=fragments,
    )
    if failure == "expired_lease":
        store._conn.execute(
            "UPDATE knowledge_jobs SET lease_expires_at = datetime('now', '-1 second') WHERE job_id = ?",
            (term_job.job_id,),
        )
    else:
        store._conn.execute("UPDATE materials SET content_hash = 'changed' WHERE id = 'vectors'")
    store._conn.commit()
    assert not store.publish_terms_if_current(
        course_id="linear",
        job_id=term_job.job_id,
        job_attempt=term_job.attempt,
        lease_owner="term-worker",
        source_revision=source_revision,
        knowledge_revision=knowledge_revision,
        terms=terms,
        rejected_atom_count=rejected,
    )
    assert store._conn.execute("SELECT COUNT(*) FROM term_compilations").fetchone()[0] == 0
    assert store._conn.execute("SELECT COUNT(*) FROM terms").fetchone()[0] == 0
    assert store._conn.execute("SELECT COUNT(*) FROM term_atom_links").fetchone()[0] == 0


async def test_zero_terms_is_a_succeeded_empty_projection(store: SqliteStore) -> None:
    semantic, source_revision, knowledge_revision, _, _ = await _publish_current_semantic(
        store, "向量空间对线性组合封闭。"
    )
    store.complete_knowledge_job("linear", semantic.job_id, "semantic-worker")
    term = store.claim_next_knowledge_job("term-worker", 60)
    assert term is not None
    await TermCompiler(store)(term)
    store.complete_knowledge_job("linear", term.job_id, "term-worker")
    compilation = store.get_current_term_compilation("linear", source_revision)
    assert compilation is not None
    assert compilation.term_count == 0 and compilation.rejected_atom_count == 1
    assert store.get_current_terms("linear", source_revision) == []


def test_term_job_identity_is_course_and_source_scoped(store: SqliteStore) -> None:
    first = enqueue_term_compile_job(
        store, course_id="linear", source_revision="source-a", knowledge_revision="knowledge-a"
    )
    duplicate = enqueue_term_compile_job(
        store, course_id="linear", source_revision="source-a", knowledge_revision="knowledge-a"
    )
    assert first.job_id == duplicate.job_id and first.token_budget is None
    with pytest.raises(ValueError, match="idempotency key"):
        enqueue_term_compile_job(
            store, course_id="linear", source_revision="source-a", knowledge_revision="knowledge-b"
        )
