"""Disposable V2-E1 visual-analysis acceptance harness.

The default invocation is entirely offline.  It creates a synthetic vector
diagram PNG, a temporary upload root and SQLite database, then runs the real
persisted ``VisualAnalysis`` handler against one deterministic fake VLM
response.  ``--real`` is the sole opt-in for one SiliconFlow request using the
existing ``.env`` VLM configuration.  It never prints credentials, image
bytes, prompts, or model output.
"""

from __future__ import annotations

import argparse
import asyncio
import binascii
import json
import struct
import tempfile
import zlib
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

from app.core.config import settings
from app.db.sqlite_store import SqliteStore
from app.schemas.evidence import SourceFragment
from app.schemas.foxsay import Course, Material
from app.services.knowledge_jobs import enqueue_material_index_job
from app.services.knowledge_worker import KnowledgeJobWorker
from app.services.visual_analysis import VisualAnalysis


_COURSE_ID = "e1-linear-algebra"
_MATERIAL_ID = "e1-vector-diagram"
_VISUAL_JOB_BUDGET = 3_600
_VISUAL_INPUT_RESERVE = 2_400
_VISUAL_MAX_OUTPUT = 1_200


@dataclass(frozen=True)
class E1Result:
    """Sanitised observables from one disposable V2-E1 run."""

    visual_job_status: str
    provider_request_count: int
    provider: str
    model: str
    visual_job_token_budget: int | None
    audit_status: str
    audit_reserved_tokens: int
    audit_accounted_tokens: int
    audit_input_tokens: int | None
    audit_output_tokens: int | None
    audit_total_tokens: int | None
    audit_elapsed_ms: int | None
    result_count: int
    temporary_artifacts_cleaned: bool


class _SingleSyntheticVisionClient:
    """A local OpenAI-shaped VLM client which permits exactly one request."""

    def __init__(self) -> None:
        self.request_count = 0
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> Any:
        self.request_count += 1
        if self.request_count > 1:
            raise AssertionError("E1 offline rehearsal permits exactly one VLM request")
        messages = kwargs["messages"]
        if len(messages) != 1 or len(messages[0]["content"]) != 2:
            raise AssertionError("E1 must provide one image and one recovery instruction")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content="图中有原点、坐标轴与一个从原点指向右上的向量。"
            ))],
            usage=SimpleNamespace(
                prompt_tokens=180,
                completion_tokens=40,
                total_tokens=220,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
            ),
        )


@contextmanager
def _temporary_visual_settings(upload_root: Path, *, offline: bool) -> Iterator[None]:
    """Keep the acceptance cap local to this disposable process/run."""
    overrides = {
        "upload_root": str(upload_root),
        "knowledge_visual_input_token_reserve": _VISUAL_INPUT_RESERVE,
        "vlm_max_tokens": _VISUAL_MAX_OUTPUT,
    }
    if offline:
        # The production handler intentionally checks this even with a passed
        # client.  A non-secret marker lets the no-network fake exercise the
        # same guard without requiring a developer's .env configuration.
        overrides["vlm_api_key"] = "offline-e1-no-network"
    old_values = {name: getattr(settings, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(settings, name, value)
        yield
    finally:
        for name, value in old_values.items():
            setattr(settings, name, value)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data)) + kind + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def _write_synthetic_linear_algebra_png(path: Path) -> None:
    """Write a tiny dependency-free axes-and-vector PNG with no user data."""
    width, height = 120, 80
    pixels = bytearray([250, 248, 242] * width * height)

    def put(x: int, y: int, rgb: tuple[int, int, int]) -> None:
        if 0 <= x < width and 0 <= y < height:
            offset = (y * width + x) * 3
            pixels[offset:offset + 3] = bytes(rgb)

    # Coordinate axes and an upward-right vector, enough to exercise a real
    # image data URL without embedding course materials or readable text.
    origin_x, origin_y = 24, 59
    for x in range(8, 112):
        put(x, origin_y, (60, 60, 60))
    for y in range(8, 70):
        put(origin_x, y, (60, 60, 60))
    for step in range(48):
        put(origin_x + step, origin_y - step // 2, (202, 79, 35))
    put(72, 35, (202, 79, 35))
    put(71, 36, (202, 79, 35))
    put(72, 36, (202, 79, 35))
    raw = b"".join(
        b"\x00" + bytes(pixels[row * width * 3:(row + 1) * width * 3])
        for row in range(height)
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _seed_visual_input(store: SqliteStore, upload_root: Path) -> None:
    store.create_course(Course(id=_COURSE_ID, title="合成线性代数 E1", status="empty"))
    store.create_material(Material(
        id=_MATERIAL_ID,
        course_id=_COURSE_ID,
        filename="synthetic-vector-diagram.md",
        kind="text_note",
        status="ready",
        revision=1,
        content_hash="e1-synthetic-vector-diagram-v1",
    ))
    store.replace_source_fragments(_COURSE_ID, _MATERIAL_ID, 1, [SourceFragment(
        fragment_id="e1-vector-fragment-0",
        course_id=_COURSE_ID,
        material_id=_MATERIAL_ID,
        material_revision=1,
        ordinal=0,
        text="下图是一个向量的坐标示意。",
        heading_path=["向量"],
        char_start=0,
        char_end=13,
        kind="figure_context",
        parser_name="e1-offline-synthetic",
        content_hash="e1-synthetic-vector-diagram-v1",
    )])
    index_job = enqueue_material_index_job(
        store, course_id=_COURSE_ID, material_id=_MATERIAL_ID, revision=1, max_attempts=1,
    )
    claimed = store.claim_next_knowledge_job("e1-seed-worker", lease_seconds=60)
    if claimed is None or claimed.job_id != index_job.job_id:
        raise RuntimeError("E1 could not claim its synthetic material index job")
    store.complete_knowledge_job(_COURSE_ID, index_job.job_id, "e1-seed-worker")
    relative_asset_path = "e1/vector-diagram.png"
    _write_synthetic_linear_algebra_png(upload_root / relative_asset_path)
    store.replace_extracted_assets([{
        "element_id": "e1-vector-diagram-asset",
        "element_type": "Figure",
        "sequential_label": "图1",
        "page_number": 1,
        "source_chapter": "向量",
        "storage_path": relative_asset_path,
        "alt_text": "",
    }], _COURSE_ID, _MATERIAL_ID, "e1-synthetic-document")


async def _run_e1(*, real: bool) -> E1Result:
    """Run one one-asset V2-E1 acceptance chain in a temporary directory."""
    result: E1Result | None = None
    temporary_root: Path | None = None
    with tempfile.TemporaryDirectory(prefix="foxsay-e1-") as temp_dir:
        temporary_root = Path(temp_dir)
        store = SqliteStore(temporary_root / "e1.sqlite")
        try:
            with _temporary_visual_settings(temporary_root / "uploads", offline=not real):
                if real and not settings.resolved_vlm_api_key.strip():
                    raise RuntimeError("--real requires configured VLM_API_KEY or EMBEDDING_API_KEY")
                _seed_visual_input(store, Path(settings.upload_root))
                job = store.enqueue_visual_analysis_job(
                    course_id=_COURSE_ID,
                    asset_requests=[{
                        "asset_id": "e1-vector-diagram-asset",
                        "reason_code": "unreadable_diagram",
                    }],
                    token_budget=_VISUAL_JOB_BUDGET,
                    max_attempts=1,
                )
                client: _SingleSyntheticVisionClient | None = None
                if real:
                    handler = VisualAnalysis(store, enabled=True)
                else:
                    client = _SingleSyntheticVisionClient()
                    handler = VisualAnalysis(store, enabled=True, client=client)
                worker = KnowledgeJobWorker(
                    store,
                    worker_id="e1-rehearsal-worker",
                    lease_seconds=60,
                    handlers={"visual_analysis": handler},
                )
                completed = await worker.run_once()
                if completed is None or completed.job_id != job.job_id:
                    raise RuntimeError("E1 did not execute its persisted visual job")
                finished = store.get_knowledge_job(_COURSE_ID, job.job_id)
                audits = store.list_model_call_audits(_COURSE_ID, job_id=job.job_id)
                results = store.get_visual_analysis_results(_COURSE_ID, job.job_id)
                if finished is None or finished.status != "succeeded":
                    raise RuntimeError("E1 visual job did not succeed")
                if len(audits) != 1 or audits[0].status != "succeeded":
                    raise RuntimeError("E1 requires exactly one succeeded visual model audit")
                if len(results) != 1:
                    raise RuntimeError("E1 requires exactly one persisted visual result")
                if client is not None and client.request_count != 1:
                    raise RuntimeError("E1 made an unexpected number of fake VLM requests")
                audit = audits[0]
                result = E1Result(
                    visual_job_status=finished.status,
                    provider_request_count=len(audits),
                    provider=audit.provider,
                    model=audit.model,
                    visual_job_token_budget=finished.token_budget,
                    audit_status=audit.status,
                    audit_reserved_tokens=audit.reserved_tokens,
                    audit_accounted_tokens=audit.accounted_tokens,
                    audit_input_tokens=audit.input_tokens,
                    audit_output_tokens=audit.output_tokens,
                    audit_total_tokens=audit.total_tokens,
                    audit_elapsed_ms=audit.elapsed_ms,
                    result_count=len(results),
                    temporary_artifacts_cleaned=False,
                )
        finally:
            store.close()
    if result is None or temporary_root is None or temporary_root.exists():
        raise RuntimeError("E1 did not clean up its temporary SQLite and upload artifacts")
    return replace(result, temporary_artifacts_cleaned=True)


async def run_offline_e1_rehearsal() -> E1Result:
    """Run the no-network E1 rehearsal used by automated tests."""
    return await _run_e1(real=False)


async def run_real_e1_acceptance() -> E1Result:
    """Run exactly one explicitly requested SiliconFlow VLM request."""
    return await _run_e1(real=True)


async def _main(*, real: bool) -> None:
    result = await (run_real_e1_acceptance() if real else run_offline_e1_rehearsal())
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Knowledge V2 E1 visual harness")
    parser.add_argument(
        "--real",
        action="store_true",
        help="explicitly make one SiliconFlow VLM request; default is offline and no-network",
    )
    args = parser.parse_args()
    asyncio.run(_main(real=args.real))
