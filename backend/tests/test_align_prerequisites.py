"""line A — prereq ETL 单元测试 (纯 mock, 不调真实 LLM / embedding)。

覆盖 6 项 checklist:
1. test_cosine_threshold_auto_accept   — sim ≥ auto_threshold 直接 source=etl_auto
2. test_cosine_threshold_judge_yes     — judge 返回 YES → source=etl_judge_reviewed
3. test_cosine_threshold_judge_no      — judge 返回 NO → unaligned
4. test_cosine_below_threshold_unaligned — sim < judge_threshold → unaligned
5. test_dry_run_does_not_call_save_kc  — dry_run 模式不写回
6. test_writes_kcprerequisite_objects  — 写回的是 KCPrerequisite 对象 (而非 dict / str)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.schemas.foxsay import KC, KCPrerequisite, PrereqSource
from scripts import align_prerequisites


# ---------------------------------------------------------------------------
# Mock store / embed / judge
# ---------------------------------------------------------------------------


class _MockStore:
    """最小 mock store — 只实现对齐脚本用到的方法。"""

    def __init__(self) -> None:
        self.kcs: dict[str, KC] = {}
        self.save_calls: list[KC] = []

    def get_kcs_by_course(self, course_id: str) -> list[KC]:
        return [kc for kc in self.kcs.values() if kc.course_id == course_id]

    def save_kc(self, kc: KC) -> None:
        self.save_calls.append(kc)
        self.kcs[kc.id] = kc


def _make_kc(kc_id: str, course_id: str, name: str, **kwargs: Any) -> KC:
    return KC(id=kc_id, course_id=course_id, name=name, **kwargs)


def _vec(components: dict[int, float], dim: int = 4) -> list[float]:
    """生成 dim 维向量,只填充 components 里的位,其余 0。"""
    v = [0.0] * dim
    for i, val in components.items():
        v[i] = val
    return v


def _ident(v: list[float]) -> list[float]:
    """self-sim = 1.0 (单位向量)。"""
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


def _make_judge_client(reply: str) -> tuple[Any, dict]:
    """构造一个 OpenAI 兼容的 mock judge client。

    返回 (client, stats),其中 stats["called"] 记录 chat.completions.create 调用次数。
    """
    stats = {"called": 0}

    def _create(**_: Any) -> Any:
        stats["called"] += 1
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create)),
    )
    return client, stats


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cosine_threshold_auto_accept(monkeypatch: pytest.MonkeyPatch) -> None:
    """prereq 与 candidate 完全同义 → cosine ≈ 1.0 → auto 接受。

    注意:prereq 字符串 ("approach") 与候选 KC name ("趋近") 不同,
    但 embedding 故意相同,模拟"ETL 前的字符串对齐"场景。
    """
    store = _MockStore()
    a = _make_kc("a", "c1", "极限", prerequisites_raw=["approach"])
    b = _make_kc("b", "c1", "趋近")
    store.kcs["a"] = a
    store.kcs["b"] = b

    same_v = _ident(_vec({0: 1.0}))
    diff_v = _ident(_vec({1: 1.0}))
    embed_map = {
        "approach": same_v,
        "趋近": same_v,    # KC b
        "极限": diff_v,    # KC a(应被排除,因为 exclude_kc_id=a)
    }

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [embed_map[t] for t in texts]

    fake_judge = SimpleNamespace()  # 永远不该被调

    report = align_prerequisites.align_course_kcs(
        "c1",
        store=store,
        embed_fn=fake_embed,
        judge_client=fake_judge,  # type: ignore[arg-type]
        auto_threshold=0.85,
        judge_threshold=0.60,
        dry_run=False,
    )

    assert report["auto_accepted"] == 1
    assert report["judge_accepted"] == 0
    assert report["unaligned"] == 0
    # save_kc 应被调一次(为 "极限" 写入新 prerequisites)
    assert len(store.save_calls) == 1
    saved = store.save_calls[0]
    assert saved.id == "a"
    assert len(saved.prerequisites) == 1
    assert saved.prerequisites[0].source == "etl_auto"  # type: ignore[union-attr]
    # 必须指向 b(而非 a 自己)
    assert saved.prerequisites[0].prerequisite_kc_id == "b"  # type: ignore[union-attr]
    assert saved.prerequisites[0].dependency_strength >= 0.99  # type: ignore[union-attr]


def test_cosine_threshold_judge_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    """sim 介于 [judge, auto) → 调 judge;judge=YES → etl_judge_reviewed。

    prereq 字符串("vecspace")与候选 KC name("向量空间")不同,但 embedding
    故意设计成 cos ≈ 0.7。
    """
    store = _MockStore()
    a = _make_kc("a", "c1", "线性映射", prerequisites_raw=["vecspace"])
    b = _make_kc("b", "c1", "向量空间")
    store.kcs["a"] = a
    store.kcs["b"] = b

    prereq_v = _ident(_vec({0: 0.7, 1: 0.714}))  # ~45° 角 → cos ≈ 0.7
    cand_b_v = _ident(_vec({0: 1.0}))
    cand_a_v = _ident(_vec({2: 1.0}))
    embed_map = {"vecspace": prereq_v, "向量空间": cand_b_v, "线性映射": cand_a_v}

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [embed_map[t] for t in texts]

    judge, judge_stats = _make_judge_client("YES")

    report = align_prerequisites.align_course_kcs(
        "c1",
        store=store,
        embed_fn=fake_embed,
        judge_client=judge,
        auto_threshold=0.85,
        judge_threshold=0.60,
        dry_run=False,
    )

    assert judge_stats["called"] == 1
    assert report["judge_accepted"] == 1
    assert report["auto_accepted"] == 0
    assert report["unaligned"] == 0
    saved = store.save_calls[0]
    assert saved.prerequisites[0].source == "etl_judge_reviewed"  # type: ignore[union-attr]


def test_cosine_threshold_judge_no(monkeypatch: pytest.MonkeyPatch) -> None:
    """sim 介于 [judge, auto) 但 judge=NO → unaligned。"""
    store = _MockStore()
    a = _make_kc("a", "c1", "极限", prerequisites_raw=["derivative"])
    b = _make_kc("b", "c1", "导数")
    store.kcs["a"] = a
    store.kcs["b"] = b

    prereq_v = _ident(_vec({0: 0.7, 1: 0.714}))  # cos ≈ 0.7 with dir0
    cand_b_v = _ident(_vec({0: 1.0}))
    cand_a_v = _ident(_vec({2: 1.0}))
    embed_map = {"derivative": prereq_v, "导数": cand_b_v, "极限": cand_a_v}

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [embed_map[t] for t in texts]

    judge, judge_stats = _make_judge_client("NO")

    report = align_prerequisites.align_course_kcs(
        "c1",
        store=store,
        embed_fn=fake_embed,
        judge_client=judge,
        auto_threshold=0.85,
        judge_threshold=0.60,
        dry_run=False,
    )

    assert judge_stats["called"] == 1
    assert report["judge_accepted"] == 0
    assert report["auto_accepted"] == 0
    assert report["unaligned"] == 1
    assert len(report["needs_review"]) == 1
    assert report["needs_review"][0]["reason"] == "judge_no"
    # 没写回
    assert store.save_calls == []


def test_cosine_below_threshold_unaligned() -> None:
    """sim < judge_threshold → 直接 unaligned,不调 judge。"""
    store = _MockStore()
    a = _make_kc("a", "c1", "线性代数", prerequisites_raw=["calc-pre"])
    b = _make_kc("b", "c1", "微积分")
    store.kcs["a"] = a
    store.kcs["b"] = b

    # prereq("calc-pre") 与所有候选正交 → cosine = 0 < judge_threshold
    prereq_v = _ident(_vec({0: 1.0}))
    cand_b_v = _ident(_vec({1: 1.0}))
    cand_a_v = _ident(_vec({2: 1.0}))
    embed_map = {"calc-pre": prereq_v, "微积分": cand_b_v, "线性代数": cand_a_v}

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [embed_map[t] for t in texts]

    judge, judge_stats = _make_judge_client("YES")

    report = align_prerequisites.align_course_kcs(
        "c1",
        store=store,
        embed_fn=fake_embed,
        judge_client=judge,
        auto_threshold=0.85,
        judge_threshold=0.60,
        dry_run=False,
    )

    assert judge_stats["called"] == 0  # judge 完全没被调
    assert report["unaligned"] == 1
    assert report["auto_accepted"] == 0
    assert report["judge_accepted"] == 0
    assert len(report["needs_review"]) == 1
    assert report["needs_review"][0]["reason"] == "below_threshold"


def test_dry_run_does_not_call_save_kc() -> None:
    """dry_run=True → save_kc 不被调,但 report 里 updated_kcs > 0。"""
    store = _MockStore()
    a = _make_kc("a", "c1", "极限", prerequisites_raw=["approach"])
    b = _make_kc("b", "c1", "趋近")
    store.kcs["a"] = a
    store.kcs["b"] = b

    same_v = _ident(_vec({0: 1.0}))
    diff_v = _ident(_vec({1: 1.0}))
    embed_map = {
        "approach": same_v,
        "趋近": same_v,
        "极限": diff_v,
    }

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [embed_map[t] for t in texts]

    report = align_prerequisites.align_course_kcs(
        "c1",
        store=store,
        embed_fn=fake_embed,
        judge_client=None,
        auto_threshold=0.85,
        judge_threshold=0.60,
        dry_run=True,
    )

    assert report["dry_run"] is True
    assert store.save_calls == []
    assert report["updated_kcs"] == 1


def test_writes_kcprerequisite_objects() -> None:
    """写回 store 的是 KCPrerequisite 对象,字段类型符合 PrereqSource Literal。"""
    store = _MockStore()
    a = _make_kc("a", "c1", "极限", prerequisites_raw=["approach"])
    b = _make_kc("b", "c1", "趋近")
    store.kcs["a"] = a
    store.kcs["b"] = b

    same_v = _ident(_vec({0: 1.0}))
    diff_v = _ident(_vec({1: 1.0}))
    embed_map = {
        "approach": same_v,
        "趋近": same_v,
        "极限": diff_v,
    }

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [embed_map[t] for t in texts]

    align_prerequisites.align_course_kcs(
        "c1",
        store=store,
        embed_fn=fake_embed,
        judge_client=None,
        auto_threshold=0.85,
        judge_threshold=0.60,
        dry_run=False,
    )

    saved = store.save_calls[0]
    assert len(saved.prerequisites) == 1
    prereq = saved.prerequisites[0]
    assert isinstance(prereq, KCPrerequisite)
    assert isinstance(prereq.prerequisite_kc_id, str)
    assert isinstance(prereq.dependency_strength, float)
    assert prereq.dependency_strength >= 0.0 and prereq.dependency_strength <= 1.0
    assert prereq.source in ("expert", "etl_auto", "etl_judge_reviewed", "legacy")
    assert prereq.source == "etl_auto"
    # 写回后,store 里的 KC 也已更新
    assert store.kcs["a"].prerequisites[0].prerequisite_kc_id == "b"


# ---------------------------------------------------------------------------
# 额外健壮性测试 (HEC-3 不计 checklist,但 HEC-1/6 覆盖)
# ---------------------------------------------------------------------------


def test_h1_llm_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """HEC-1:embedding/LLM 失败必须抛(不静默)。"""
    store = _MockStore()
    a = _make_kc("a", "c1", "X", prerequisites_raw=["Y"])
    b = _make_kc("b", "c1", "Y")
    store.kcs["a"] = a
    store.kcs["b"] = b

    def fake_embed(_: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding API down")

    with pytest.raises(RuntimeError, match="embedding API down"):
        align_prerequisites.align_course_kcs(
            "c1",
            store=store,
            embed_fn=fake_embed,
            judge_client=None,
        )


def test_h6_explicit_course_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """HEC-6:course_id 显式传参,不反推。空 course_id → 空报告,不抛。"""
    store = _MockStore()
    report = align_prerequisites.align_course_kcs(
        "nonexistent-course",
        store=store,
        embed_fn=lambda texts: [[0.0] * 4 for _ in texts],
        judge_client=None,
    )
    assert report["course_id"] == "nonexistent-course"
    assert report["total_kcs"] == 0
    assert report["auto_accepted"] == 0
    assert report["unaligned"] == 0


def test_cli_help_exits_zero() -> None:
    """CLI --help 不抛。"""
    from scripts.align_prerequisites import _build_arg_parser

    parser = _build_arg_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0