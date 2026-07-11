"""D1b1 SemanticAtom evidence and publication-fence regressions (zero network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db.sqlite_store import SqliteStore
from app.schemas.evidence import SourceFragment
from app.schemas.foxsay import Course, Material
from app.schemas.semantic_atoms import SemanticAtomCandidate
from app.services.course_compiler import CourseCompiler
from app.services.audited_text_model import AuditedTextResult
from app.services.knowledge_jobs import (
    enqueue_course_compile_job,
    enqueue_material_index_job,
    enqueue_semantic_atom_extraction_job,
)
from app.services.knowledge_worker import KnowledgeJobWorker
from app.services.semantic_atom_compiler import build_semantic_atoms
from app.services.semantic_atom_extractor import SemanticAtomExtractor
from app.services.knowledge_status import build_knowledge_status


class FakeAuditedTextModel:
    def __init__(self, content: str, call_id: str = "audit-semantic") -> None:
        self.content = content
        self.call_id = call_id
        self.messages: list[dict[str, str]] | None = None

    async def complete(self, _job, **kwargs) -> AuditedTextResult:
        self.messages = kwargs["messages"]
        return AuditedTextResult(content=self.content, call_id=self.call_id, usage_source="provider")


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    result = SqliteStore(tmp_path / "semantic-atoms.db")
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
        text="向量空间对线性组合封闭。",
        heading_path=["向量空间"],
        char_start=0,
        char_end=12,
        kind="paragraph",
        parser_name="synthetic-d1b1",
        content_hash="vectors-hash",
    )
    result.replace_source_fragments("linear", "vectors", 1, [fragment])
    index_job = enqueue_material_index_job(
        result, course_id="linear", material_id="vectors", revision=1
    )
    claimed = result.claim_next_knowledge_job("seed-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == index_job.job_id
    result.complete_knowledge_job("linear", index_job.job_id, "seed-worker")
    yield result
    result.close()


async def _current_outline(store: SqliteStore):
    manifest = store.get_compilable_source_manifest("linear")
    assert manifest is not None
    job = enqueue_course_compile_job(
        store, course_id="linear", source_revision=manifest[0]
    )
    worker = KnowledgeJobWorker(
        store, worker_id="outline-worker", handlers={"compile_course": CourseCompiler(store)}
    )
    completed = await worker.run_once()
    assert completed is not None and completed.job_id == job.job_id
    outline = store.get_current_course_outline("linear", manifest[0])
    assert outline is not None
    return manifest[0], outline


def _insert_succeeded_audit(store: SqliteStore, job, call_id: str = "audit-semantic") -> None:
    assert job.target_source_revision is not None
    assert job.target_knowledge_revision is not None
    store._conn.execute(
        """
        INSERT INTO model_call_audits (
            call_id, course_id, job_id, job_attempt, source_revision, knowledge_revision,
            call_kind, purpose, provider, model, request_fingerprint, status,
            input_token_upper_bound, max_output_tokens, reserved_tokens, usage_source,
            accounted_tokens, course_budget_tokens, job_budget_tokens, total_tokens, finished_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'text', 'semantic_atom_extract', 'fake', 'fake-model',
                  ?, 'succeeded', 1, 1, 2, 'provider', 2, 100, 100, 2, datetime('now'))
        """,
        (
            call_id,
            job.course_id,
            job.job_id,
            job.attempt,
            job.target_source_revision,
            job.target_knowledge_revision,
            "a" * 64,
        ),
    )
    store._conn.commit()


async def _claimed_semantic_job(store: SqliteStore):
    source_revision, outline = await _current_outline(store)
    job = enqueue_semantic_atom_extraction_job(
        store,
        course_id="linear",
        source_revision=source_revision,
        knowledge_revision=outline.knowledge_revision,
    )
    claimed = store.claim_next_knowledge_job("semantic-worker", lease_seconds=60)
    assert claimed is not None and claimed.job_id == job.job_id
    _insert_succeeded_audit(store, claimed)
    fragments = store.list_current_ready_source_fragments("linear")
    return claimed, outline, fragments


async def test_semantic_atom_publish_rehydrates_current_evidence_and_is_idempotent(
    store: SqliteStore,
) -> None:
    job, outline, fragments = await _claimed_semantic_job(store)
    candidate = SemanticAtomCandidate(
        atom_type="definition",
        statement="  向量空间对线性组合封闭。  ",
        section_id=outline.sections[0].section_id,
        evidence_fragment_ids=[fragments[0].fragment_id],
        model_call_id="audit-semantic",
    )
    atoms, rejected = build_semantic_atoms(
        [candidate],
        course_id="linear",
        source_revision=job.target_source_revision or "",
        knowledge_revision=job.target_knowledge_revision or "",
        outline=outline,
        fragments=fragments,
    )

    assert rejected == 0 and len(atoms) == 1
    assert store.publish_semantic_atoms_if_current(
        course_id="linear",
        job_id=job.job_id,
        job_attempt=job.attempt,
        lease_owner="semantic-worker",
        source_revision=job.target_source_revision or "",
        knowledge_revision=job.target_knowledge_revision or "",
        atoms=atoms,
        rejected_candidate_count=rejected,
    )
    assert store.publish_semantic_atoms_if_current(
        course_id="linear",
        job_id=job.job_id,
        job_attempt=job.attempt,
        lease_owner="semantic-worker",
        source_revision=job.target_source_revision or "",
        knowledge_revision=job.target_knowledge_revision or "",
        atoms=atoms,
        rejected_candidate_count=rejected,
    )
    store.complete_knowledge_job("linear", job.job_id, "semantic-worker")

    persisted = store.get_current_semantic_atoms("linear", job.target_source_revision or "")
    assert len(persisted) == 1
    assert persisted[0].statement == "向量空间对线性组合封闭。"
    assert persisted[0].evidence[0].fragment_id == fragments[0].fragment_id
    assert persisted[0].evidence[0].course_id == "linear"
    assert store._conn.execute("SELECT COUNT(*) FROM semantic_atoms").fetchone()[0] == 1
    status = build_knowledge_status(store, "linear")
    assert status.semantic_status == "ready"
    assert status.semantic_atom_count == 1


async def test_invalid_candidates_are_rejected_before_any_projection_write(store: SqliteStore) -> None:
    job, outline, fragments = await _claimed_semantic_job(store)
    candidates = [
        SemanticAtomCandidate(
            atom_type="concept",
            statement="跨章节伪造",
            section_id="missing-section",
            evidence_fragment_ids=[fragments[0].fragment_id],
            model_call_id="audit-semantic",
        ),
        SemanticAtomCandidate(
            atom_type="concept",
            statement="未知片段",
            section_id=outline.sections[0].section_id,
            evidence_fragment_ids=["not-current"],
            model_call_id="audit-semantic",
        ),
    ]
    atoms, rejected = build_semantic_atoms(
        candidates,
        course_id="linear",
        source_revision=job.target_source_revision or "",
        knowledge_revision=job.target_knowledge_revision or "",
        outline=outline,
        fragments=fragments,
    )

    assert atoms == [] and rejected == 2
    assert store.publish_semantic_atoms_if_current(
        course_id="linear",
        job_id=job.job_id,
        job_attempt=job.attempt,
        lease_owner="semantic-worker",
        source_revision=job.target_source_revision or "",
        knowledge_revision=job.target_knowledge_revision or "",
        atoms=atoms,
        rejected_candidate_count=rejected,
    )
    assert store._conn.execute("SELECT COUNT(*) FROM semantic_atoms").fetchone()[0] == 0


@pytest.mark.parametrize("failure", ["expired_lease", "stale_source"])
async def test_semantic_atom_publish_fence_writes_nothing_when_target_is_invalid(
    store: SqliteStore, failure: str
) -> None:
    job, outline, fragments = await _claimed_semantic_job(store)
    atoms, _ = build_semantic_atoms(
        [
            SemanticAtomCandidate(
                atom_type="concept",
                statement="向量空间",
                section_id=outline.sections[0].section_id,
                evidence_fragment_ids=[fragments[0].fragment_id],
                model_call_id="audit-semantic",
            )
        ],
        course_id="linear",
        source_revision=job.target_source_revision or "",
        knowledge_revision=job.target_knowledge_revision or "",
        outline=outline,
        fragments=fragments,
    )
    if failure == "expired_lease":
        store._conn.execute(
            "UPDATE knowledge_jobs SET lease_expires_at = datetime('now', '-1 second') WHERE job_id = ?",
            (job.job_id,),
        )
    else:
        store._conn.execute("UPDATE materials SET content_hash = 'new-hash' WHERE id = 'vectors'")
    store._conn.commit()

    assert not store.publish_semantic_atoms_if_current(
        course_id="linear",
        job_id=job.job_id,
        job_attempt=job.attempt,
        lease_owner="semantic-worker",
        source_revision=job.target_source_revision or "",
        knowledge_revision=job.target_knowledge_revision or "",
        atoms=atoms,
        rejected_candidate_count=0,
    )
    assert store._conn.execute("SELECT COUNT(*) FROM semantic_atom_compilations").fetchone()[0] == 0
    assert store._conn.execute("SELECT COUNT(*) FROM semantic_atoms").fetchone()[0] == 0


async def test_semantic_atom_rejects_an_audit_from_another_job(store: SqliteStore) -> None:
    job, outline, fragments = await _claimed_semantic_job(store)
    atoms, _ = build_semantic_atoms(
        [
            SemanticAtomCandidate(
                atom_type="concept",
                statement="向量空间",
                section_id=outline.sections[0].section_id,
                evidence_fragment_ids=[fragments[0].fragment_id],
                model_call_id="wrong-audit",
            )
        ],
        course_id="linear",
        source_revision=job.target_source_revision or "",
        knowledge_revision=job.target_knowledge_revision or "",
        outline=outline,
        fragments=fragments,
    )

    with pytest.raises(ValueError, match="model-call audit"):
        store.publish_semantic_atoms_if_current(
            course_id="linear",
            job_id=job.job_id,
            job_attempt=job.attempt,
            lease_owner="semantic-worker",
            source_revision=job.target_source_revision or "",
            knowledge_revision=job.target_knowledge_revision or "",
            atoms=atoms,
            rejected_candidate_count=0,
        )
    assert store._conn.execute("SELECT COUNT(*) FROM semantic_atom_compilations").fetchone()[0] == 0


async def test_extractor_uses_fake_audited_json_and_only_current_section_fragments(
    store: SqliteStore,
) -> None:
    job, outline, fragments = await _claimed_semantic_job(store)
    model = FakeAuditedTextModel(
        json.dumps(
            {
                "atoms": [
                    {
                        "atom_type": "definition",
                        "statement": "向量空间对线性组合封闭。",
                        "section_id": outline.sections[0].section_id,
                        "evidence_fragment_ids": [fragments[0].fragment_id],
                    }
                ]
            }
        )
    )

    await SemanticAtomExtractor(store, text_model=model)(job)
    store.complete_knowledge_job("linear", job.job_id, "semantic-worker")

    atoms = store.get_current_semantic_atoms("linear", job.target_source_revision or "")
    assert len(atoms) == 1
    assert model.messages is not None
    prompt = model.messages[1]["content"]
    assert fragments[0].fragment_id in prompt
    assert "not-current" not in prompt


async def test_extractor_malformed_json_fails_without_a_projection(store: SqliteStore) -> None:
    job, _, _ = await _claimed_semantic_job(store)
    model = FakeAuditedTextModel("not-json")

    with pytest.raises(Exception, match="not valid JSON") as exc_info:
        await SemanticAtomExtractor(store, text_model=model)(job)

    assert getattr(exc_info.value, "code") == "semantic_atom_output_invalid"
    assert store._conn.execute("SELECT COUNT(*) FROM semantic_atom_compilations").fetchone()[0] == 0
