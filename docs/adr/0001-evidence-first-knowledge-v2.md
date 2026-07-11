# ADR-0001：证据优先的知识体系 V2

- 状态：**Accepted（已接受）**
- 日期：2026-07-11
- 决策范围：FoxSay 课程级知识体系的后续重构边界

> 本 ADR 记录已达成的架构决策和实施约束；它**不**声明任何 V2 代码、数据迁移或端到端能力已经完成。

## 背景

现有知识体系把材料、DMAP、章节摘要、课程骨架、KC、图谱和检索结果混作多个彼此可能矛盾的表示，且引用无法稳定回到原文。V2 的首要目标不是增加更多图或 Agent 工具，而是让每个可展示的知识结论都能回溯到当前课程的可定位证据。

## 决策

### 1. `SourceFragment` 与 `EvidenceRef` 是事实与溯源的唯一基础

- `SourceFragment` 是课程材料解析后得到的、带稳定 ID 的原文证据单元。它显式绑定 `course_id`、`material_id`、位置（页/幻灯片/标题路径等）和解析版本。
- `EvidenceRef` 是下游对象引用证据的统一结构，至少包含 `course_id`、来源类型、来源 ID、`fragment_id`、可读定位信息；不得仅以文件名或人类可读 locator 充当主键。
- 课程回答、KC、术语、关系、讲义、练习、复习步骤和笔记的材料性结论均使用 `EvidenceRef`。原文预览按稳定 fragment ID 打开，不依赖前端解析字符串定位。

### 2. 语义与视觉均为证据上的派生产物

- `SemanticAtom` 表示从文字材料中抽取的最小语义单元（概念、定义、公式、条件、命题、例子等），必须关联一个或多个 `EvidenceRef`。
- `VisualAtom` 表示图、表、公式截图、流程图、幻灯片视觉布局等无法可靠由文本解析恢复的证据单元，同样必须关联 `EvidenceRef`，并保留其生成方式与置信信息。
- Atom 不是新的无来源“知识真相”；它们是可替换、可重建、可审计的索引层。

全文或向量索引（包括 Qdrant）只能产生候选；任何可展示的材料证据都必须以当前 `course_id`、material revision 与 fragment identity 回到 canonical `SourceFragment` 重新验证和水合。索引 payload 中的文本、locator 或文件名不是事实源。

### 3. Outline、Term、KC 与关系均从 Atom/证据派生

- `CourseOutline` 是前端唯一的课程导航事实视图：章节/小节及其证据覆盖。它取代多个并列、互相竞争的骨架表示。
- `Term`、`KC`、章节摘要及先修/关联关系均是派生对象，必须携带证据和构建 revision。
- 关系图只是 Outline/KC 关系的可视化投影，不是独立事实源，也不引入图数据库作为 MVP 前提。
- 没有充分证据的概念、术语或关系应当标记为缺失/低置信，不能以完整知识卡或确定关系展示。

### 4. 严格区分课程材料与 Fox 补充说明

- 所有回答使用明确 provenance：`answer_source: "material" | "supplementary"`，并保留 `confidence_status`、相关性分数和证据引用。
- 材料型内容必须可回到 `EvidenceRef`；材料不足时，Fox 的通用补充必须显式披露“课程材料未覆盖”，不得伪装为课程结论。
- 若同一回复同时包含两类内容，UI/响应应将其清晰分段，而不是静默混合。

### 5. 以 revision 与持久化 job 管理增量构建和失败

- 每门课程维护 `source_revision`（材料事实变化）与 `knowledge_revision`（已成功构建的派生知识）。两者不一致即为 stale，不得把旧知识显示为最新结果。
- 解析、fragment 构建、语义抽取、条件视觉理解、Outline/KC/Term 构建、索引等均以可观察、可重试的 job 表示；错误必须携带阶段、受影响材料和可重试性。
- 前端以 `KnowledgeStatus` 快照作为状态事实源；SSE 仅负责提示刷新，不能是唯一状态通道。
- 支持部分可用：已完成材料可以被透明地用于问答，但响应与 UI 必须说明当前覆盖范围。

检索可用性与 CRAG 置信度正交：`available + out_of_scope` 是成功检索后的材料边界；`unavailable` 是未就绪或操作失败，必须携带结构化错误、没有 CRAG 置信度和材料引用，不能叙述为“材料未覆盖”。

### 6. 模型职责按证据类型分工

- **DeepSeek** 负责以文本为中心的生成与抽取：基于已检索证据生成课程回答、文本语义 Atom、摘要及教学表达。它的输出是派生内容，不取代原始证据。
- **Qwen VLM** 仅在材料含有文本解析无法可靠恢复的视觉信息时条件性调用，用于生成带来源的 `VisualAtom` 候选；不作为所有材料的默认步骤，也不以未验证的视觉结论直接支撑课程回答。
- 新模型名、端点或服务配置仍须遵守 HEC-5 的验证要求；本 ADR 不新增或假定具体模型标识。

### 7. Agent/ReAct 不是 V2 的先决条件

- V2 的证据、状态、Outline、检索和 AnswerEnvelope 契约应可在没有复杂 Agent 编排时独立工作。
- ReAct 工具链、动态 Skill、工具调用时间线、自动讲义/闪卡/复杂出题等作为后续消费者重构；它们必须消费既定的 EvidenceRef、revision、scope 和 AnswerEnvelope，而不能另建旁路知识体系。

独立的后端 `RetrievalOutcome` / `AnswerEnvelope` 契约不构成 chat、Agent、SSE 或前端迁移；这些消费者必须在后续任务显式接入后，才能宣称使用 V2。

## 实施后果

1. 后端 public response 与前端公共类型需以 `course_id`、revision、EvidenceRef 和结构化错误为共同边界；现有仅含 `file_name/locator` 的引用不可作为 V2 最终契约。
2. 应提供至少以下能力：知识状态快照、按 fragment ID 的原文预览、CourseOutline 查询、带 provenance 的答案完成事件，以及显式的检索来源 scope。
3. 前端先展示真实的 empty/processing/partial/ready/failed/stale 状态，再开放课程地图、KC、复习和图谱；“材料 ready”不等于“知识体系 ready”。
4. 新增或重试材料必须触发 revision 失效与增量 job；旧的讲义、练习、复习内容需标记其基于的 knowledge revision。
5. 复习计划、/btw、笔记和后续生成式功能必须保留知识点/证据引用；没有学习诊断数据时不得将材料推测难点表述为学生个人薄弱项。
6. 现有 Skeleton、ChapterWiki、CourseIndex、KC 或图谱接口可在迁移期兼容存在，但不得继续被前端并列视为独立事实源。

## 非目标

- 本 ADR 不承诺图数据库、跨课程知识检索、学习掌握度/SRS、自动反馈训练闭环或完整 Agent 重写。
- 本 ADR 不把视觉模型调用扩展为默认 OCR/解析替代，也不允许无证据的模型输出进入课程知识事实层。
