"""line A — KC 先修关系离线 ETL 脚手架 (MVP)。

职责:对单门课程下所有 KC 的 `prerequisites_raw: list[str]`,
通过 cosine 相似度 + Qwen fast-judge 二级分流,产出结构化的
`prerequisites: list[KCPrerequisite]`,并写回 store。

算法:
1. embed_texts([prereq_name]) → query embedding
2. 同 course 每个 KC → embed_texts([kc.name]) → candidate embedding
3. 取 cosine 最高的候选:
   - sim >= auto_threshold (默认 0.85) → source="etl_auto", strength=sim
   - judge_threshold <= sim < auto_threshold → 调 qwen3-4b fast judge
       YES → source="etl_judge_reviewed", strength=sim
       NO  → unaligned
   - sim < judge_threshold → unaligned

输出(每个 course_id 一次运行):
- data/alignment_reports/<course>_<utc-iso>.json     — 统计 + 摘要
- data/alignment_reports/<course>_needs_review.jsonl — 未对齐的 prereq

非 --dry-run 模式调 store.save_kc(updated_kc)。

HEC:
- HEC-1:LLM/embedding 失败抛(不静默)
- HEC-6:显式 course_id
- HEC-7:只用既有依赖(openai / pydantic),不装新包
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

# 允许 `python -m backend.scripts.align_prerequisites` 直接跑
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.schemas.foxsay import KC, KCPrerequisite, PrereqSource  # noqa: E402

logger = logging.getLogger("align_prerequisites")

NAMESPACE_DMAP = uuid.UUID("12345678-1234-5678-1234-567812345678")

DEFAULT_AUTO_THRESHOLD = 0.85
DEFAULT_JUDGE_THRESHOLD = 0.60

REPORT_DIR = _PROJECT_ROOT / "data" / "alignment_reports"


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    """标准 cosine 相似度。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Judge client (Qwen fast / main via LM Studio)
# ---------------------------------------------------------------------------


def _get_judge_client() -> OpenAI:
    """LM Studio OpenAI 兼容客户端。失败由调用方决定(HEC-1)。"""
    return OpenAI(
        api_key=settings.judge_api_key or "lm-studio",
        base_url=settings.judge_api_base,
    )


def _judge_same_concept(
    prereq_name: str,
    candidate_name: str,
    *,
    client: OpenAI | None = None,
) -> bool:
    """Qwen fast judge:判定两个概念是否同一。

    prompt 极简:希望模型只在最后一词输出 YES / NO。
    """
    client = client or _get_judge_client()
    prompt = (
        "判断下面两个概念是否同一概念(同义或极近义)。\n"
        f"概念 A: {prereq_name}\n"
        f"概念 B: {candidate_name}\n"
        "同一概念? 只回答 YES 或 NO,不要其他内容。"
    )
    response = client.chat.completions.create(
        model=settings.judge_fast_model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=8,
    )
    content = (response.choices[0].message.content or "").strip().upper()
    if "YES" in content and "NO" not in content:
        return True
    if "NO" in content:
        return False
    # 无法解析 → 默认 NO (HEC-1:保守,不静默通过)
    logger.warning("Judge 返回非 YES/NO: %r — 视为 NO", content)
    return False


# ---------------------------------------------------------------------------
# Core alignment
# ---------------------------------------------------------------------------


def _kc_id_for_name(course_id: str, chapter_id: str, name: str) -> str:
    """对齐 KC.id 的稳定计算(uuid5)。与 schemas/foxsay.py NAMESPACE 一致。

    注意:实际 ETL 应优先用 store 中真实 KC.id;此处仅在 fuzzy fallback 时用。
    """
    raw = f"{course_id}:{chapter_id}:{name}"
    return str(uuid.uuid5(NAMESPACE_DMAP, raw))


def _align_one_prereq(
    prereq_name: str,
    candidates: list[tuple[str, str, list[float]]],
    qvec: list[float],
    *,
    auto_threshold: float,
    judge_threshold: float,
    judge_client: OpenAI | None,
    exclude_kc_id: str | None = None,
    dry_run: bool,
) -> tuple[KCPrerequisite | None, str]:
    """对单条 prereq_name 找最佳候选 KC。

    返回 (kcprereq_or_None, reason)。
    reason ∈ {"auto", "judge_yes", "judge_no", "below_threshold", "no_candidates"}
    exclude_kc_id: 不参与候选(防止 KC 把自己当作自己的 prereq)。
    """
    if not candidates:
        return None, "no_candidates"

    best_sim = -1.0
    best_kc_id: str | None = None
    for kc_id, _kc_name, cvec in candidates:
        if exclude_kc_id is not None and kc_id == exclude_kc_id:
            continue
        sim = _cosine(qvec, cvec)
        if sim > best_sim:
            best_sim = sim
            best_kc_id = kc_id

    if best_kc_id is None:
        return None, "no_candidates"

    if best_sim >= auto_threshold:
        return (
            KCPrerequisite(
                prerequisite_kc_id=best_kc_id,
                dependency_strength=float(best_sim),
                source="etl_auto",
            ),
            "auto",
        )

    if best_sim >= judge_threshold:
        # 找原始 candidate name 用于 prompt
        candidate_name = next(
            (n for k, n, _ in candidates if k == best_kc_id), prereq_name
        )
        same = _judge_same_concept(
            prereq_name, candidate_name, client=judge_client
        )
        if same:
            return (
                KCPrerequisite(
                    prerequisite_kc_id=best_kc_id,
                    dependency_strength=float(best_sim),
                    source="etl_judge_reviewed",
                ),
                "judge_yes",
            )
        return None, "judge_no"

    return None, "below_threshold"


def align_course_kcs(
    course_id: str,
    *,
    store: object,
    embed_fn: object,
    judge_client: OpenAI | None = None,
    auto_threshold: float = DEFAULT_AUTO_THRESHOLD,
    judge_threshold: float = DEFAULT_JUDGE_THRESHOLD,
    dry_run: bool = False,
) -> dict:
    """对一门课程的所有 KC 做 prereq 对齐,返回报告 dict。

    store: 必须实现 get_kcs_by_course(course_id) -> list[KC]
           可选 save_kc(kc) (non-dry-run 调)
    embed_fn: callable(list[str]) -> list[list[float]] (注入方便 mock)
    """
    if auto_threshold <= judge_threshold:
        raise ValueError(
            f"auto_threshold ({auto_threshold}) 必须 > judge_threshold ({judge_threshold})"
        )

    kcs: list[KC] = store.get_kcs_by_course(course_id)  # type: ignore[attr-defined]
    if not kcs:
        logger.info("课程 %s 没有 KC", course_id)
        return {
            "course_id": course_id,
            "total_kcs": 0,
            "total_prereqs_raw": 0,
            "auto_accepted": 0,
            "judge_accepted": 0,
            "unaligned": 0,
            "updated_kcs": 0,
            "dry_run": dry_run,
            "needs_review": [],
        }

    # 1. 收集所有 candidate name + 所有 prereq name,一次性 embed
    candidate_names: list[str] = []
    candidate_kc_ids: list[str] = []
    for kc in kcs:
        candidate_names.append(kc.name)
        candidate_kc_ids.append(kc.id)

    candidate_embs = embed_fn(candidate_names)

    # 同 course 下,每条 KC 都可能挂 prerequisites_raw;逐条处理
    prereq_queries: list[tuple[int, str]] = []  # (kc_index, prereq_name)
    for idx, kc in enumerate(kcs):
        for raw in kc.prerequisites_raw:
            prereq_queries.append((idx, raw))

    if prereq_queries:
        prereq_embs = embed_fn([p for _, p in prereq_queries])
    else:
        prereq_embs = []

    # 2. 分流
    needs_review: list[dict] = []
    updated_kcs_count = 0
    auto_accepted = 0
    judge_accepted = 0
    unaligned = 0

    # per-kc 收集新 prerequisites
    new_prereqs_per_kc: dict[int, list[KCPrerequisite]] = {i: [] for i in range(len(kcs))}

    for (kc_idx, prereq_name), qvec in zip(prereq_queries, prereq_embs):
        candidates = list(zip(candidate_kc_ids, candidate_names, candidate_embs))
        kcprereq, reason = _align_one_prereq(
            prereq_name,
            candidates,
            qvec,
            auto_threshold=auto_threshold,
            judge_threshold=judge_threshold,
            judge_client=judge_client,
            exclude_kc_id=kcs[kc_idx].id,
            dry_run=dry_run,
        )

        if kcprereq is not None:
            new_prereqs_per_kc[kc_idx].append(kcprereq)
            if reason == "auto":
                auto_accepted += 1
            elif reason == "judge_yes":
                judge_accepted += 1
        else:
            unaligned += 1
            needs_review.append(
                {
                    "kc_id": kcs[kc_idx].id,
                    "kc_name": kcs[kc_idx].name,
                    "prereq_raw": prereq_name,
                    "reason": reason,
                    "best_similarity": _cosine(
                        qvec,
                        candidate_embs[
                            max(
                                range(len(candidate_embs)),
                                key=lambda i: _cosine(qvec, candidate_embs[i]),
                            )
                        ]
                    )
                    if candidate_embs
                    else 0.0,
                }
            )

    # 3. 写回
    for kc_idx, kc in enumerate(kcs):
        new_prereqs = new_prereqs_per_kc[kc_idx]
        if not new_prereqs:
            continue
        updated = kc.model_copy(update={"prerequisites": new_prereqs})
        if not dry_run:
            store.save_kc(updated)  # type: ignore[attr-defined]
        updated_kcs_count += 1

    return {
        "course_id": course_id,
        "total_kcs": len(kcs),
        "total_prereqs_raw": len(prereq_queries),
        "auto_accepted": auto_accepted,
        "judge_accepted": judge_accepted,
        "unaligned": unaligned,
        "updated_kcs": updated_kcs_count,
        "dry_run": dry_run,
        "needs_review": needs_review,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m backend.scripts.align_prerequisites",
        description="line A — KC 先修关系离线 ETL",
    )
    p.add_argument("--course-id", required=True, help="目标课程 id")
    p.add_argument("--dry-run", action="store_true", help="不写回 store")
    p.add_argument(
        "--auto-threshold",
        type=float,
        default=DEFAULT_AUTO_THRESHOLD,
        help=f"cosine >= 此值自动接受 (默认 {DEFAULT_AUTO_THRESHOLD})",
    )
    p.add_argument(
        "--judge-threshold",
        type=float,
        default=DEFAULT_JUDGE_THRESHOLD,
        help=f"cosine 介于 [judge, auto) 调 fast judge (默认 {DEFAULT_JUDGE_THRESHOLD})",
    )
    p.add_argument(
        "--report-dir",
        default=str(REPORT_DIR),
        help=f"报告输出目录 (默认 {REPORT_DIR})",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    args = _build_arg_parser().parse_args(argv)

    # store / embed_fn 走真实路径 (CLI 模式)
    from app.db.sqlite_store import SqliteStore
    from app.services.embedding import embed_texts

    store = SqliteStore(settings.sqlite_path)
    try:
        report = align_course_kcs(
            args.course_id,
            store=store,
            embed_fn=embed_texts,
            judge_client=_get_judge_client(),
            auto_threshold=args.auto_threshold,
            judge_threshold=args.judge_threshold,
            dry_run=args.dry_run,
        )
    finally:
        store.close()

    # 输出报告
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_course = args.course_id.replace("/", "_")
    report_path = report_dir / f"{safe_course}_{ts}.json"
    review_path = report_dir / f"{safe_course}_needs_review.jsonl"

    needs_review = report.pop("needs_review", [])
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with review_path.open("w", encoding="utf-8") as f:
        for entry in needs_review:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # 控制台摘要
    print(
        json.dumps(
            {**report, "report_path": str(report_path), "review_path": str(review_path)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())