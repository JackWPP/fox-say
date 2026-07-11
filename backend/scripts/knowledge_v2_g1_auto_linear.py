"""Offline rehearsal for the one-request Knowledge V2 G1 acceptance run.

The default is deliberately a *dry* harness: it creates a disposable SQLite
database, uses a local single-response OpenAI-shaped client, and never contacts
a provider.  ``--real`` is the sole explicit opt-in for one real DeepSeek call.
It proves the durable automatic hand-off:

``D0 outline -> auto semantic job -> audited semantic publish -> auto Term job``.

Do not add an implicit live mode here: an acceptance harness must not spend a
user's model budget merely because it was invoked.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.db.sqlite_store import SqliteStore
from app.schemas.evidence import SourceFragment
from app.schemas.foxsay import Course, Material
from app.schemas.knowledge_jobs import KnowledgeJobCreate
from app.services.audited_text_model import AuditedDeepSeekTextModel
from app.services.course_compiler import CourseCompiler
from app.services.kc_compiler import KnowledgeComponentCompiler
from app.services.knowledge_worker import KnowledgeJobWorker
from app.services.semantic_atom_extractor import SemanticAtomExtractor
from app.services.source_revision import build_knowledge_revision
from app.services.term_compiler import TermCompiler


_COURSE_ID = "g1-linear-algebra"
_MATERIAL_ID = "g1-vector-space"
_SEMANTIC_JOB_BUDGET = 4_000
_COURSE_BUDGET = 4_000


@dataclass(frozen=True)
class G1Result:
    """Sanitised observables for one disposable G1 chain run."""

    outline_job_status: str
    semantic_job_status: str
    term_job_status: str
    kc_job_status: str
    provider_request_count: int
    provider: str
    model: str
    semantic_job_token_budget: int | None
    audit_status: str
    audit_reserved_tokens: int
    audit_accounted_tokens: int
    audit_input_tokens: int | None
    audit_output_tokens: int | None
    audit_total_tokens: int | None
    audit_elapsed_ms: int | None
    semantic_atom_count: int
    term_count: int
    kc_count: int
    temporary_db_cleaned: bool


class _SingleSyntheticCompletionClient:
    """One deterministic local completion with an OpenAI-compatible shape."""

    def __init__(self) -> None:
        self.request_count = 0
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> Any:
        self.request_count += 1
        if self.request_count > 1:
            raise AssertionError("G1 rehearsal permits exactly one semantic model request")
        messages = kwargs["messages"]
        payload = json.loads(messages[1]["content"])
        section = payload["sections"][0]
        fragment_id = section["fragments"][0]["fragment_id"]
        content = json.dumps(
            {
                "atoms": [
                    {
                        "atom_type": "definition",
                        "statement": "向量空间是对加法与数乘封闭的集合。",
                        "section_id": section["section_id"],
                        "evidence_fragment_ids": [fragment_id],
                    }
                ]
            },
            ensure_ascii=False,
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(
                prompt_tokens=220,
                completion_tokens=80,
                total_tokens=300,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
            ),
        )


def _enqueue_seed_index_job(store: SqliteStore) -> None:
    index_job = store.enqueue_knowledge_job(
        KnowledgeJobCreate(
            job_id="g1-index-job",
            course_id=_COURSE_ID,
            material_id=_MATERIAL_ID,
            job_type="index_material",
            revision=1,
            scope="material",
            idempotency_key="knowledge:index_material:g1-linear-algebra:g1-vector-space:r1",
            token_budget=None,
            max_attempts=1,
        )
    )
    claimed = store.claim_next_knowledge_job("g1-seed-worker", lease_seconds=60)
    if claimed is None or claimed.job_id != index_job.job_id:
        raise RuntimeError("G1 rehearsal could not claim its synthetic material index job")
    store.complete_knowledge_job(_COURSE_ID, index_job.job_id, "g1-seed-worker")


def _enqueue_outline_job(store: SqliteStore, source_revision: str) -> str:
    knowledge_revision = build_knowledge_revision(
        source_revision=source_revision,
        compiler_version="course-outline-d0",
    )
    job = store.enqueue_knowledge_job(
        KnowledgeJobCreate(
            job_id="g1-outline-job",
            course_id=_COURSE_ID,
            material_id=None,
            job_type="compile_course",
            revision=None,
            scope="course",
            idempotency_key=f"knowledge:compile_course:{_COURSE_ID}:source:{source_revision}",
            token_budget=None,
            max_attempts=1,
            target_source_revision=source_revision,
            target_knowledge_revision=knowledge_revision,
        )
    )
    return job.job_id


async def _run_g1(*, real: bool) -> G1Result:
    """Run one disposable, no-network automatic-chain rehearsal.

    The temporary directory owns the SQLite file, and is removed before this
    function returns.  It neither reads nor prints environment configuration,
    prompts, source payloads, credentials, or model output.
    """
    result: G1Result | None = None
    temp_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="foxsay-g1-") as temp_dir:
        temp_path = Path(temp_dir)
        db_path = Path(temp_dir) / "g1-linear.db"
        store = SqliteStore(db_path)
        try:
            store.create_course(Course(id=_COURSE_ID, title="合成线性代数 G1", status="empty"))
            store.create_material(
                Material(
                    id=_MATERIAL_ID,
                    course_id=_COURSE_ID,
                    filename="synthetic-vector-space.md",
                    kind="text_note",
                    status="ready",
                    revision=1,
                    content_hash="g1-synthetic-vector-space-v1",
                )
            )
            store.replace_source_fragments(
                _COURSE_ID,
                _MATERIAL_ID,
                1,
                [
                    SourceFragment(
                        fragment_id="g1-vector-space-fragment-0",
                        course_id=_COURSE_ID,
                        material_id=_MATERIAL_ID,
                        material_revision=1,
                        ordinal=0,
                        text="向量空间是对加法与数乘封闭的集合。",
                        heading_path=["向量空间"],
                        char_start=0,
                        char_end=17,
                        kind="paragraph",
                        parser_name="g1-offline-synthetic",
                        content_hash="g1-synthetic-vector-space-v1",
                    )
                ],
            )
            _enqueue_seed_index_job(store)
            manifest = store.get_compilable_source_manifest(_COURSE_ID)
            if manifest is None:
                raise RuntimeError("G1 rehearsal did not produce a compilable synthetic source")
            outline_job_id = _enqueue_outline_job(store, manifest[0])

            client: _SingleSyntheticCompletionClient | None = None
            if real:
                # This import/configuration path is reachable only after the
                # caller explicitly selected --real.  No key is printed.
                from openai import OpenAI

                from app.core.config import settings

                if not settings.deepseek_api_key:
                    raise RuntimeError("--real requires configured DEEPSEEK_API_KEY")
                model = AuditedDeepSeekTextModel(
                    store,
                    client=OpenAI(
                        api_key=settings.deepseek_api_key,
                        base_url=settings.deepseek_api_base,
                        timeout=settings.knowledge_model_timeout_seconds,
                        max_retries=0,
                    ),
                    model=settings.deepseek_model,
                    provider="deepseek",
                    course_budget_tokens=_COURSE_BUDGET,
                )
            else:
                client = _SingleSyntheticCompletionClient()
                model = AuditedDeepSeekTextModel(
                    store,
                    client=client,
                    model="g1-offline-synthetic",
                    provider="offline-g1",
                    course_budget_tokens=_COURSE_BUDGET,
                )
            worker = KnowledgeJobWorker(
                store,
                worker_id="g1-rehearsal-worker",
                lease_seconds=60,
                handlers={
                    "compile_course": CourseCompiler(
                        store,
                        auto_enqueue_semantic=True,
                        semantic_token_budget=_SEMANTIC_JOB_BUDGET,
                        semantic_max_attempts=1,
                    ),
                    "extract_semantic_atoms": SemanticAtomExtractor(store, text_model=model),
                    "compile_terms": TermCompiler(store),
                    "compile_kcs": KnowledgeComponentCompiler(store),
                },
            )
            for _ in range(4):
                completed = await worker.run_once()
                if completed is None:
                    raise RuntimeError("G1 rehearsal automatic chain stopped before completion")

            jobs = {job.job_type: job for job in store.list_knowledge_jobs(_COURSE_ID)}
            semantic_job = jobs.get("extract_semantic_atoms")
            term_job = jobs.get("compile_terms")
            kc_job = jobs.get("compile_kcs")
            outline_job = store.get_knowledge_job(_COURSE_ID, outline_job_id)
            if outline_job is None or semantic_job is None or term_job is None or kc_job is None:
                raise RuntimeError("G1 rehearsal did not persist every expected durable job")
            if any(job.status != "succeeded" for job in (outline_job, semantic_job, term_job, kc_job)):
                raise RuntimeError("G1 rehearsal did not complete every expected durable job")
            if client is not None and client.request_count != 1:
                raise RuntimeError("G1 rehearsal made an unexpected number of synthetic provider requests")
            audits = store.list_model_call_audits(_COURSE_ID, job_id=semantic_job.job_id)
            if len(audits) != 1 or audits[0].status != "succeeded":
                raise RuntimeError("G1 rehearsal lacks one succeeded semantic model audit")
            atoms = store.get_current_semantic_atoms(_COURSE_ID, manifest[0])
            terms = store.get_current_terms(_COURSE_ID, manifest[0])
            components = store.get_current_knowledge_components(_COURSE_ID, manifest[0])
            if not real and (len(atoms) != 1 or len(terms) != 1 or len(components) != 1):
                raise RuntimeError("G1 rehearsal did not publish the expected Atom, Term, and KC")
            result = G1Result(
                outline_job_status=outline_job.status,
                semantic_job_status=semantic_job.status,
                term_job_status=term_job.status,
                kc_job_status=kc_job.status,
                provider_request_count=len(audits),
                provider=audits[0].provider,
                model=audits[0].model,
                semantic_job_token_budget=semantic_job.token_budget,
                audit_status=audits[0].status,
                audit_reserved_tokens=audits[0].reserved_tokens,
                audit_accounted_tokens=audits[0].accounted_tokens,
                audit_input_tokens=audits[0].input_tokens,
                audit_output_tokens=audits[0].output_tokens,
                audit_total_tokens=audits[0].total_tokens,
                audit_elapsed_ms=audits[0].elapsed_ms,
                semantic_atom_count=len(atoms),
                term_count=len(terms),
                kc_count=len(components),
                temporary_db_cleaned=False,
            )
        finally:
            store.close()
    if result is None or temp_path is None:
        raise RuntimeError("G1 rehearsal completed without a result")
    if temp_path.exists():
        raise RuntimeError("G1 rehearsal did not clean up its temporary SQLite directory")
    return replace(result, temporary_db_cleaned=True)


async def run_offline_g1_rehearsal() -> G1Result:
    """Run the default no-network rehearsal used by automated tests."""
    return await _run_g1(real=False)


async def run_real_g1_acceptance() -> G1Result:
    """Run exactly one explicitly requested real DeepSeek G1 request."""
    return await _run_g1(real=True)


async def _main(*, real: bool) -> None:
    result = await (run_real_g1_acceptance() if real else run_offline_g1_rehearsal())
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Knowledge V2 G1 automatic-chain harness")
    parser.add_argument(
        "--real",
        action="store_true",
        help="explicitly make one audited DeepSeek request; default is no-network offline mode",
    )
    args = parser.parse_args()
    asyncio.run(_main(real=args.real))
