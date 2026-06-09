# PR0 — 三线并行的共享 Contract (v1)

> Lock date: 2026-06
> Scope: 锁定 line A (prereq ETL)、line B (200 题评测脚手架)、line C (图谱可视化)
>        三条并行工作线的共享数据契约。
> Status: **Locked** — 修改本契约必须经过显式 PR review,因为三线下游消费。

---

## 为什么要 PR0

调研结论 (research_result/) + 用户决策已锁:

1. 标杆课 = **线性代数** (中国本科生,期末抱佛脚场景)
2. Judge 模型 = **Qwen3.5 9B (lmstudio)** 跟 DeepSeek 不同家族,防 self-preference
3. 三线 (prereq ETL / 评测 / 图谱) 共享:
   - `KCPrerequisite` 结构化先修关系 — line A 主导,B/C 消费
   - `EvalCase` 评测用例 — line B 主导,只产不消
   - `KGNode / KGEdge / KnowledgeGraphResponse` 图谱 API — line C 主导

如果三线启动后再补 schema,会出现"A 改了 KC.prerequisites,B 的题库引用了旧 KC ID,C 的边渲染断裂"的连环灾难。
**PR0 先锁定 contract → 三线再开 worktree** 是唯一安全顺序。

---

## 锁定的字段表

### KCPrerequisite (line A → B/C 消费)

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `prerequisite_kc_id` | str | — | 真实存在的 KC.id (uuid5) |
| `dependency_strength` | float | 1.0 | [0,1] 冷启动期都 1.0;后续 COMMAND/E-PRISM 学出真实概率 |
| `source` | Literal | "etl_auto" | "expert" / "etl_auto" / "etl_judge_reviewed" / "legacy" |

**消费契约**:
- line B 的 `EvalCase.associated_kc_id` 可以引用 prerequisites_raw 里的字符串名,**不能**直接引用 prerequisites 字段 (因为 line A 完成前 prerequisites 是空的)
- line C 的图谱边 `KGEdge.source/target` 必须用 KCPrerequisite.prerequisite_kc_id (KC.id),不能用字符串名

### CommonMistake (line A 主导,评测/前端消费)

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `mistake_id` | str | — | 唯一 ID (如 "cm_001") |
| `description` | str | — | 错误描述 |
| `associated_bug_rule_id` | str | "" | 学生认知诊断的 bug rule 标识 |

**消费契约**:
- line B 的 EvalCase 可在 pedagogical_constraint 中引用 mistake_id
- 前端 KC 详情抽屉可显示 description

### EvalCase (line B 独占)

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `case_id` | str | — | 全局唯一 (e.g. "LA-CH04-023") |
| `course_id` | str | — | ★ 显式 (HEC-6) |
| `question` | str | — | 学生提问原文 |
| `question_type` | Literal | — | definition/derivation/cross_chapter/refusal/ambiguous |
| `associated_kc_id` | str \| None | None | 跨章题可空 |
| `bloom_level` | str | "Understanding" | 6 阶 Bloom 之一 |
| `gold_answer` | str | — | 标准答案 |
| `gold_citations` | list[Citation] | [] | 期望出现的引用 (file_name · locator) |
| `gold_evidence_chunks` | list[str] | [] | 期望检索到的 Chunk ID |
| `answerability` | bool | True | false = 应拒答 |
| `pedagogical_constraint` | str | "" | 给 Judge 看的强教学规约 |

**调研依据**: `research_result/FoxSay RAG 评测设计.md` 第 "Ground Truth 字段规范" 节。

### KGNode / KGEdge / KnowledgeGraphResponse (line C 独占)

| schema | 字段 | 默认值 | 语义 |
|---|---|---|---|
| KGNode | id, label, chapter_id | — | KC.id, KC.name, KC.chapter_id |
| KGNode | mastery: float | 0.0 | 一期固定 0,二期接学情 |
| KGNode | importance: Literal | "medium" | high/medium/low |
| KGNode | cognitive_dimension | "conceptual" | KLI 5 分类 |
| KGEdge | source, target | — | KC.id |
| KGEdge | strength: float | 1.0 | 等于 KCPrerequisite.dependency_strength |
| KGEdge | edge_type | "prerequisite" | prerequisite / related |
| KnowledgeGraphResponse | course_id, nodes, edges | — | ★ course_id 显式 |
| KnowledgeGraphResponse | layout_hint | "dagre" | 给前端布局算法提示 |

---

## KC schema 升级清单

| 字段 | 状态 | 用途 / 默认 |
|---|---|---|
| `prerequisites: list[str]` | **deprecated → migrated** | model_validator 自动搬到 prerequisites_raw |
| `prerequisites_raw: list[str]` | **新增** | 旧字符串保留,给 line A ETL 重新对齐 |
| `prerequisites: list[KCPrerequisite]` | **新增 (覆盖同名)** | 结构化,line A 填,B/C 消费 |
| `common_mistakes: list[str]` | **保留** | 不破坏既有 LLM 抽取代码 |
| `common_mistakes_v2: list[CommonMistake]` | **新增** | 结构化,带 bug_rule_id,优先级高于 v1 |
| `cognitive_dimension: Literal[...]` | **新增** | KLI 5 分类,default="conceptual" |
| `derivation_steps: list[str]` | **新增 (理工偏)** | 推导过程,LLM 抽取填充 |
| `last_practiced_at`, `mastery_score`, `srs_state` | **新增 (留接口)** | 一期不更新,二期"贯穿学期"用 |
| `viewpoints`, `counter_arguments`, `classical_quotes` | **新增 (文科留位)** | 一期不写 |

**KC.id 仍是 uuid5(course:chapter:name) — 不变,保证幂等**

---

## Migration 策略 (零数据搬迁)

由于 `wiki_kcs` 表用 `data_json TEXT` 整段存 KC JSON,**无需 ALTER TABLE,无需 SQL migration**。

机制:
1. 老 KC JSON (含 `prerequisites: list[str]`) 入库时是合法的
2. 反序列化 (`KC.model_validate_json`) 触发 `model_validator(mode="before")`
3. 自动检测:`prerequisites` 是 `list[str]` (非 `list[dict]`) → 平移到 `prerequisites_raw`,`prerequisites` 设空
4. 下次 `save_kc` 时,新 JSON 写入数据库,自然完成"惰性迁移"

测试覆盖见 `backend/tests/test_pr0_contracts.py::test_kc_sqlite_round_trip_legacy_format`。

---

## 模型分工 (新增配置项)

| 配置 | 默认值 | 用途 |
|---|---|---|
| `JUDGE_API_KEY` | "lm-studio" | LM Studio 不验证 key |
| `JUDGE_API_BASE` | "http://localhost:1234/v1" | LM Studio 默认端口 |
| `JUDGE_MODEL_NAME` | "qwen/qwen3.5-9b" | 主 Judge,reasoning 模型 (~2000 token/次) |
| `JUDGE_FAST_MODEL_NAME` | "qwen/qwen3-4b-2507" | 批量轻活,非 reasoning (5 选 1 / 格式校验) |
| `RERANKER_MODEL_NAME` | "qwen3-reranker-0.6b" | NLI 蕴含判定,评测 v2 ALiiCE 用 |

DeepSeek V4 Flash (现有 deepseek_* 配置) 留在**生成端** (KC 抽取 / ChapterWiki / 出题 / Agent 回答)。Qwen 系列留在**评判端**,按任务复杂度分流:
- 复杂判断 (Faithfulness / 教学规约) → qwen3.5-9b (reasoning, 慢, 高质量)
- 批量轻活 (cognitive_dim 5 选 1 / JSON schema 校验) → qwen3-4b-2507 (非 reasoning, 快)
- NLI 蕴含 (ALiiCE 引用细粒度判定) → qwen3-reranker-0.6b (专用 reranker,免 BGE)

**禁止** DeepSeek 当 Judge — self-preference bias (调研 `research_result/FoxSay RAG 评测设计.md` 第 "LLM Judge 偏见" 节)。

---

## 三线启动门禁

PR0 合并 (本文件 + schemas/foxsay.py + config.py + env.example + tests) 后,
三线 worktree 才可以并行开启:

```
worktree/A — feature/line-a-prereq-etl
   消费: KC.prerequisites_raw → 产出 KC.prerequisites (KCPrerequisite list)
   产出: backend/scripts/align_prerequisites.py

worktree/B — feature/line-b-eval-suite
   产出: data/golden_suite_v0_200.json (200 个 EvalCase)
   消费: 现有 KC (用 prerequisites_raw 即可,不阻塞等 A)

worktree/C — feature/line-c-kg-viz
   产出: GET /courses/{id}/knowledge-graph → KnowledgeGraphResponse
   消费: A 完成前用 prerequisites_raw fuzzy fallback,A 完成后切 prerequisites
```

---

## 修改本契约的流程

1. 不允许直接 push,必须 PR + 至少 1 review
2. 任何字段重命名 / 删除必须先有 migration plan
3. 已上线后再加字段:加默认值 OK,不需要 PR0 级 review
4. Literal 字段加新枚举值:加默认值兼容 OK
5. 删除 Literal 枚举值:必须 PR0 级 review
