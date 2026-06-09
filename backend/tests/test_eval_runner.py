"""Runner 端到端测试 — mock LLM 跑完整 pipeline,验证 30 题报告产出。"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import Citation, KC

from backend.eval.runner import (
    _default_mock_foxsay,
    _load_kc_lookup,
    render_report,
    run_pilot,
)
from backend.eval.schemas import EvalCase, FoxsayAnswer, JudgeVerdict, PilotCase, PilotSuite, ValidatorReport


@pytest.fixture
def temp_store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    s = SqliteStore(db_path=path)
    yield s
    s.close()
    Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 1. 默认 mock foxsay_call
# ---------------------------------------------------------------------------


def test_default_mock_foxsay_refusal_path():
    case = EvalCase(
        case_id="LA-REF-001",
        course_id="linear-algebra",
        question="什么是光合作用?",
        question_type="refusal",
        gold_answer="不知道",
        answerability=False,
    )
    ans = _default_mock_foxsay(case)
    assert ans.confidence_status == "out_of_scope"
    assert "超出" in ans.answer or "不知道" in ans.answer
    assert ans.citations == []


def test_default_mock_foxsay_answerable_path():
    case = EvalCase(
        case_id="LA-DEF-001",
        course_id="linear-algebra",
        question="什么是特征值?",
        question_type="definition",
        gold_answer="特征值定义",
        answerability=True,
    )
    ans = _default_mock_foxsay(case)
    assert ans.confidence_status == "grounded"
    assert "(mock)" in ans.answer
    assert ans.refusal_reason is None


# ---------------------------------------------------------------------------
# 2. KC lookup
# ---------------------------------------------------------------------------


def test_load_kc_lookup_returns_empty_when_no_kcs(temp_store):
    # 课存在但无 KC
    temp_store._conn.execute(
        "INSERT INTO courses (id, title, status) VALUES (?, ?, ?)",
        ("empty-course", "空课", "empty"),
    )
    temp_store._conn.commit()
    lookup = _load_kc_lookup(temp_store, "empty-course")
    assert lookup == {}


def test_load_kc_lookup_returns_kcs(temp_store):
    kc = KC(id="kc_test", course_id="c1", name="test kc")
    temp_store.save_kc(kc)
    lookup = _load_kc_lookup(temp_store, "c1")
    assert "kc_test" in lookup
    assert lookup["kc_test"].name == "test kc"


# ---------------------------------------------------------------------------
# 3. render_report — markdown 文本
# ---------------------------------------------------------------------------


def test_render_report_contains_key_sections():
    # 最小数据
    case = EvalCase(
        case_id="LA-DEF-001",
        course_id="linear-algebra",
        question="什么是特征值?",
        question_type="definition",
        gold_answer="特征值定义",
        answerability=True,
    )
    pc = PilotCase(eval_case=case)
    suite = PilotSuite(course_id="linear-algebra", cases=[pc])
    val_reports = [ValidatorReport(case_id="LA-DEF-001", verdict="pass")]
    judge_verdicts = [JudgeVerdict(case_id="LA-DEF-001", faithfulness=3, passed=True)]

    md = render_report(suite, val_reports, judge_verdicts, "线性代数", "20260609T000000Z")
    assert "FoxSay 评测报告" in md
    assert "linear-algebra" in md
    assert "按题型分布" in md
    assert "LA-DEF-001" in md
    assert "definition" in md
    assert "Faithfulness" in md


# ---------------------------------------------------------------------------
# 4. run_pilot 端到端 — mock 全部
# ---------------------------------------------------------------------------


def test_run_pilot_end_to_end_with_mock_llms(temp_store):
    """完整跑 30 题:mock LLM + mock foxsay,验证产出文件 + summary。"""
    # 准备一条 KC
    kc = KC(id="kc_eigen", course_id="linear-algebra", name="特征值")
    temp_store.save_kc(kc)

    # 准备 KC 课记录(让 get_course 不返回 None)
    temp_store._conn.execute(
        "INSERT INTO courses (id, title, status) VALUES (?, ?, ?)",
        ("linear-algebra", "线性代数", "ready"),
    )
    temp_store._conn.commit()

    # mock generator
    def gen_llm(system: str, user: str) -> str:
        if "题型: definition" in user:
            qtype = "definition"
        elif "题型: derivation" in user:
            qtype = "derivation"
        elif "题型: cross_chapter" in user:
            qtype = "cross_chapter"
        elif "题型: refusal" in user:
            qtype = "refusal"
        else:
            qtype = "ambiguous"
        obj = {
            "case_id": f"LA-{qtype.upper()}-999",
            "question": f"Q {qtype}",
            "question_type": qtype,
            "associated_kc_id": "kc_eigen" if qtype in {"definition", "derivation"} else None,
            "bloom_level": "Understanding",
            "gold_answer": (
                "标准答案:这是一个 50 字以上的具体答案,涵盖要点 1、2、3。"
                if qtype != "refusal" else "这个问题超出了范围,不知道。"
            ),
            "gold_citations": (
                [{"file_name": "f.pdf", "locator": "p1"}]
                if qtype in {"definition", "derivation", "cross_chapter"} else []
            ),
            "answerability": qtype != "refusal",
        }
        return json.dumps(obj, ensure_ascii=False)

    # mock validator
    def val_llm(system: str, user: str) -> str:
        return json.dumps({"verdict": "pass", "failed_rules": []})

    # mock judge
    def judge_llm(system: str, user: str) -> str:
        return json.dumps({"faithfulness": 3, "reasoning": "mock"})

    # 把这些 mock 注入到 runner — 实际做法:让 gen_llm 也用作 judge/validator 的 llm_call
    # runner 内部对 generator/validator/judge 是分别调 llm 的,所以需要 monkey-patch
    import backend.eval.generator as gen_mod
    import backend.eval.judge as judge_mod
    import backend.eval.validator as val_mod

    orig_gen = gen_mod._get_client
    orig_val = val_mod._get_judge_client
    orig_judge = judge_mod._get_judge_client

    class _NoClient:
        def __init__(self, *a, **k): pass

    gen_mod._get_client = lambda: _NoClient()
    val_mod._get_judge_client = lambda: _NoClient()
    judge_mod._get_judge_client = lambda: _NoClient()

    # 通过 llm_call 注入
    try:
        with tempfile.TemporaryDirectory() as outdir:
            # runner 直接用 llm_call=None 时,会调 _get_client(); 改成传 foxsay_call
            # generator 和 validator 仍要 mock, 我们在 patch 后让它们走 llm_call
            # 但 runner 内部没暴露 generator 的 llm_call 入参,所以靠 patch client
            # 上面 patch 后 _get_client() 返回 _NoClient, 没 chat.completions.create
            # → 会失败。我们用 monkey patch 替换 generator.generate_suite
            orig_generate_suite = gen_mod.generate_suite
            gen_mod.generate_suite = lambda *a, **k: orig_generate_suite(
                *a, **k, llm_call=gen_llm,
            )
            orig_validate_suite = val_mod.validate_suite
            val_mod.validate_suite = lambda cases, kc_lookup=None, llm_call=None: (
                orig_validate_suite(cases, kc_lookup=kc_lookup, llm_call=val_llm)
            )
            orig_judge_suite = judge_mod.judge_suite
            judge_mod.judge_suite = lambda cases, actuals, llm_call=None: (
                orig_judge_suite(cases, actuals, llm_call=judge_llm)
            )

            result = run_pilot(
                course_id="linear-algebra",
                course_title="线性代数",
                store=temp_store,
                foxsay_call=_default_mock_foxsay,
                output_dir=outdir,
                iso_timestamp="20260609T000000Z",
            )

            gen_mod.generate_suite = orig_generate_suite
            val_mod.validate_suite = orig_validate_suite
            judge_mod.judge_suite = orig_judge_suite

            assert "summary" in result
            assert result["summary"]["n_total"] == 30
            # report 写出
            rp = Path(result["report_path"])
            assert rp.exists()
            content = rp.read_text(encoding="utf-8")
            assert "线性代数" in content
            assert "按题型分布" in content
    finally:
        gen_mod._get_client = orig_gen
        val_mod._get_judge_client = orig_val
        judge_mod._get_judge_client = orig_judge
