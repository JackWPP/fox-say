"""PR0 contract tests — 锁定三线并行(A/B/C)共享 schema,防止后续回归。

覆盖:
1. 新 schema 字段合法性 (KCPrerequisite / CommonMistake / EvalCase /
   KGNode / KGEdge / KnowledgeGraphResponse)
2. KC 升级后向后兼容:
   - 旧 KC JSON (prerequisites: list[str]) 反序列化自动迁移到 prerequisites_raw
   - 旧字段 common_mistakes / prerequisites 不被破坏
   - 新字段都有合理默认值
3. SqliteStore round-trip:
   - 老格式 KC JSON 入库 → 取出来 → 字段已迁移
   - 新格式 KC 入库 → 取出来 → 字段不丢
4. Settings 新增 judge_* 字段可读
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import (
    KC,
    Citation,
    CommonMistake,
    EvalCase,
    KCPrerequisite,
    KGEdge,
    KGNode,
    KnowledgeGraphResponse,
)


# ---------------------------------------------------------------------------
# 1. 新 schema 字段合法性
# ---------------------------------------------------------------------------


def test_kc_prerequisite_defaults():
    """KCPrerequisite:dependency_strength 默认 1.0, source 默认 etl_auto。"""
    p = KCPrerequisite(prerequisite_kc_id="kc_abc123")
    assert p.prerequisite_kc_id == "kc_abc123"
    assert p.dependency_strength == 1.0
    assert p.source == "etl_auto"


def test_kc_prerequisite_source_literal_validation():
    """source 字段是 Literal,非法值必须报 ValidationError。"""
    with pytest.raises(ValidationError):
        KCPrerequisite(
            prerequisite_kc_id="kc_x",
            source="hand_made",  # 非法值
        )


def test_common_mistake_minimal():
    """CommonMistake 最小字段:mistake_id + description。"""
    m = CommonMistake(mistake_id="cm_001", description="混淆代数重数与几何重数")
    assert m.mistake_id == "cm_001"
    assert m.associated_bug_rule_id == ""  # 默认空


def test_eval_case_required_fields():
    """EvalCase 必填:case_id / course_id / question / question_type / gold_answer。"""
    case = EvalCase(
        case_id="LA-CH04-001",
        course_id="linear-algebra",
        question="什么是特征值?",
        question_type="definition",
        gold_answer="特征值是...",
    )
    assert case.answerability is True
    assert case.gold_citations == []
    assert case.pedagogical_constraint == ""


def test_eval_case_question_type_literal():
    """question_type 是 Literal,非法值报错。"""
    with pytest.raises(ValidationError):
        EvalCase(
            case_id="x",
            course_id="x",
            question="x",
            question_type="essay",  # 非法
            gold_answer="x",
        )


def test_eval_case_refusal_case():
    """拒答类 case:answerability=False,gold_answer 是拒答文案。"""
    case = EvalCase(
        case_id="LA-OUT-001",
        course_id="linear-algebra",
        question="什么是光合作用?",
        question_type="refusal",
        gold_answer="这个问题超出了线性代数的范围。",
        answerability=False,
    )
    assert case.answerability is False


def test_kg_node_defaults():
    """KGNode:mastery 默认 0.0,importance 默认 medium。"""
    n = KGNode(id="kc_x", label="特征值", chapter_id="ch-4")
    assert n.mastery == 0.0
    assert n.importance == "medium"
    assert n.cognitive_dimension == "conceptual"


def test_kg_edge_defaults():
    """KGEdge:strength 默认 1.0,edge_type 默认 prerequisite。"""
    e = KGEdge(source="kc_a", target="kc_b")
    assert e.strength == 1.0
    assert e.edge_type == "prerequisite"


def test_knowledge_graph_response_round_trip():
    """KnowledgeGraphResponse:序列化 + 反序列化保持一致。"""
    resp = KnowledgeGraphResponse(
        course_id="linear-algebra",
        nodes=[
            KGNode(id="kc_a", label="向量空间", chapter_id="ch-1", importance="high"),
            KGNode(id="kc_b", label="线性变换", chapter_id="ch-2"),
        ],
        edges=[KGEdge(source="kc_a", target="kc_b", strength=0.9)],
    )
    raw = resp.model_dump_json()
    restored = KnowledgeGraphResponse.model_validate_json(raw)
    assert restored.course_id == "linear-algebra"
    assert len(restored.nodes) == 2
    assert restored.nodes[0].importance == "high"
    assert restored.edges[0].strength == 0.9
    assert restored.layout_hint == "dagre"


# ---------------------------------------------------------------------------
# 2. KC 升级后向后兼容性
# ---------------------------------------------------------------------------


def test_kc_new_fields_defaults():
    """KC 新增字段必须有合理默认值,旧调用方不需要改。"""
    kc = KC(id="kc_x", course_id="c1", name="特征值")
    # PR0 新字段默认
    assert kc.cognitive_dimension == "conceptual"
    assert kc.derivation_steps == []
    assert kc.last_practiced_at is None
    assert kc.mastery_score == 0.0
    assert kc.srs_state is None
    assert kc.viewpoints == []
    assert kc.counter_arguments == []
    # PR0 新增结构化字段
    assert kc.prerequisites == []
    assert kc.prerequisites_raw == []
    assert kc.common_mistakes_v2 == []
    # 旧字段保留
    assert kc.common_mistakes == []


def test_kc_legacy_prerequisites_auto_migration():
    """关键测试:老 KC JSON 里 prerequisites 是 list[str],
    反序列化时 model_validator 应自动搬到 prerequisites_raw。"""
    legacy_data = {
        "id": "kc_x",
        "course_id": "c1",
        "name": "特征值",
        "prerequisites": ["矩阵", "线性方程组"],  # ★ 老格式
    }
    kc = KC.model_validate(legacy_data)
    # 老 list[str] 已迁移到 raw
    assert kc.prerequisites_raw == ["矩阵", "线性方程组"]
    # 新字段留空 (等 ETL 后续填充)
    assert kc.prerequisites == []


def test_kc_new_format_no_migration():
    """新格式 KC (prerequisites: list[KCPrerequisite]) 不应触发 migration。"""
    new_data = {
        "id": "kc_x",
        "course_id": "c1",
        "name": "特征值",
        "prerequisites": [
            {"prerequisite_kc_id": "kc_matrix", "dependency_strength": 0.9},
        ],
        "prerequisites_raw": ["矩阵"],  # 之前 ETL 留下的
    }
    kc = KC.model_validate(new_data)
    assert len(kc.prerequisites) == 1
    assert kc.prerequisites[0].prerequisite_kc_id == "kc_matrix"
    assert kc.prerequisites[0].dependency_strength == 0.9
    # raw 字段不被覆盖
    assert kc.prerequisites_raw == ["矩阵"]


def test_kc_legacy_migration_idempotent():
    """已经迁移过的 KC (prerequisites=[] + prerequisites_raw=[...])
    再次反序列化,raw 不应被空 prerequisites 覆盖成 []。"""
    migrated = {
        "id": "kc_x",
        "course_id": "c1",
        "name": "特征值",
        "prerequisites": [],
        "prerequisites_raw": ["矩阵", "线性方程组"],
    }
    kc = KC.model_validate(migrated)
    assert kc.prerequisites_raw == ["矩阵", "线性方程组"]
    assert kc.prerequisites == []


def test_kc_empty_prerequisites_no_migration():
    """空 prerequisites: [] 不应触发 migration (避免无意义覆盖 raw)。"""
    data = {
        "id": "kc_x",
        "course_id": "c1",
        "name": "特征值",
        "prerequisites": [],
        "prerequisites_raw": ["existing_raw"],
    }
    kc = KC.model_validate(data)
    assert kc.prerequisites_raw == ["existing_raw"]


# ---------------------------------------------------------------------------
# 3. SqliteStore round-trip 兼容性
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    """临时 SqliteStore,测试完销毁。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = SqliteStore(db_path=db_path)
    yield s
    s.close()
    Path(db_path).unlink(missing_ok=True)


def test_kc_sqlite_round_trip_legacy_format(store):
    """模拟一个老 KC (用 raw INSERT 写入 list[str] 格式),
    然后用 get_kc 读出来,验证自动 migration。"""
    legacy_json = json.dumps({
        "id": "kc_legacy",
        "type": "knowledge_component",
        "course_id": "c1",
        "chapter_id": "ch-1",
        "name": "矩阵的逆",
        "prerequisites": ["矩阵乘法", "行列式"],  # 老格式
        "valid_at": "2026-01-01",
        "version": 1,
    }, ensure_ascii=False)

    # 绕过 save_kc (因为它会先 dump 新 schema),直接 raw INSERT 模拟老数据
    store._conn.execute(
        """INSERT INTO wiki_kcs
           (kc_id, course_id, chapter_id, name, layer, bloom_level,
            data_json, valid_at, invalid_at, version, content_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("kc_legacy", "c1", "ch-1", "矩阵的逆", "micro", "Understanding",
         legacy_json, "2026-01-01", None, 1, ""),
    )
    store._conn.commit()

    kc = store.get_kc("kc_legacy")
    assert kc is not None
    assert kc.prerequisites_raw == ["矩阵乘法", "行列式"]
    assert kc.prerequisites == []
    assert kc.cognitive_dimension == "conceptual"  # 新字段默认


def test_kc_sqlite_round_trip_new_format(store):
    """新格式 KC save → get 字段无损。"""
    kc = KC(
        id="kc_new",
        course_id="c1",
        chapter_id="ch-2",
        name="特征向量",
        cognitive_dimension="procedural_skill",
        derivation_steps=["第一步: 求特征多项式", "第二步: 解齐次方程组"],
        prerequisites=[
            KCPrerequisite(prerequisite_kc_id="kc_matrix", dependency_strength=0.95),
        ],
        common_mistakes_v2=[
            CommonMistake(mistake_id="cm_1", description="混淆代数重数与几何重数"),
        ],
    )
    store.save_kc(kc)

    restored = store.get_kc("kc_new")
    assert restored is not None
    assert restored.cognitive_dimension == "procedural_skill"
    assert len(restored.derivation_steps) == 2
    assert restored.prerequisites[0].prerequisite_kc_id == "kc_matrix"
    assert restored.prerequisites[0].dependency_strength == 0.95
    assert restored.common_mistakes_v2[0].mistake_id == "cm_1"


# ---------------------------------------------------------------------------
# 4. Settings 新增 judge 配置
# ---------------------------------------------------------------------------


def test_settings_judge_defaults():
    """judge_* 字段必须存在且有合理默认 (指向 LM Studio 本地)。"""
    s = Settings(_env_file=None)  # 不读 .env, 用纯默认
    assert s.judge_api_key == "lm-studio"
    assert s.judge_api_base == "http://localhost:1234/v1"
    assert s.judge_model_name == "qwen/qwen3.5-9b"
    assert s.judge_fast_model_name == "qwen/qwen3-4b-2507"
    assert s.reranker_model_name == "qwen3-reranker-0.6b"


def test_settings_judge_overridable_via_init():
    """judge_* 字段可通过环境变量风格的初始化参数覆盖。"""
    s = Settings(
        _env_file=None,
        judge_api_base="http://192.168.1.40:1234/v1",
        judge_model_name="qwen/qwen3-32b",
    )
    assert s.judge_api_base == "http://192.168.1.40:1234/v1"
    assert s.judge_model_name == "qwen/qwen3-32b"
