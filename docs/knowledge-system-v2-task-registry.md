# FoxSay 知识体系 V2：任务台账与统一调度约定

> 状态：**Active**
>
> 更新日期：2026-07-11（Asia/Shanghai）
>
> 实施蓝图：[知识体系 V2 实施蓝图](knowledge-system-v2-implementation-plan.md)；架构决策：[ADR-0001](adr/0001-evidence-first-knowledge-v2.md)。

本文件让 V2 的工程工作跨会话、跨 Agent 和跨 commit 可恢复。它记录的是**重构工作**，不是某个用户课程正在执行的后台任务。

## 1. 两条必须分开的持久化链路

| 问题 | 唯一事实源 | 谁写入 | 何时可信 |
| --- | --- | --- | --- |
| “这份线性代数材料现在索引到哪一步、能否重试？” | SQLite `knowledge_jobs`、关联 revision/产物与 `KnowledgeStatus` | HTTP 层 enqueue；受控 worker 领取并更新 | 数据库中的目标 revision 状态与可验证产物一致时。SSE 只提示刷新。 |
| “V2 的哪一项重构正在做、谁可改哪些文件、何时算交付？” | 本台账与对应 commit/测试证据 | 单一实施协调者 | 台账状态、可重复验证和 commit 三者一致时。聊天、子 Agent 口头回报和临时 TODO 不是事实源。 |

因此，不能用“worker 正在跑”代替工程验收，也不能用“Agent 说做完了”把一个课程 job 标为成功。两类状态都必须可恢复、可审计，但存储位置和生命周期不同。

## 2. 统一调度协议

### 2.1 角色与写权限

1. **实施协调者**是台账的唯一状态写入者：负责排序、依赖检查、任务领取、范围隔离、汇总证据及 commit 后的状态迁移。
2. **执行 Agent**在开始前阅读 `AGENTS.md`、ADR、实施蓝图和本台账；它只修改被分配的路径，并向协调者报告精确的文件、测试、风险、未验证项和 commit。
3. **运行时 worker**不是工程 Agent。它只能从 `knowledge_jobs` 原子领取自己能处理的 job，且只能写回相同 `course_id`、revision 和 lease；它不读取或修改本台账。
4. 一个任务如需多人并行，协调者必须拆成互不重叠的子任务和文件范围。共享 schema、公共类型、迁移、`AGENTS.md`、实施蓝图及本台账默认由协调者串行修改。

### 2.2 状态机与完成定义

```text
proposed → ready → active → review → complete
active / review → blocked → active; complete → reopened → active
```

- `proposed`：已发现，尚未定义依赖、范围或验收。
- `ready`：依赖满足，可被领取。
- `active`：已领取并有明确文件范围；不是“已经完成”。
- `review`：实现和最窄验证已完成，等待协调者核对范围、证据和 commit。
- `blocked`：有可复现的外部或契约阻塞；必须记录已经尝试的命令、错误和下一步，不能把可继续推进的问题写成 blocked。
- `complete`：所列验收通过、实际状态/文档一致、相关变更已经 commit。没有 commit 的代码最多为 `review`。
- `reopened`：已完成项被新的可复现回归影响；保留原始完成证据，并建立新的修复范围后回到 `active`。

每次状态迁移都要在第 5 节追加一条记录。完成态不能因为后续发现回归而静默保留；应新建修复任务，并将受影响任务标注 `stale`/`reopened`（在活动记录中说明）。

### 2.3 每次派发的最小包

协调者在派发前必须给出以下内容；缺一项时先补台账，不开始改业务代码。

| 必填项 | 目的 |
| --- | --- |
| `task_id` 与目标 | 让工作可跨会话续接，而不是依赖聊天上下文。 |
| 依赖与当前 revision | 防止旧材料/旧契约覆盖新事实。 |
| 允许修改的文件范围 | 避免并发 Agent 覆盖同一业务文件。 |
| 非目标 | 防止把 Agent、图谱或 UI 重写混进证据底座任务。 |
| 验收和命令 | 把“做了”变成可重复证明。 |
| 成本/时延影响 | 任何模型或重编译任务都必须预先说明预算、缓存和用户可见等待策略。 |

执行完成的回报格式固定为：`task_id`、修改文件、运行命令及结果、未跑项/原因、发现的契约差异、建议 commit。协调者确认后更新本文件，并在 commit 中保留该台账变更或可定位的验证证据。

## 3. V2 当前工作序列

状态反映当前仓库的可验证程度，不把 staged/WIP 误写为已交付。`owner` 是角色而非持久个人名；当前协调者可以在活动记录中写临时领取信息。

| ID | 状态 | 依赖 | 可修改范围 / 交付物 | 完成证据 |
| --- | --- | --- | --- | --- |
| V2-00 | `complete` | ADR-0001 | `AGENTS.md`、本台账、实施蓝图中的命名一致性 | 两条持久化链路和调度规则已写明；链接可读；文档 commit。 |
| V2-A | `reopened` | ADR-0001 | 证据对象、revision 防护、持久 job schema/store 与 lease 基础 | 历史基础见 `262bd37`、`5079c50`、`647670f`、`bf98b74`；V2-A1 正在关闭 logical job identity 的唯一性缺口。 |
| V2-A1 | `active` | V2-A | `knowledge_jobs` 的 material/course logical identity 唯一性、enqueue 防护与迁移安全 | 任一 course/material/revision/job_type 只能有一个 durable job；状态/证据查询不受伪造 idempotency key 影响。 |
| V2-B | `complete` | V2-A | `index_material` 受控 worker、材料上传 enqueue、持久进度与重试入口 | `f794f44`；31 个 V2 窄测试、Ruff 与前端 typecheck 通过。旧 revision 不能写回 fragment、向量或 parser assets。 |
| V2-C | `active` | V2-B | fragment preview、`EvidenceRef`、`KnowledgeStatus`、精确/向量/Outline 邻域检索与前端真实状态 | 两门合成课程不跨 `course_id`；每个 citation 以 fragment ID 打开正确位置；重连后状态来自 API 而非 SSE。由 C1～C3 串行交付。 |
| V2-C1 | `active` | V2-B | 后端 `KnowledgeStatus`、当前 revision fragment preview 和公共证据 DTO；仅修改 schema/store/API/tests | 状态由持久材料/job/fragment 计算；跨课程、旧 revision、未知 fragment 均不能预览；不调用模型。 |
| V2-C2 | `ready` | V2-C1 | fragment-first 混合检索、CRAG 结果与服务器侧 `AnswerEnvelope`；仅修改 retrieval/service/query tests | 只检索当前 course/current revision 的 `source_fragment`；无效 Qdrant payload 丢弃；模型不能伪造 citation。 |
| V2-C3 | `ready` | V2-C1, V2-C2 | 前端 public types、CitationCard、SourcesPanel/Chat 状态呈现 | 引用按 `fragment_id` 打开；`supplementary` 不被展示为拒答；状态重连来自 API。 |
| V2-D | `ready` | V2-C | 课程级 `compile_course`、Outline、SemanticAtom、Term、KC、关系及 revision 依赖 | 模型输出的 fragment ID 均经代码校验；坏引用只丢弃该候选并留下 warning；增量与全量重建决策可审计。 |
| V2-E | `ready` | V2-C | 条件性 `visual_analysis`、SiliconFlow Qwen VLM 验证、使用审计、预算/等待 UX | 按 HEC-5 留下 endpoint/model/错误路径验证记录；无视觉模型时文本链路仍可用；图像数、视觉 token、重试均受 job 预算限制。 |
| V2-F | `ready` | V2-C, V2-D | 前端与后续 Agent 改读 V2 EvidenceRef/revision/AnswerEnvelope，移除旧并列事实写路径 | 旧 Wiki/DMAP/KC 不再被当作独立事实源；Agent 不跨课程或 revision 读取；迁移和删除有回归测试。 |
| V2-G | `ready` | V2-B, V2-C, V2-D, V2-E, V2-F | 合成线性代数验收集、本地实材演示记录与成本/时延基线 | 完成实施蓝图第 10 节全部工程和产品验收；记录 p50/p95 时延、每 job token 与失败/重试结果，不提交真实课程材料。 |

### 3.1 当前契约差异必须显式关闭

现有 SQLite schema 已实现的 job 状态为 `queued | running | succeeded | retryable | failed`，而实施蓝图写的是后续目标状态词汇（含 `retry_wait`、`cancelled`）。在 V2-C 开始暴露公共状态前，协调者必须新建或补充一个有测试的契约对齐任务：要么实现目标状态及迁移，要么修正蓝图和 UI 映射。不得让不同 Agent 依据不同词汇写 API、worker 或前端。

同样，材料索引 job 的唯一当前名称是 `index_material`；不得重新引入 `material_index`。未来的 `visual_analysis`、`repair_evidence`、`course_rebuild` 仅是规划中的 job 类型，在 schema、worker、预算与测试一起落地前，不能被文档表述为现有能力。

当前 job 只持久化预算上限，尚未持久化每次模型调用的 model、输入/输出 token、elapsed、`max_attempts`、`not_before` 或取消原因；这些不是“已经有预算审计”的同义词。V2-C/D/E 在开放相应能力前必须把需要的字段、迁移和 UI 映射一起落地并测试。

`extracted_assets` 仍是 legacy 解析资产表，尚无独立 revision 历史。它在 V2-E 形成 revision-aware `VisualAtom`/资产证据契约前只能作为当前材料的可失效缓存，不能单独进入课程结论、Term、KC 或引用。

### 3.2 活动任务包：V2-C1

- **目标**：公开一个只读、无模型调用的证据状态边界。`KnowledgeStatus` 必须从 SQLite 的当前材料 revision、持久 job 和可验证 fragment 计算，而不是由 SSE 或前端猜测；fragment 预览必须以 `course_id + fragment_id` 解析并拒绝旧 revision。
- **依赖与范围**：依赖 `f794f44` 的 V2-B；允许修改 `backend/app/schemas/`、`backend/app/db/sqlite_store.py`、`backend/app/services/knowledge_status.py`、`backend/app/api/`、对应 backend tests 和实际架构文档。不得改 `agent.py`、legacy retrieval、课程编译、VLM 或前端。
- **验收**：empty/processing/partial/failed 的状态映射有确定性测试；两个课程中相同/伪造 fragment ID 不越界；当前 revision 的 preview 有 material/file/locator，旧 revision 只可在以后显式历史接口开放，当前接口返回 404；HTTP 断线后重新请求仍得出同一状态。
- **成本与时延**：只读 SQLite 查询，不新增模型调用或 embedding；列表/状态接口应是常数次或按材料数线性的小查询，不能扫描原始 Markdown。

### 3.3 活动任务包：V2-A1

- **目标**：补齐持久化队列的逻辑身份约束。`idempotency_key` 之外，还必须唯一约束 material-scoped `(course_id, material_id, job_type, revision)` 和 course-scoped `(course_id, job_type, revision)`；否则同一事实可能有多个相互矛盾的 job。
- **依赖与范围**：允许修改 `backend/app/db/sqlite_store.py`、持久 job schema/store tests 及实际架构文档；不得改变已约定的 job 状态词汇、引入队列服务、删除已有 job 或修改 Agent/前端。
- **验收**：不同 idempotency key 的重复逻辑 job 被明确去重或拒绝；新 SQLite 库有数据库级唯一约束；历史数据库若存在冲突，启动错误必须可见且指出修复方向，不能静默删除任务；C1 的 status/current-evidence 查询不再因重复 row 放大 coverage。
- **成本与时延**：纯 SQLite schema/查询修复，不调用模型；enqueue 只增加索引命中或常数次查找。

## 4. 成本、等待和“自然生长”的调度门槛

1. **先确定性，后模型**：解析、标题树、fragment、内容 hash、失效范围和基础索引先完成；不能为了“看起来聪明”对整门课无差别烧 token。
2. **按影响面决定增量或重建**：由变更材料覆盖率、标题树变化和依赖校验结果决定。满足小变更条件时只派受影响材料/章节；覆盖度过大或依赖无法闭合时，才创建显式的课程重建任务并显示原因。没有实际支持前，不能假装 `course_rebuild` 已可运行。
3. **VLM 是按需证据补全**：`Qwen/Qwen3.6-27B` 通过 SiliconFlow OpenAI-compatible endpoint `https://api.siliconflow.cn/v1` 仅处理解析无法可靠恢复的图片、图表或公式视觉信息。密钥只可由环境变量注入；可用性、请求/错误路径和计费需按 HEC-5 写验证记录。
4. **预算先于派发**：每个模型 job 必须带 `job_id`/请求关联、模型、用途、输入/输出 token、耗时、重试次数和上限。预算耗尽进入可展示的暂停/失败状态，绝不静默生成无证据内容。
5. **等待分层**：基础 fragment 索引 ready 后即可先提供带证据的原文问答；课程级投影在后台继续，UI 显示 `empty / processing / partial / ready / stale / failed`。线性代数首次端到端运行后，以实测 p50/p95 而不是猜测配置默认预算与预计等待时间。

## 5. 追加式活动记录

协调者仅在这里追加状态迁移，保留时间、任务、范围、证据和 commit；不要改写历史来掩盖失败。

| 时间（Asia/Shanghai） | Task | 迁移 | 范围 / 证据 | Commit |
| --- | --- | --- | --- | --- |
| 2026-07-11 | V2-00 | `proposed → active` | 建立工程任务台账，并把运行时 job 与工程任务的事实源分离。 | pending |
| 2026-07-11 | V2-B | `ready → active` | 受控 worker、上传 enqueue、持久进度的实现正在由对应测试验证；完成态等待实际 commit。 | pending |
| 2026-07-11 | V2-B | `active → complete` | `f794f44`；持久 worker、上传 enqueue、revision publication fence、fragment preview/progress 与合成材料测试完成。 | `f794f44` |
| 2026-07-11 | V2-00 | `active → complete` | 统一调度规则、任务台账、实际 job 名称与交接协议已落盘。 | this commit |
| 2026-07-11 | V2-C / V2-C1 | `ready → active` | 领取只读证据状态与当前 revision fragment preview；范围、非目标、验收和成本限制见 §3.2。 | pending |
| 2026-07-11 | V2-A / V2-A1 | `complete → reopened / proposed → active` | C1 审查发现 `idempotency_key` 唯一不足以阻止同一 logical job 重复；按 §3.3 先补数据库级约束。 | pending |

## 6. 交接检查

开始新会话或替换协调者时，按此顺序恢复工作：

1. 阅读 `AGENTS.md`、ADR-0001、实施蓝图、本台账以及 `git status --short`；先区分已提交、staged 和未跟踪内容。
2. 找出所有 `active`/`review` 任务及其依赖和文件范围，不从聊天记录猜测当前阶段；如范围重叠，先由协调者重新拆分或串行化。
3. 对运行时问题查询 `knowledge_jobs`/`KnowledgeStatus` 和目标 revision；对工程问题查询本台账、相关 commit 和测试。
4. 先运行任务列出的最窄检查；若发现差异，追加 `proposed` 修复任务并报告协调者，而不是在别人的范围内顺手重构。
5. 只有在验证、文档和 commit 都到位后，迁移为 `complete` 并派发其依赖任务。
