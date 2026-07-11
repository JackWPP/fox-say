# FoxSay Course Agent V2：系统重构与全流程实施计划

> 状态：**方案已确认，尚未开始实现**
>
> 日期：2026-07-11（Asia/Shanghai）
>
> 主验收课：**线性代数**（验证工具，不是产品边界）
>
> 工程任务：`V2-F0`～`V2-F8`；状态与领取范围以
> [`knowledge-system-v2-task-registry.md`](knowledge-system-v2-task-registry.md) 为唯一事实源。
>
> 前置交接：[`knowledge-v2-agent-handoff.md`](knowledge-v2-agent-handoff.md)

## 1. 决策摘要

本阶段要完成的是一套**面向任意课程的 Course Agent V2 系统重构**，覆盖后端 Agent Runtime、Chat/Review/Artifact workflow、模型审计、持久状态以及电脑端 Course Workspace。线性代数承担主要工程验收与现场演示，因为它能同时压测定义、公式、推导、步骤、跨章节关系、图示、出题和备考；它不是运行时能力或 UI 的限定条件。

重构必须同时证明四件事：

1. FoxSay 确实把任意课程材料构造成可追溯的课程知识体系，而不是只做一次向量搜索。
2. Agent 确实消费当前 V2 Evidence、Outline、Term、KC 与 Relation，并以通用 workflow 完成普通问答、深度理解、学习产物和对话式备考。
3. 现有电脑端前端完成一次围绕 Agent 运行状态、证据、课程知识和备考对话的系统重构，不再由多套 legacy Chat/Review/Prompt hack 拼接体验。
4. 从课程建立、材料处理、知识展示、问答、复习到 `/btw` 的用户主流程尽量完整跑通；未完成环节必须诚实标为降级或后续项。

所有 Agent schema、工具、prompt、路由和组件必须 course-agnostic，不允许在业务代码里硬编码“特征值”“矩阵”、固定章节或数学专属字段。运行时范围由 `course_id + source_revision + knowledge_revision` 决定，教学策略由当前证据类型和用户请求选择。线性代数是主验收集；另用一门小型文字型合成课程做通用性 smoke，防止系统在无公式、无先修边时失效。本阶段仍不为老师端、硬件端、跨课程 Agent、完整 SRS 或全学科模板市场提前建设基础设施。

## 2. 当前起点与迁移边界

### 2.1 已经完成、应直接复用

- `SourceFragment → CourseOutline → SemanticAtom → Term → KnowledgeComponent → KCRelation` 的 V2 链路已经闭合。
- 材料 revision、course/source/knowledge revision、持久 `knowledge_jobs`、lease、重试和发布栅栏已经存在。
- `retrieve_current_fragments(...)` 已提供 exact-first、可选向量召回、canonical rehydrate、CRAG 和结构化 `unavailable`。
- `AnswerEnvelope` 已能从本轮 canonical hits 组装不可伪造的 V2 citation。
- `V2AgentTools` 已能安全只读当前 Outline、Term、KC、Relation、Evidence 与 `KnowledgeStatus`。
- 前端已具备 `KnowledgeStatus`、V2 `EvidenceRef` 类型和按 opaque `fragment_id` 打开原文的 CitationCard 边界。

### 2.2 尚未迁移、不能继续伪装成 V2

- 生产 `/chat/stream` 仍运行 legacy Wiki/DMAP/KC 的 8 轮 ReAct。
- 模型可以不检索直接回答；引用仍可能由模型正文正则或 filename/locator fallback 产生。
- Chat 模型调用尚未进入 V2 审计、预算与 `max_retries=0` 边界。
- Chat history 没有保存 source/knowledge revision、retrieval availability、answer source 与完整 AnswerEnvelope。
- `/btw` 仍硬编码 `grounded` 和 `relevance=1.0`；复习计划和步骤仍读取 legacy Skeleton。
- 欢迎概述、讲义、Quiz、知识图谱和部分 Studio 内容仍把 legacy 投影当事实输入。

迁移期间允许以 feature boundary 让整条请求选择 legacy 或 V2，但**禁止在一条回答里合并两套事实**。所有新 Course Agent workflow 都只消费 V2；线性代数主验收不接受 legacy fallback。

## 3. 主验收素材与通用性验证

### 3.1 仓库内合成素材

新增的自动测试和 demo harness 使用合成、可公开的线性代数 Markdown/图片，不提交用户材料。合成素材至少覆盖：

| 材料 | 内容 | 主要验证点 |
| --- | --- | --- |
| A：向量空间 | 向量空间、子空间、基、维数、线性组合、线性无关 | 定义、标题召回、先修关系 |
| B：矩阵与方程组 | 矩阵运算、初等变换、秩、线性方程组、可逆矩阵 | 算法步骤、跨章节联系 |
| C：特征理论 | 特征值、特征向量、相似矩阵、对角化及条件 | 公式、条件、推导、综合问答 |
| D：例题与易错点 | 典型判定题、反例、必要/充分条件区分 | 教学解释、出题与批改 |

可增加一张合成二维线性变换/特征方向示意图验证 `visual_analysis` 的任务、审计和 UI 状态；在 VisualAtom 尚未正式投影为当前可引用证据前，它只能作为视觉能力展示，不能支撑 Chat 的材料结论。

### 3.2 本地真实材料

真实 PDF/PPT 只用于本地演示和脱敏验收，不提交仓库、数据库、解析产物、embedding、prompt 或模型输出。真实演示必须通过公开上传 API 和持久任务链进入系统，不能直接向 V2 表灌数据。

### 3.3 线性代数主验收问题集

最小问题集按能力而不是按固定答案组织：

| 类型 | 示例 | 预期 |
| --- | --- | --- |
| 定义 | “什么是特征值？” | `grounded`，引用定义 fragment |
| 条件 | “矩阵可对角化需要什么条件？” | 多证据回答，区分充分/必要条件 |
| 方法 | “如何判断一组向量线性无关？” | 给出课程材料中的步骤和定位 |
| 推导 | “为什么相似矩阵有相同特征值？” | 基于公式/定理证据解释，不伪造推导来源 |
| 跨章节 | “线性无关、满秩和可逆之间是什么关系？” | 触发 deep-dive，读取多个 KC/Relation |
| 模糊 | “它为什么能对角化？” | 利用会话锚点或追问，不猜对象 |
| 部分覆盖 | “谱定理和对角化有什么区别？” | `ambiguous` 时只陈述材料能支持的部分 |
| 超范围 | “光电效应是什么？” | `available + out_of_scope + supplementary`，无材料引用 |
| 系统故障 | 索引未就绪/检索失败 | `unavailable`，可见错误与重试，不说“材料未覆盖” |
| 选材范围 | 只选择材料 C 后询问秩 | 明确受限结果，不偷偷扩大到全课程 |

### 3.4 文字型课程通用性 smoke

增加一门小型合成“学术写作基础”课程，只用于防止数学硬编码，不与线性代数争夺主演示资源。它包含论点、证据组织、段落结构和引用规范等文本章节，并允许零公式、零 KC relation 的合法结果。Smoke 至少验证：

- 同一上传、KnowledgeStatus、Outline/KC、Chat 和 Citation 契约可运行；
- quick answer 能引用文本 fragment，out-of-scope 能透明补充；
- Course Workspace 在无公式、零关系和较少 KC 时不会空白、报错或伪造关系；
- deep-dive 若缺少 relation，可以基于 Outline/Evidence 做文本比较并明确降级；
- prompt、工具、Artifact 和 Review schema 没有线性代数专有字段或固定中文章节名。

## 4. 通用全流程与线性代数主演示

系统面向所有课程提供同一条主流程；线性代数将它具体化为主要演示脚本和高难验收集。

### 4.1 线性代数主演示

```text
创建“线性代数”课程
  → 上传合成或本地真实材料
  → SourcesPanel 展示持久处理状态
  → V2 知识链逐层就绪
  → 第一份课程简报 + 可交互课程地图
  → 快速问答与可打开的原文引用
  → “深度理解”狐狸小队处理跨章节问题
  → 保存一个带 revision/evidence 的学习产物
  → 切换超级备考，生成当前 revision 的复习计划
  → 讲解 → 作答 → 批改 → 针对缺口补讲
  → /btw 插问并返回原复习步骤
  → 展示本次会话产生的学习观察和进度
  → 修改一份材料，旧答案/产物/计划显示 stale
```

现场演示可以预先运行同一公开流程得到 warm course，避免把网络和模型等待当舞台风险；同时必须保留一份 cold-start 录屏或自动 harness 证明课程确实从上传开始构建，不能提交预造数据库冒充全流程。

### 4.2 通用能力契约

- Workflow 只依据用户意图、证据可用性、Outline/KC/Relation 能力状态和显式模式路由，不依据课程名路由。
- `quick_answer`、`deep_dive`、`course_brief`、`study_artifact`、`review_plan`、`review_session` 与 `/btw` 对所有课程使用同一 public schema。
- Tutor 根据当前 Evidence/Atom/KC 的实际类型选择“定义解释、步骤讲解、比较、推导、例子或文本归纳”，不假设每门课都有公式、先修边或可计算题。
- Outline ready 但 KC/Relation 缺失时，原文问答和章节导航仍可用；UI 与 Agent 只能降级对应增强能力，不能把空投影当系统故障或伪造关系。
- 知识展示组件按通用 section/KC/relation/evidence DTO 渲染；数学公式由 Markdown/KaTeX 处理，不进入业务主键或专属字段。
- 除线性代数主套件外，F2/F4/F8 必须运行一门小型文字型合成课程，至少验证无公式、零关系、不同章节命名和超范围回答。

## 5. 产品与界面设计

### 5.1 一个 Course Workspace，两种模式

继续使用 NotebookLM 风格三栏，但明确职责：

- **左侧 Sources**：材料、当前选择范围、revision-aware 处理进度、错误与重试；个人笔记与课程材料分组显示。
- **中间 Conversation**：日常学习与超级备考共用的对话主舞台。模式切换改变 Agent workflow 和交互卡片，不跳到割裂的第二套产品。
- **右侧 Studio**：课程地图、知识追踪、复习计划、学习产物、会话进度；它保存对话产生的结构化结果，不用 prompt hack 反向污染普通 Chat。

### 5.2 前端系统重构范围

这次不是给现有页面加几张 Agent 卡片，而是重整当前电脑端的主状态与组件边界：

```text
CourseWorkspace
  ├─ SourcesPane
  │   ├─ MaterialScopePicker
  │   └─ KnowledgeBuildStatus
  ├─ ConversationPane
  │   ├─ SessionSwitcher
  │   ├─ AgentRunTimeline
  │   ├─ AnswerEnvelopeView
  │   ├─ ReviewConversation
  │   └─ CourseComposer
  └─ StudioPane
      ├─ CourseMap
      ├─ KnowledgeTrace
      ├─ ReviewPlan
      ├─ LearningArtifact
      └─ Notes
```

- 建立唯一 `useCourseAgentRun`/等价数据层，负责 SSE、取消、run/session/course fence、snapshot 对账和可见错误；Chat、Review、Artifact 不再各写一套流式解析器。
- 建立唯一 `AnswerEnvelopeView`，负责 material/ambiguous/supplementary/unavailable、citation、warning 和 stale 渲染。
- 合并或删除当前未挂载的 `ChatTab/ChatMessage` 第二套实现，实际入口只保留一个 Conversation tree。
- `LectureView`、`QuizView` 不再通过普通 Chat endpoint 塞 prompt 或在浏览器信任模型 JSON；结构化产物由对应 workflow/API 产生并在 Studio 渲染。
- 日常学习与超级备考共享 CourseWorkspace；Review 以对话卡片推进，右侧展示计划和进度，不再是一套孤立页面状态。
- 前端不从 `course.status`、动画、localStorage 或空数组猜测知识/Run 终态；状态由 KnowledgeStatus、AgentRun snapshot、Review/Artifact 持久记录驱动。
- 本阶段以桌面端完成度为优先，仍需保证窄屏可基本操作，但不扩展为移动端产品重写。

### 5.3 “知识体系已经构建”的可见证据

重构后的 Course Workspace 为所有课程提供三个知识视图，线性代数负责验证其高密度数据表现：

1. **构建状态**：fragment、Outline section、Semantic Atom、Term、KC、Relation 的当前计数与状态；状态来自 SQLite/`KnowledgeStatus`，不是 SSE 猜测。
2. **课程地图**：按 V2 CourseOutline 展示章节与小节，KC 挂在对应 section，Relation 只展示有 EvidenceRef 的当前关系。
3. **知识追踪抽屉**：点击“特征值”等 KC，可看到 `KC → Term → Atom → SourceFragment` 的追溯链，并能打开原文页/幻灯片。

课程简报只能根据当前 Outline/KC/Relation 描述“课程包含什么、材料重点集中在哪里、建议从哪些先修项开始”，没有真实作答记录时不得声称“你最薄弱的是某章”。

### 5.4 Agent 协作过程

用户始终面对一个 FoxSay；后台 specialist 以可折叠的阶段卡展示：

- `Evidence Scout`：定位到若干 current fragments。
- `Course Mapper`：找到相关 section、KC 和 evidence-constrained relation。
- `Tutor`：组织讲解。
- `Examiner`：生成题目与 rubric。
- `Grader`：依据 rubric 和证据评价本次作答。
- `Verifier`：检查 revision、引用、输出结构和发布条件。

前端只展示动作、结果数量、耗时和可见错误，不展示隐藏思维链或模型内部推理文本。

### 5.5 回答的四种诚实状态

| 后端状态 | UI 文案与行为 |
| --- | --- |
| `available + grounded + material` | “基于本课材料”，展示 canonical citations |
| `available + ambiguous + material` | “材料证据有限”，指出能确认与不能确认的边界 |
| `available + out_of_scope + supplementary` | “本课材料未覆盖 · Fox 补充”，无材料 citation |
| `unavailable` | 系统故障卡、错误阶段和重试；不渲染成普通知识回答 |

首版不允许 `ambiguous` 在同一自由文本中偷偷混入通用知识。若演示确实需要“材料说明 + 通用补充”，先在 `V2-F0` 定义显式 `AnswerSection[]` provenance，再实现分块 UI；不能只靠一句免责声明。

## 6. Agent Runtime 设计

### 6.1 总体流程

```text
Chat / Review / Studio request
  → Transport：校验 course、session、idempotency 和 source scope
  → TurnScope：固定 source_revision / knowledge_revision
  → Run Director：选择 workflow，不产生课程事实
  → Evidence Gate：V2 retrieval + CRAG
  → Specialist nodes：按 workflow 读取受限 V2 工具
  → Audited Model Gateway：预算、usage、elapsed、max_retries=0
  → Verifier：citation allow-list + revision publication fence
  → AnswerEnvelope / Artifact / Review output
  → DB terminal state
  → SSE compatibility events
```

### 6.2 Workflow 类型

#### `quick_answer`

- 适用：定义、公式解释、单概念、普通追问。
- 固定先做 V2 retrieval；模型无权跳过。
- 默认一次 Tutor 调用；检索充分时不进入 ReAct。
- 最终 citation 只能来自本轮 `RetrievalOutcome`。

#### `deep_dive`

- 适用：跨章节联系、先修链、比较、系统讲解。
- Evidence Scout 先产生基础 EvidencePack。
- Course Mapper 只读取当前 Outline、按 query/ID/limit 限制的 Term/KC/Relation；不得把整门课列表塞入 prompt。
- Tutor 生成结构化讲解；Verifier 检查每个材料性结论的 citation alias。
- 最多 2～3 次受审计模型调用；没有无上限自主循环。

#### `course_brief`

- 只在 source/knowledge revision ready 后生成或刷新。
- 输入为当前 Outline/KC/Relation 的受限摘要与 EvidenceRef，不读 legacy Wiki/CourseIndex。
- 输出为 revision-bound Studio artifact；旧 revision 自动 stale。

#### `study_artifact`

- 首轮系统重构至少跑通一种核心产物，推荐通用的“章节复习简报”或“概念关系讲义”；schema 不得依赖数学专属字段。
- 产物有明确 schema、EvidenceRef、source/knowledge revision 与生成状态。
- Lecture/Quiz 不再通过给普通 Chat 塞 prompt 来伪装独立功能。

#### `review_plan`

- 输入：考试日期、当前 Outline/KC/Relation、已有的真实 ReviewAttempt/LearnerObservation。
- 没有学习记录时，优先级只能基于章节顺序、材料覆盖和先修关系，不能伪造个人薄弱点。
- 先由确定性 scheduler 给出天数/时间硬边界，再由模型组织教学表达。

#### `review_session`

```text
briefing → teach → attempt → feedback → recap → done
```

- Coach 选择当前计划项，不自由跳课程范围。
- Examiner 生成 `Question + Rubric + KC IDs + EvidenceRefs` 的结构化题目。
- Grader 只比较用户答案、rubric 与证据，返回“正确点、缺失点、错误点、不确定项”。
- 本次 attempt 可以产生最小学习观察；它不能修改课程 KC 或 Relation。
- Tutor 只针对已验证缺口补讲，之后进入下一题或 recap。

#### `btw`

- 是 `review_session` 当前 step 下的 child turn。
- 复用 `quick_answer/deep_dive` 的完整 Evidence/CRAG/AnswerEnvelope 路径。
- 持久化 `return_anchor = review_session_id + day/item + step_id`。
- 回答成功、失败或取消都不自动推进主复习状态。

## 7. 运行时数据契约

### 7.1 `TurnScope`

```text
turn_id
course_id
session_id
workflow_kind
source_revision
knowledge_revision
scope_mode: all_ready | selected
selected_material_ids
selected_note_ids
review_context (optional, explicit IDs only)
```

- `scope_mode=selected` 的空列表表示没有材料，不能退化为全课程。
- 所有 material/note/session ID 都由服务端验证属于当前 course。
- 个人笔记首版只作为“用户上下文”，不能生成 material citation。

### 7.2 `AgentRun` 与 `AgentStep`

```text
AgentRun
  run_id, turn_id, workflow_kind
  course_id, session_id
  source_revision, knowledge_revision
  status: accepted | retrieving | planning | executing | composing |
          verifying | completed | failed | interrupted | cancelled | stale
  token_budget, error, created_at, updated_at

AgentStep
  step_id, run_id, agent_role, step_type
  status, model_call_id, output_type
  input_fingerprint, elapsed_ms, error
```

不持久化隐藏思维链。`AgentStep` 只保存可审计的动作、输入 fingerprint、结构化产物引用、usage 和错误。

### 7.3 Chat terminal record

Assistant history 必须无损保存：

- `run_id`、`turn_id`、`course_id`、`session_id`
- source/knowledge revision
- retrieval availability、confidence status、answer source
- AnswerEnvelope citations、coverage、warnings、structured error
- terminal status 与 model-call audit identity

历史文本只帮助理解追问，不是新一轮的课程证据。新一轮仍重新检索；历史 revision 与当前不同，前端显示“基于旧版材料”。

### 7.4 最小学习观察

```text
LearnerObservation
  observation_id
  course_id, kc_id
  observation_type:
    explicit_difficulty | correct_attempt | incorrect_attempt |
    missing_condition | repeated_clarification
  confidence
  source_run_id, source_attempt_id
  created_at
```

首轮系统重构只要求 observation 可追溯和可展示，不在本阶段实现完整 SRS、长期遗忘曲线或跨课程用户画像。

## 8. 持久化、模型审计与预算

### 8.1 不混淆两类运行时

- `knowledge_jobs` 继续是材料/课程知识构建的唯一事实源。
- Chat/Agent 使用独立 `agent_runs`/`agent_steps`，不得为满足外键创建假的 knowledge job。
- 交互式短 Run 可在请求内执行并持久化终态；超过请求生命周期的 artifact Run 才进入受控持久执行。不得使用裸 `asyncio.create_task()` 承载需要恢复的产物。

### 8.2 泛化 model-call owner

现有 `model_call_audits.job_id → knowledge_jobs` 不能直接承载 Chat。迁移目标：

```text
owner_type: knowledge_job | agent_run
owner_id
owner_attempt
budget_scope: knowledge_build | interactive | review | artifact
```

- knowledge-job owner 保留 attempt/lease/revision 栅栏。
- agent-run owner 校验 run 状态、course、revision 和 per-run budget。
- interactive/review 预算不能静默吃掉知识编译预算。
- query embedding 若调用外部服务，同样必须关联 run 并审计；未完成审计前 exact-only 只能作为 canary，不能据此自信判定 out-of-scope。

### 8.3 调用上限

| Workflow | 默认模型调用预算 |
| --- | --- |
| quick answer | 1 次正文生成；exact 不足时最多一次受审计 query embedding |
| deep dive | 2～3 次受审计 text call，含必要的 planner/repair/verify |
| course brief / artifact | 每个产物独立硬预算，失败不无限重跑 |
| review question | 1 次 Examiner 结构化生成 |
| grading | 1 次 Grader；只有实际缺口才调用 Tutor 补讲 |
| `/btw` | 复用 quick/deep 上限，不继承主线剩余轮数 |

SDK 内部重试固定为 0；若允许一次结构化 repair，必须是新的可见 audit call。真实默认 token cap 只有在标杆课记录 p50/p95、输入输出 token 和失败成本后再调整。

## 9. API 与 SSE 迁移契约

### 9.1 Chat 请求

第一阶段保留 `/courses/{course_id}/chat/stream`，扩展 request：

```json
{
  "question": "线性无关、满秩和可逆有什么关系？",
  "session_id": "...",
  "client_request_id": "...",
  "workflow_hint": "auto | quick_answer | deep_dive",
  "source_scope": {
    "mode": "all_ready | selected",
    "material_ids": ["..."]
  },
  "user_context_note_ids": ["..."]
}
```

服务端生成并返回真实 `run_id/turn_id`；不接受客户端指定 course/revision。

### 9.2 SSE 事件

首次迁移兼容现有 `tool_call | token | done | error` 事件名，同时增加 version 与 run identity：

```text
accepted   {run_id, turn_id, session_id, source_revision, knowledge_revision}
phase      {run_id, phase, agent_role, display_message}
token      {run_id, delta}
done       {run_id, message_id, envelope}
error      {run_id, error_code, message, retriable}
```

若必须严格保留旧监听器，`phase` 可临时映射为兼容 `tool_call`，但 UI 只展示友好阶段名。所有事件都带 run/session/course fence；A 会话的迟到事件不能写入当前 B 会话。

### 9.3 Run snapshot

增加只读 `GET /courses/{course_id}/agent-runs/{run_id}` 返回持久状态和终态引用。SSE 中断后前端依靠此 API 对账；SSE 本身不是完成事实源。

### 9.4 知识展示 API

为 Course Workspace 提供 course-agnostic、current-only 的只读 DTO，不直接暴露整库表：

- 当前课程地图：Outline + bounded KC/Relation projection。
- 当前知识计数/阶段：扩展 KnowledgeStatus 或独立 summary。
- 单 KC 知识追踪：KC → Term → Atom → EvidenceRef。

所有 endpoint 显式 course/revision 校验，拒绝 stale、unknown 和 cross-course ID。

## 10. 失败、取消与 revision 更新

- session 创建、切换、删除和 touch 都必须同时校验 `course_id + session_id`。
- provider、embedding、Qdrant、JSON schema、budget、timeout、citation 和 revision 错误均为结构化终态，不能保存 `"(empty)"` 成功消息。
- 用户可以取消当前 Run；取消成功后停止发布答案，已发生的模型 usage 仍保留审计。
- 生成过程中 source revision 改变，Verifier 将 Run 标为 `stale_turn_source`，不发布旧引用答案。
- 材料更新后：旧聊天保留历史但显示 stale；Course Brief、Artifact、ReviewPlan 标为 stale；新问题重新检索 current evidence。
- prompt 中的课程材料一律视为不可信数据片段；材料里的“忽略系统规则”等文本不能改变 Agent 工具、scope、citation 或输出协议。

## 11. 实施任务与提交边界

每个子任务开始前由协调者在台账领取并写明互斥文件范围。下表定义目标与依赖；精确活动状态仍以任务台账为准。

### V2-F0：Course Agent V2 方案与契约冻结

- **交付**：本文、台账子任务、交接链接；冻结通用 quick/deep/artifact/review 范围、前端重构边界、notes policy、mixed-answer policy、run/revision/SSE 基线，以及线性代数主验收集。
- **非目标**：不改业务代码、SQLite schema、前端行为，不调用模型。
- **验收**：相对链接可读；任务依赖、文件范围、成本和重复验证命令齐全；文档不声称 runtime 已实现。

### V2-F1：AgentRun、课程隔离与模型审计底座

- **依赖**：F0。
- **建议范围**：AgentRun/model audit schema、SQLite migration/store、session course fence、配置与 backend tests；共享 schema 由协调者串行修改。
- **交付**：agent run terminal state、idempotency、owner-type audit、interactive/review budget、`max_retries=0`。
- **非目标**：不接生产 Chat、不实现多 Agent、不改前端。
- **验收**：旧 DB 安全迁移；跨课程 session/run mutation 被拒绝；预算拒绝零 provider call；失败/usage/elapsed 可见；knowledge-job lease 语义无回归。

### V2-F2：V2 quick-answer 垂直切片

- **依赖**：F1、已完成 V2-C/D。
- **建议范围**：TurnScope、EvidencePack、audited chat writer、AnswerEnvelope integration 和 service tests。
- **交付**：course-agnostic `retrieve → CRAG → writer → server assemble → revision fence`，先不接 HTTP。
- **验收**：线性代数主问题集的 grounded/ambiguous/out-of-scope/unavailable，以及一门文字型合成课程 smoke；无检索直接回答不可能；伪 fragment/cross-course/stale citation 无法发布；模型错误不产生成功答案。

### V2-F3：Chat API、SSE 与历史迁移

- **依赖**：F2。
- **建议范围**：`api/chat.py`、chat persistence、history/session API、SSE contract、backend endpoint tests。
- **交付**：现有 stream endpoint 对所有课程整条请求切 V2；done 携带完整 envelope；history 无损恢复；run snapshot；取消/断线对账。
- **验收**：API → SSE → DB → history round trip；失败不保存空答案；旧会话迟到事件不能写入新会话；selected empty scope 不扩大。

### V2-F4：知识体系展示与诚实回答 UX

- **依赖**：F3。
- **建议范围**：前端公共类型串行更新、统一 Agent run 数据层、CourseWorkspace、SourcesPanel、Conversation、AnswerEnvelope、Agent timeline、Knowledge Studio、Review Conversation、Citation 和样式；不在旧组件上分散打补丁。
- **交付**：现有电脑端完成系统重构：真实 V2 状态、四种回答状态、可打开 citation、run phase、stale history、Outline/KC/Relation/trace 展示、日常学习/备考模式一致布局；合并或删除未接入的第二套 Chat UI 与 prompt-hack 页面。
- **验收**：typecheck/build；线性代数和文字型合成课程的浏览器流程完成刷新、选材、引用、错误、stale 和模式切换；生产入口不再读取 legacy Wiki/CourseIndex 作为课程事实。

### V2-F5：deep-dive 多 Agent

- **依赖**：F2、F4。
- **建议范围**：bounded V2 tool DTO、Run Director、Mapper/Tutor/Verifier nodes、phase events、聚焦 tests。
- **交付**：通用 deep-dive workflow 触发 Scout → Mapper → Tutor → Verifier；线性代数跨章节题作为主验收，普通题仍走 quick path。
- **验收**：工具只读 current revision；调用次数/结果大小受限；关系必须有 EvidenceRef；最终仍为 AnswerEnvelope；重复/循环调用不会无限执行。

### V2-F6：对话式备考、`/btw` 与最小学习观察

- **依赖**：F3、F5、current KC/Relation。
- **建议范围**：review schemas/store/service/API、review Agent nodes、Review frontend、`/btw` child turn、tests。
- **交付**：revision-bound plan；teach → attempt → feedback → recap；结构化 question/rubric/grading；return anchor；可追溯 LearnerObservation。
- **验收**：无学习记录不伪造薄弱点；grader error 可见；`/btw` 不推进主线；材料更新使 plan stale；刷新页面能恢复 session/step。

### V2-F7：课程简报、核心 Artifact 与演示打磨

- **依赖**：F4、F5。
- **建议范围**：course brief/artifact schema、生成 service、Studio UI、demo copy 和 tests。
- **交付**：第一份课程简报、至少一种 revision/evidence-bound 学习产物、狐狸小队友好阶段展示。
- **验收**：产物引用可打开；旧 revision 标 stale；模型失败不保留空产物；不读取 legacy Skill 输出。

### V2-F8：legacy 切除、通用性 smoke 与全流程主验收

- **依赖**：F3～F7。
- **建议范围**：删除所有 Course Agent Chat/Review/Studio production consumers 的 legacy Wiki/DMAP/KC/regex citation 路径；新增通用 benchmark harness、线性代数主套件、文字型 smoke、浏览器流程和脱敏报告。
- **交付**：course-agnostic 合成 harness、线性代数 cold-start/可预热 live demo、真实本地材料记录、第二课程 smoke 和成本/时延基线；V2-G 获得可执行输入。
- **验收**：见第 12 节；代码、测试、文档和 commit 一致后才能关闭 V2-F。

## 12. 全流程完成门槛

### 12.1 P0：Course Agent V2 系统必须完成

- [ ] 生产 Course Workspace、Chat、deep-dive、Review 和 Artifact workflow 均使用通用 course/revision 契约，不含学科硬编码。
- [ ] 前端统一 Agent run、AnswerEnvelope、Sources、Knowledge Studio 和 Review Conversation，删除或退役重复 Chat/Prompt-hack 入口。
- [ ] 通过公开 API 创建课程、上传至少三份合成线性代数材料并完成持久任务链。
- [ ] 浏览器可见 Fragment、Outline、Atom、Term、KC、Relation 的真实状态/计数。
- [ ] 课程地图与至少一个 KC 的 `KC → Term → Atom → Evidence` 追踪可操作。
- [ ] quick answer 覆盖 grounded、ambiguous、out-of-scope、unavailable 四种状态。
- [ ] 每个材料 citation 可按 fragment ID 打开正确文件和位置。
- [ ] deep-dive 跑通“线性无关、满秩、可逆”跨章节问题并展示 bounded Agent 阶段。
- [ ] 超级备考跑通 plan、teach、attempt、feedback、recap 与 `/btw` 返回。
- [ ] 材料 revision 更新后，旧回答/产物/计划不会冒充 current。
- [ ] 两门课程和两个会话之间的材料、run、history、review、memory 不泄漏。
- [ ] provider/retrieval/budget/断线错误在前端可见且可重试。
- [ ] 一门小型文字型合成课程完成上传、课程地图、quick answer 和 out-of-scope smoke，证明无公式/KC relation 时仍可工作。

### 12.2 P1：显著增强演示

- [ ] current V2 课程简报作为“第一个惊喜”。
- [ ] 至少一个带 EvidenceRef 的 Studio 学习产物。
- [ ] Grader 产生可追溯的最小 LearnerObservation，并影响本次 session 下一步。
- [ ] Agent phase 卡显示角色、产出数量和耗时，不显示思维链。
- [ ] 合成视觉任务在明确 opt-in 下展示 job/audit/result；未进入证据投影时有清楚提示。

### 12.3 P2：有余力再做

- [ ] 语音输入/朗读。
- [ ] 音频概览或双角色课程播客。
- [ ] 多种 Artifact、完整闪卡系统或长讲义后台生成。
- [ ] 完整 SRS、跨会话长期画像、老师端、硬件端。

P2 未完成不阻塞 V2-F 关闭，也不得为了舞台效果削弱 course/revision/citation/audit 边界。

## 13. 重复验证与验收记录

计划中的新测试文件和脚本在对应任务实现前并不存在；以下是完成时要求形成的命令形状，不是当前完成声明：

```powershell
cd backend
uv run pytest tests/test_agent_runs.py tests/test_chat_answer_v2.py tests/test_chat_api_v2.py
uv run pytest tests/test_deep_dive_agent.py tests/test_review_v2.py
uv run ruff check app tests
uv run pytest
```

```powershell
cd frontend
npm run typecheck
npm run build
```

```powershell
cd backend
uv run python -m scripts.course_agent_benchmark --suite linear-algebra --synthetic
uv run python -m scripts.course_agent_benchmark --suite text-smoke --synthetic
uv run python -m scripts.course_agent_benchmark --suite linear-algebra --real
```

`--real` 必须显式确认外部调用、使用临时或本地演示数据、限制请求数和 token，并输出脱敏记录。最终 postmortem 至少记录：

- source/knowledge revision 与各投影计数；
- 每个 workflow 的 provider/model、请求数、input/output/total token；
- retrieval、首内容和终态的 elapsed；
- p50/p95（样本不足时明确写 insufficient sample）；
- citation 可打开率、跨课程/旧 revision 拒绝结果；
- budget、timeout、provider、断线和重试观察；
- 未通过项及下一条可执行命令。

## 14. 现场演示脚本

建议用一条 6～8 分钟故事线，不用功能菜单巡礼：

1. 打开预热的“线性代数”课程，同时展示 cold-start 构建记录。
2. 展示课程地图和“特征值”的知识追踪链，证明 FoxSay 不是普通 RAG。
3. 问“什么是特征值？”，点击引用回到材料原文。
4. 问“线性无关、满秩和可逆有什么关系？”，展示狐狸小队协作和跨章节证据。
5. 问“光电效应是什么？”，展示透明补充而不是伪造引用。
6. 切换超级备考，Coach 讲解一个目标，Examiner 出题，用户故意漏掉关键条件。
7. Grader 指出缺失条件，Tutor 定向补讲；右侧显示本次可追溯学习观察。
8. 使用 `/btw 为什么特征向量不能是零向量？`，回答后自动回到原题。
9. 结束时展示今天完成的 KC、仍需复习项和所有回答的 EvidenceRef。

对外叙事建议：

> NotebookLM 帮你读资料；FoxSay 把资料构造成一门课，再让一支受证据约束的狐狸小队陪你从“看懂”走到“答对”。

## 15. 明确不做的捷径

- 不直接把现有 8 轮/11 工具 legacy ReAct 换一组工具名后宣称迁移完成。
- 不让模型自由生成 filename、locator、fragment ID 或 CRAG 状态。
- 不用预造 SQLite 数据库、手写 KC/Relation 或静态 JSON 冒充知识构建结果。
- 不把模型生成的概述、讲义、题目或聊天历史写回 V2 事实层。
- 不以材料“难”推断用户“不会”；个人结论必须来自显式行为证据。
- 不用 SSE、动画或 Agent phase 卡代替持久 run/job 状态。
- 不在没有真实标杆课记录时更新比赛文案为“全流程已完成”。
