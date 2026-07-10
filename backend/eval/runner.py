"""端到端评测 runner。

流程:
1. 从 store 拿 KC 列表
2. generator.generate_suite → 30 题
3. validator.validate_suite → 7 规则格式校验
4. foxsay_call(case) 拿实际回答(默认 mock;可注入真实 agent)
5. judge.judge_suite → Faithfulness 0-3
6. 输出 eval_reports/<course>_<iso>.md 报告
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import Citation, KC

from backend.eval.generator import generate_suite
from backend.eval.judge import judge_suite
from backend.eval.schemas import (
    FoxsayAnswer,
    JudgeVerdict,
    PilotSuite,
    ValidatorReport,
)
from backend.eval.validator import validate_suite

logger = logging.getLogger(__name__)

# foxsay_call 签名:(EvalCase) → FoxsayAnswer
FoxsayCall = Callable[[Any], FoxsayAnswer]


def _default_mock_foxsay(case: Any) -> FoxsayAnswer:
    """pilot 阶段默认 mock:基于 gold_answer + answerability 模拟回答。"""
    if not case.answerability:
        return FoxsayAnswer(
            course_id=case.course_id,
            answer="课程材料中未覆盖此内容，以下是通用理解，建议对照教材确认。" + (case.gold_answer or "")[:100],
            citations=[],
            confidence_status="out_of_scope",
            refusal_reason="supplementary",
        )
    return FoxsayAnswer(
        course_id=case.course_id,
        answer="(mock) " + (case.gold_answer or "")[:200],
        citations=case.gold_citations or [
            Citation(file_name="mock.pdf", locator="第一部分"),
        ],
        confidence_status="grounded",
    )


def _load_kc_lookup(store: SqliteStore, course_id: str) -> dict[str, KC]:
    try:
        kcs = store.get_kcs_by_course(course_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("get_kcs_by_course 失败: %s, 视为空", e)
        return {}
    return {kc.id: kc for kc in kcs}


def run_pilot(
    course_id: str,
    course_title: str,
    store: SqliteStore,
    foxsay_call: FoxsayCall | None = None,
    output_dir: str | Path = "eval_reports",
    iso_timestamp: str | None = None,
) -> dict[str, Any]:
    """端到端跑 30 题 pilot。

    返回 dict:
    {
        "suite": PilotSuite,
        "validator_reports": list[ValidatorReport],
        "judge_verdicts": list[JudgeVerdict],
        "report_path": str,
        "summary": {...},
    }
    """
    if foxsay_call is None:
        foxsay_call = _default_mock_foxsay

    iso = iso_timestamp or datetime.now(tz=timezone.utc).replace(tzinfo=None).strftime("%Y%m%dT%H%M%SZ")
    kc_lookup = _load_kc_lookup(store, course_id)
    kcs = list(kc_lookup.values())

    logger.info("pilot start: course=%s, kcs=%d", course_id, len(kcs))

    # 1) 生成
    suite = generate_suite(course_id, course_title, kcs)
    logger.info("generated %d cases", len(suite.cases))

    # 2) validator
    val_reports = validate_suite(
        [c.eval_case for c in suite.cases],
        kc_lookup=kc_lookup,
    )
    pass_cnt = sum(1 for r in val_reports if r.verdict == "pass")
    logger.info("validator: %d/%d pass", pass_cnt, len(val_reports))

    # 3) 跑 FoxSay(每条 EvalCase)
    actuals: list[FoxsayAnswer] = []
    for c in suite.cases:
        try:
            actuals.append(foxsay_call(c.eval_case))
        except Exception as e:  # noqa: BLE001
            logger.exception("foxsay_call 失败 case=%s: %s", c.eval_case.case_id, e)
            actuals.append(
                FoxsayAnswer(
                    course_id=c.eval_case.course_id,
                    answer=f"(runner 异常) {e!s}",
                    citations=[],
                    confidence_status="out_of_scope",
                )
            )

    # 4) judge
    judge_verdicts = judge_suite(
        [c.eval_case for c in suite.cases],
        actuals,
    )
    faith_pass = sum(1 for v in judge_verdicts if v.passed)
    logger.info("judge: %d/%d faithfulness>=2", faith_pass, len(judge_verdicts))

    # 5) 写报告
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{course_id}_{iso}.md"
    report_text = render_report(
        suite, val_reports, judge_verdicts, course_title, iso
    )
    report_path.write_text(report_text, encoding="utf-8")
    logger.info("report written: %s", report_path)

    summary = {
        "n_total": len(suite.cases),
        "n_validator_pass": pass_cnt,
        "n_judge_pass": faith_pass,
        "by_type": _by_type_breakdown(suite, val_reports, judge_verdicts),
        "report_path": str(report_path),
    }
    return {
        "suite": suite,
        "validator_reports": val_reports,
        "judge_verdicts": judge_verdicts,
        "report_path": str(report_path),
        "summary": summary,
    }


def _by_type_breakdown(
    suite: PilotSuite,
    val_reports: list[ValidatorReport],
    judge_verdicts: list[JudgeVerdict],
) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for pc, vr, jv in zip(suite.cases, val_reports, judge_verdicts):
        t = pc.eval_case.question_type
        slot = out.setdefault(t, {"total": 0, "val_pass": 0, "judge_pass": 0})
        slot["total"] += 1
        if vr.verdict == "pass":
            slot["val_pass"] += 1
        if jv.passed:
            slot["judge_pass"] += 1
    return out


def render_report(
    suite: PilotSuite,
    val_reports: list[ValidatorReport],
    judge_verdicts: list[JudgeVerdict],
    course_title: str,
    iso: str,
) -> str:
    """生成可读的 markdown 报告。"""
    n = len(suite.cases)
    n_val = sum(1 for r in val_reports if r.verdict == "pass")
    n_judge = sum(1 for v in judge_verdicts if v.passed)

    by_type = _by_type_breakdown(suite, val_reports, judge_verdicts)

    lines: list[str] = []
    lines.append(f"# FoxSay 评测报告 (Pilot) — {course_title}")
    lines.append("")
    lines.append(f"- course_id: `{suite.course_id}`")
    lines.append(f"- generated_at: {iso}")
    lines.append(f"- generator: `{suite.generator_model}`")
    lines.append(f"- 题目总数: **{n}**")
    lines.append(f"- Validator 通过: **{n_val}/{n}** ({100*n_val//max(n,1)}%)")
    lines.append(f"- Judge 通过 (faithfulness ≥ 2): **{n_judge}/{n}** ({100*n_judge//max(n,1)}%)")
    lines.append("")

    lines.append("## 按题型分布")
    lines.append("")
    lines.append("| 题型 | 总数 | Validator 通过 | Judge 通过 |")
    lines.append("|---|---|---|---|")
    for t, slot in by_type.items():
        lines.append(
            f"| {t} | {slot['total']} | {slot['val_pass']} | {slot['judge_pass']} |"
        )
    lines.append("")

    lines.append("## 逐题明细")
    lines.append("")
    for pc, vr, jv in zip(suite.cases, val_reports, judge_verdicts):
        c = pc.eval_case
        lines.append(f"### {c.case_id} — {c.question_type} / {c.bloom_level}")
        lines.append(f"- Q: {c.question}")
        lines.append(
            f"- Validator: **{vr.verdict}**"
            + (f" (failed: {','.join(vr.failed_rules)})" if vr.failed_rules else "")
        )
        lines.append(
            f"- Judge Faithfulness: **{jv.faithfulness}** "
            f"({'pass' if jv.passed else 'fail'})"
            + (f" — {jv.reasoning}" if jv.reasoning else "")
        )
        lines.append("")

    return "\n".join(lines)
