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
| V2-A | `complete` | ADR-0001 | 证据对象、revision 防护、持久 job schema/store 与 lease 基础 | 历史基础见 `262bd37`、`5079c50`、`647670f`、`bf98b74`；`881b2d4` 补齐 logical job identity 唯一性。 |
| V2-A1 | `complete` | V2-A | `knowledge_jobs` 的 material/course logical identity 唯一性、enqueue 防护与迁移安全 | `881b2d4`；数据库 partial unique indexes、可见历史重复错误和回归测试已覆盖。 |
| V2-B | `complete` | V2-A | `index_material` 受控 worker、材料上传 enqueue、持久进度与重试入口 | `f794f44`；31 个 V2 窄测试、Ruff 与前端 typecheck 通过。旧 revision 不能写回 fragment、向量或 parser assets。 |
| V2-C | `complete` | V2-B | fragment preview、`EvidenceRef`、`KnowledgeStatus`、精确/向量/Outline 邻域检索与前端真实状态 | C1～C3 均已提交；合成课程隔离、current-fragment 边界、浏览器重连事实源和前端证据状态均有可重复验证。chat / Agent 迁移仍为 V2-F。 |
| V2-C1 | `complete` | V2-B | 后端 `KnowledgeStatus`、当前 revision fragment preview 和公共证据 DTO；仅修改 schema/store/API/tests | `881b2d4`；状态由持久材料/job/fragment 计算；跨课程、旧 revision、未知 fragment 均不能预览；不调用模型。 |
| V2-C2 | `complete` | V2-C1 | fragment-first 混合检索、CRAG 结果与服务器侧 `AnswerEnvelope`；仅修改 retrieval/service/query tests，不新增 HTTP/SSE/chat/Agent/frontend 接入 | `0f8d592`、`8060137`、`2209b08`、`056d050`、`02940bd`、`2603bf5`、`0c495f1`、`2b1c319`；canonical rehydrate、availability/error、citation 与成本短路回归通过。 |
| V2-C3 | `complete` | V2-C1, V2-C2 | 前端 V2 public types、可复用的 evidence-aware CitationCard、SourcesPanel 的真实证据状态 | `da2a0b3`、`5355ece`；`npm run typecheck`、`npm run build` 通过。隔离浏览器创建/刷新合成线性代数课程后，`KnowledgeStatus` 以 200 响应驱动“尚无证据”和“课程地图尚未编译”。没有生产 AnswerEnvelope/chat citation，因此 V2 citation 点击仍由 C1/C2 endpoint 测试覆盖。不得把 legacy chat citation/CRAG 映射成 V2。 |
| V2-D | `active` | V2-C | 课程级 `compile_course`、Outline、SemanticAtom、Term、KC、关系及 revision 依赖 | 先由 D0 把 source-pinned、零模型的 CourseOutline snapshot 与状态发布栅栏做成可运行垂直切片；模型 Atom/Term/KC/关系随后拆分，不得跳过身份和审计边界。 |
| V2-D0 | `complete` | V2-C | 将占位 `compile_course` 变成 source-pinned、确定性的 CourseOutline 编译与读取边界；只写 V2 projection tables | `33b3869`；D0 course job target/identity、compiler handler、immutable header/payload、current-outline API 与 `KnowledgeStatus` ready/stale/processing 已验证；56 个 V2 聚焦回归、270 个 backend tests 与相关 Ruff 通过。零 LLM/VLM/embedding 调用。 |
| V2-D0a | `complete` | V2-D0, V2-D1a | 补齐 D0 projection publication 的 lease-expiry/owner 栅栏；只修复已发现的 worker 写入边界 | `3adfbf4`；原子 attempt/owner/expiry/revision publication guard 与失租回归已提交，零模型/向量/网络调用。 |
| V2-D1a | `complete` | V2-D0 | course-scoped DeepSeek text-call audit、course/job budget reservation、retry ceiling 与 audited wrapper；不生成知识投影 | `d1ee488`；持久 audit/reservation、预算可见性、retry ceiling 与 fake-provider 回归已提交。没有调用真实外部模型，也未迁移 material embedding 或 legacy 路径。 |
| V2-D1b0 | `complete` | V2-D0, V2-D1a | 为语义原子抽取预留独立的 course job type 与 SQLite enum 迁移；不 enqueue、不调用模型、不写 Atom | `0304f91`；独立 identity、旧 `CHECK` 表重建迁移和 unsupported-handler boundary 均已提交，零模型/embedding/VLM/网络调用。 |
| V2-D1b1 | `complete` | V2-D0, V2-D0a, V2-D1a, V2-D1b0 | SemanticAtom schema、候选验证与 source/outline/lease-pinned 原子发布；不调用模型、不注册 handler | `75a77c2`；candidate rehydrate、stable ID、audit/source/outline/lease atomic fence 与 current read boundary 已提交，零外部模型调用。 |
| V2-D1c | `review` | V2-D1a, V2-D1b0, V2-D1b1 | audited DeepSeek SemanticAtom handler 与严格 JSON candidate parsing；不自动 enqueue | 已注册 explicit-job handler，fake audited model 端到端覆盖 JSON→candidate→D1b1 publish 和 malformed JSON failure，等待协调者核对并提交。 |
| V2-E | `ready` | V2-C | 条件性 `visual_analysis`、SiliconFlow Qwen VLM 验证、使用审计、预算/等待 UX | 按 HEC-5 留下 endpoint/model/错误路径验证记录；无视觉模型时文本链路仍可用；图像数、视觉 token、重试均受 job 预算限制。 |
| V2-F | `ready` | V2-C, V2-D | 前端与后续 Agent 改读 V2 EvidenceRef/revision/AnswerEnvelope，移除旧并列事实写路径 | 旧 Wiki/DMAP/KC 不再被当作独立事实源；Agent 不跨课程或 revision 读取；迁移和删除有回归测试。 |
| V2-G | `ready` | V2-B, V2-C, V2-D, V2-E, V2-F | 合成线性代数验收集、本地实材演示记录与成本/时延基线 | 完成实施蓝图第 10 节全部工程和产品验收；记录 p50/p95 时延、每 job token 与失败/重试结果，不提交真实课程材料。 |
| V2-M1 | `complete` | — | 隔离修复 legacy raw-text fallback 的 `_text_overlap_score` 未定义 lint 缺陷；仅修改该 helper 与其回归测试 | `5b29a0d`；恢复历史 Jaccard 评分语义；`ruff check app/services/retrieval.py` 通过，未改 V2-C2 行为或 legacy 检索排序策略。 |

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

### 3.4 活动任务包：V2-C2

- **目标**：建立不依赖旧 Wiki/KC/DMAP 的 fragment-first 检索与答案证据契约。精确标题/原文召回与 Qdrant 只产生候选；所有最终 hit 必须由 C1 的 current-ready SQLite boundary 重新水合，`EvidenceRef`、文件名和 locator 一律从该 canonical fragment 组装。
- **依赖与范围**：依赖 `881b2d4`；允许修改 V2 retrieval/answer schema、`backend/app/services/retrieval.py`、`vectorstore.py`、必要的 query tool 与对应 tests。不得接入或重写 `agent.py`、`chat.py`、SSE、聊天持久化、前端、legacy `search_wiki_layer()` 或 legacy term 索引。
- **验收**：exact 命中不依赖 embedding；vector payload 的跨课程、错误 type、历史 revision、错误 material/revision 对、未知 fragment、错误 content hash 都会被丢弃；同文本的不同材料保留为不同证据；CRAG 三阈值、partial coverage、vector 故障可见；`available + out_of_scope` 不带材料 citation。`unavailable` 必须为 `confidence=null + error + 无 material hit`，不能伪装为课程未覆盖；已有 canonical exact evidence 时向量失败必须保留 `available` 与 warning。Qdrant filter 必须按成对 material/revision scope 过滤，不能用两个独立 `MatchAny` 造成交叉泄漏。
- **成本与时延**：检索阶段不调用 DeepSeek/Qwen。先做本地/SQLite 的 exact-first 召回；只有 exact 未同时满足足量 `grounded` evidence 时，才生成 query embedding 并查询 Qdrant。Qdrant 只在已有 embedding 上 over-fetch 候选，候选经 payload 校验和 canonical rehydrate 后才可输出。模型正文生成、SSE 和聊天写库留给后续任务；失败不得被伪装为课程未覆盖。

### 3.5 活动任务包：V2-M1

- **目标**：将 V2-C2 审查发现的 legacy `_text_overlap_score` 缺失从 C2 范围中隔离出来，恢复旧 raw-text fallback 的可运行性，而不借机重写 legacy `search_wiki_layer()`。
- **依赖与范围**：允许修改 `backend/app/services/retrieval.py` 中该私有 helper 及一个最小回归测试文件；必须保持 `6d6ce1a` 之前的 Jaccard 语义（字符集合交集除以并集）。不得修改 V2-C2 的 `retrieve_current_fragments`、schema、CRAG 阈值、Agent/chat、Qdrant schema 或前端。
- **验收**：空输入返回 `0.0`；已知字符集合样例保持 Jaccard 分数；`uv run ruff check app/services/retrieval.py` 不再有 F821；相关 pytest 通过。全量 mypy 的其他既存 legacy baseline 不得被声称为已修复。
- **成本与时延**：纯本地私有函数修复，不调用模型、embedding、Qdrant 或 SQLite。

### 3.6 活动任务包：V2-C3

- **目标**：让已存在的 V2 `KnowledgeStatus` 和 current `SourceFragmentPreview` 成为前端可见、可验证的事实边界；为后续 V2 `AnswerEnvelope` 提供严格的 evidence-aware 引用类型与卡片，而不伪造现有 legacy chat 已完成迁移。
- **依赖与范围**：依赖 C1/C2；允许修改 `frontend/src/types/foxsay.ts`、`frontend/src/shared/types.ts`、`frontend/src/features/course/CitationCard.tsx`、`SourcesPanel.tsx`、必要的 course hook/调用点与相关 CSS。可以新增最小 `useKnowledgeStatus` hook。不得修改 backend API、`agent.py`、`chat.py`、SSE 协议、聊天历史、legacy 引用 DTO 的含义，或以文件名/locator 反推 fragment ID。
- **实现边界**：`GET /courses/{course_id}/knowledge-status` 是状态唯一事实源；进入/重新挂载、材料上传或重试后必须重新读取，处理中可以有限轮询。带 `EvidenceRef.fragment_id` 的 V2 citation 才允许调用 `GET /courses/{course_id}/source-fragments/{fragment_id}`；legacy citation 保持自己的旧预览路径，绝不可被升级为 V2。当前没有 `RetrievalOutcome`/`AnswerEnvelope` HTTP 或 chat/SSE 生产调用点，因此真实回答中的 `supplementary`、`unavailable` 和 V2 citation 渲染留给 V2-F；C3 只能定义契约/可复用渲染边界，不能声称聊天已迁移。
- **验收**：source-ready 但 projection-not-started 显示“材料证据已就绪、课程地图尚未编译”，不显示“课程已吃透”；processing/retryable/failed/missing-evidence 覆盖与错误可见；V2 citation 只按 fragment ID 打开 current preview，404/失败清晰可见；无 fragment ID 的 legacy citation 不调用 V2 endpoint；前端 `npm run typecheck` 与 `npm run build` 通过。测试/人工验证必须记录状态 API 是重连事实源，SSE 最多作为刷新提示。
- **成本与时延**：不调用模型、embedding 或 Qdrant；状态在挂载/材料上传或重试后读取，只有任一 material evidence 仍为 `processing` 时才以有限频率轮询；原文预览仅在用户点击单个 V2 citation 时请求。

### 3.7 活动任务包：V2-D0

- **目标**：把当前仅有 schema/enqueue 占位的 `compile_course` 变成一个可恢复、可验证的零模型垂直切片。它只从 current-ready `SourceFragment` 构建确定性的 `CourseOutline` snapshot，并使 `KnowledgeStatus` 能真实区分 `not_started / processing / ready / stale / failed` 的课程投影；不把 legacy Wiki、DMAP、KC、ChapterWiki 或 CourseIndex 当作输入或输出事实源。
- **依赖与范围**：依赖已完成的 V2-C。允许修改 `backend/app/schemas/knowledge_jobs.py`、新增 V2 projection/source-revision schema、`sqlite_store.py`、`knowledge_jobs.py`、新增 course compiler service、`material_indexer.py`、`knowledge_status.py`、`main.py`、必要的只读 course-outline API 和对应 backend tests，以及实际架构/台账文档。不得修改 legacy pipeline/Wiki 表、`agent.py`、chat/SSE 协议、前端、Qdrant schema、DeepSeek/Qwen 调用或引入图数据库。
- **身份与持久化契约**：course-scoped job 必须显式持久化 `target_source_revision` 与确定性的 `target_knowledge_revision`；逻辑唯一性按 `(course_id, job_type, target_source_revision)`，不得继续把现有整数 `revision` 误当材料集合身份。为兼容队列字段，store 在持久化同一 target 前原子分配 course job 的整数 revision。新增不可变 `course_compilations` header（供 `KnowledgeStatus` 常数次读取）与 `course_projection_snapshots` payload（供 CourseOutline 查询）；二者显式带 `course_id`、source/knowledge revision、compiler version、job ID、计数与时间戳。每个 Outline section 的材料依据必须由 real `EvidenceRef.from_source_fragment()` 组装。
- **执行与发布栅栏**：只有所有当前材料 revision 均为 ready、各自的 `index_material` job succeeded 且 fragment 可验证时，才允许创建/执行 compile job。材料 index handler 可在自己已发布 fragment、但尚未被 worker 标记 succeeded 的短窗口中受控地 enqueue 下一条 course job；compiler handler 在开始和同一 SQLite 发布事务中都重新计算 canonical source manifest。任一不匹配以可见 `stale_course_source_revision` 结束且不得写 snapshot；同 source revision 重试不得重复 snapshot。主 worker 必须注册真实 compile handler，不能再落入 `unsupported_knowledge_job_type`。
- **D0 输出与非目标**：D0 只发布基于 material/heading path/ordinal 的稳定 CourseOutline，并提供只读 current-outline endpoint；无标题材料仍要以材料级 fallback section 可定位。`SemanticAtom`、术语别名/定义、KC、Relation、章节摘要、模型调用审计、VLM 与前端消费留给后续 D1/E/F；不得为了填满课程地图生成无证据概念。
- **验收**：两份合成线性代数材料可得到稳定的 Outline 和可打开的 current `EvidenceRef`；相同 fragment 在两门课中绝不跨 course snapshot；未完全 ready 的 source 不创建/不运行 compilation；入队后或发布前材料 revision 改变时 job 可见 stale failure 且无 snapshot；同 source 重试不重复写；current source 与 succeeded header 相等才 `projection_status=ready`，不等时 `stale`，current target queued/running 时 `processing`。course-outline endpoint 拒绝 old/stale/跨课程 snapshot。D0 compiler tests 不调用 LLM/VLM/embedding。
- **成本与时延**：只读 SQLite fragments + 确定性分组 + SQLite payload/header 写入；不调用模型、embedding、Qdrant 或网络服务。每次编译对当前 fragment 数线性，header/status 查询不得读取 outline JSON 或原始 Markdown；source-ready 后由持久 job 异步完成，UI 可先继续使用 fragment 问答。

### 3.8 活动任务包：V2-D1a

- **目标**：在任何 D1 语义抽取前建立模型调用的可恢复审计和双层硬预算门。新的 `model_call_audits` 记录必须把 `call_id`、`course_id`、`job_id`、job attempt、target source/knowledge revision、`call_kind`、purpose、provider/model、无原文的 request fingerprint、输入 token 上界、输出 token 上限、reservation、provider reported usage、reasoning usage、elapsed、状态、错误及时间戳显式持久化；`course_model_budgets` 按 `(course_id, source_revision)` 持久化课程上限和已占用/结算额度。二者是调用审计，不替代 `knowledge_jobs` 的课程工作流状态。
- **依赖与范围**：依赖 D0；允许修改 V2 course job/schema/store、配置、增加 audited DeepSeek text-model service、`KnowledgeStatus` 与其前端公开类型/展示、对应 backend/frontend tests 和实际架构/台账文档。允许复用已声明的 OpenAI-compatible client，但不得改 material `embedding.py`、legacy Wiki/quiz/review/terminology 调用、`agent.py`、chat/SSE、Qdrant 或 VLM。material embedding 的独立预算审计另列后续任务，不能被此处默认视为已解决。不得在本任务调用真实 DeepSeek、SiliconFlow 或任何外部模型。
- **预算与错误契约**：reservation 必须在 SQLite `BEGIN IMMEDIATE` 中同时检查同一 `(course_id, source_revision)` 的 course budget 与 job budget；请求只允许由 audited wrapper 发出，并以保守、可解释的输入 token 上界加显式 `max_output_tokens` 保留额度。SDK 必须显式 `max_retries=0`，避免未审计的内部重试。额度不足时持久化 `rejected/token_budget_exhausted`，在网络调用前返回稳定错误；客户端/超时/429/5xx/invalid response/usage 缺失分别持久化可见状态，不能吞掉。reported usage 可为空但须标为 `unavailable`，绝不能伪造为零；失败且账单未知时 reservation 不得静默释放。job 增加显式 `max_attempts`，重试超过上限必须停止。
- **非目标**：本任务不生成 `SemanticAtom`、Term、KC 或 Relation，不修改 D0 的 current compiler identity，不把 token 估算冒充账单，也不声称已有全局/用户级成本统计。后续 D1b 应使用新的 course-scoped extraction job type，而不是重用已成功的 D0 job；模型 audit 表的 status 仅辅助课程 job 失败诊断，真正 compile/extraction job 的 `retryable/failed` 仍由 worker 统一写回。
- **验收**：合成 running compile/index job 能 reserve→success，记录 course/revision/purpose/model、request fingerprint、reported input/output/reasoning/total tokens 和 elapsed；并发/重复 reservation 不能超过 course 或 job cap，拒绝时 fake provider 未被调用；客户端异常、timeout、429、invalid response、usage 缺失均有确定 audit status/error，且不会泄漏跨 course/job record；`KnowledgeStatus`/SourcesPanel 可见当前 projection 的预算或模型错误；旧 SQLite 数据库会迁移且不丢 queue/projection 数据。全部测试使用 fake client，网络调用计数为零。
- **成本与时延**：SQLite reservation/finish 为常数次读写；没有 D1b handler 前不触发网络。生产调用时单次请求的输入上界与输出上限之和先占用 course 与 job budget，预算耗尽立即返回，不排队无限重试。

### 3.9 就绪任务包：V2-D0a

- **目标**：修复 D0 审查发现的 projection 发布 lease 栅栏缺口。`publish_course_compilation_if_current` 必须以被领取 job 的 `attempt + lease_owner + 未过期 lease + source/knowledge revision` 作为原子发布前提；失租或被回收的旧 worker 只能退出，不能写入任何 `course_compilations` 或 snapshot。
- **依赖与范围**：依赖已完成的 D0、D1a（只复用其 current-lease 查询）；允许修改 `course_compiler.py`、对应 SQLite publication guard、D0 worker/compiler tests 及架构/台账文档。不得改 projection identity、引入模型、重写 queue 状态词汇或触碰 D1a audit 表。
- **验收**：合成过期 lease、owner 不匹配和 attempt 已被回收的 compiler 均返回可见 lease-lost/stale 结果且数据库无 header/payload；正常 worker 保持 D0 的 source fence/outline 回归。单 worker SQLite 行为不变。
- **成本与时延**：只有已有 SQLite transaction 中的常数次 job-row 校验；零模型、零向量、零网络调用。

### 3.10 活动任务包：V2-D1b0

- **目标**：在写入任何 `SemanticAtom` 或调用 DeepSeek 前，为它建立独立的 `extract_semantic_atoms` course job type。不能复用 D0 已成功的 `compile_course` job，也不能用文件名或当前内存状态推导它的 source/knowledge target。
- **依赖与范围**：依赖 D0、D1a；允许修改 V2 job schema、SQLite `_SCHEMA`/安全枚举迁移、job store/enqueue contract、相关 tests 与实际架构/台账文档。不得注册 worker handler、自动 enqueue、调用 audited model、写 Atom/Term/KC/Relation、修改 D0 compilation identity、legacy pipeline 或前端。
- **迁移与身份契约**：新 job 是 `scope=course`，显式带 target source/knowledge revision；逻辑 identity 仍为 `(course_id, job_type, target_source_revision)`，因此它与同一 source 的 D0 job 不冲突。SQLite 既存 `knowledge_jobs` 若 job-type `CHECK` 不允许该值，必须以可重复的表重建迁移扩展约束，完整保留 job rows、course compilation、model audit 和 partial identity indexes；迁移后运行 `foreign_key_check`，不能静默删除或重写历史任务。
- **验收**：fresh DB 的 schema/type 都接受新 job；含 D0 header 和 D1a audit 的合成旧 DB 重开后保留数据并可 enqueue 新 job；相同 course/source 的 D0 和 semantic job 各自只一条、跨 course 隔离；D1b0 不会被 material indexer 自动入队，worker 未注册 handler 时的失败仍可见；零模型/embedding/VLM/网络调用。
- **成本与时延**：一次性本地 SQLite migration；运行时仅复用现有 identity-index 查询。没有 handler，不产生 token、Qdrant 或用户等待。

### 3.11 活动任务包：V2-D1b1

- **目标**：建立可重建的 `SemanticAtom` projection，但不调用模型。候选含 type、短 statement、section ID 与 fragment IDs；服务端只从 current-ready `SourceFragment` 重新组装 `EvidenceRef`，并验证它们都属于当前 D0 `CourseOutline` 的同一 section。候选不合格时计入 warning/rejected count，绝不能入库为无来源 Atom。
- **依赖与范围**：依赖 D0/D0a/D1a/D1b0；允许新增 V2 atom/compilation schema、SQLite tables/store/service、当前 atoms 只读 API（如需要）、相关 tests 与实际架构/台账文档。不得注册 extractor worker、调用 DeepSeek/Qwen/embedding、自动 enqueue、写 Term/KC/Relation、读取 legacy Wiki/DMAP/KC 或改变 D0 outline 格式。
- **身份与发布契约**：`semantic_atom_compilations` 和 `semantic_atoms` 均显式带 course/source/knowledge revision、job ID 与 model call ID（候选的调用关联只可为审计中相同 course/job/revision 的成功 call）。Atom ID 由 course/source/knowledge/section/type/statement/排序后的 canonical fragment IDs 稳定哈希生成。SQLite 发布在一个事务内重新校验 job attempt/lease、当前 source manifest、成功 D0 header/outline、canonical fragment 与 model-call audit；任何一项不匹配则零写入。
- **验收**：合成线性代数 current outline + fake audit 可发布稳定 Atom 和真实 EvidenceRef；跨课程/旧 revision/非本 section/未知 fragment/错误 audit call 的候选被拒绝；stale source、失租或 job 回收时 header/Atom 均不写；同 target retry 幂等且不重复；零外部模型调用。
- **成本与时延**：本地 SQLite + Pydantic 校验，按候选和引用数线性；没有 worker handler，不产生 token、embedding、Qdrant 或用户等待。

### 3.12 活动任务包：V2-D1c

- **目标**：注册 `extract_semantic_atoms` 的受控 handler。它只在已被显式 enqueue 且 worker 已领取的 course job 内，通过 `AuditedDeepSeekTextModel` 发起调用；禁止从材料上传、D0 完成或 HTTP 请求中自动 enqueue。模型只可返回带 D0 section ID 与允许 fragment ID 的 JSON candidates，候选随后必须经 D1b1 rehydrate/publish。
- **依赖与范围**：依赖 D1a/D1b0/D1b1；允许新增 semantic extractor service、`main.py` handler 注册、必要配置、对应 tests 与实际架构/台账文档。不得改 legacy OpenAI 调用、Agent/chat/SSE、自动调度、VLM、embedding、Term/KC/Relation 或前端成本页；不得使用真实外部模型测试。
- **调用与失败契约**：prompt 仅含当前 outline section ID、其 allowed fragment ID 和文字；JSON root/schema 错误是可见、有限可重试的 `semantic_atom_output_invalid`，无有效 candidate 可作为零 Atom 的已完成 projection 但记录 rejected count。预算拒绝、timeout/429/5xx、lease lost 和 stale target 保留 D1a 的 code/retry 语义；D1b1 publish false 时不得把 job 标为成功。
- **验收**：fake audited model 的结构化输出生成可读取 Atom，并验证 prompt 不含跨 section fragment；malformed JSON、未知 section/fragment、budget rejection、lease loss/stale 都无 Atom/header 发布且 worker 状态可见；默认 upload/index/D0 路径不创建 semantic job，所有测试零网络。
- **成本与时延**：一个显式 semantic job 目前使用一个受 budget 上限保护的 course-level text call；超过预算不会出网。后续按 section 分批与自动调度必须以实测线性代数 token/时延为准，另立任务。

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
| 2026-07-11 | V2-A / V2-A1 | `reopened / active → complete` | `881b2d4`；partial unique indexes、可见迁移错误与 enqueue 回归覆盖完成。 | `881b2d4` |
| 2026-07-11 | V2-C1 | `active → complete` | `881b2d4`；当前证据状态、current-ready source preview、legacy/hash/revision/course isolation 测试完成。 | `881b2d4` |
| 2026-07-11 | V2-C2 | `ready → active` | 领取纯 fragment-first 检索与 AnswerEnvelope 契约；范围、非目标、验收和成本限制见 §3.4。 | pending |
| 2026-07-11 | V2-M1 | `proposed → ready` | C2 审查发现 `retrieval.py` 的 legacy raw-text fallback 在 C2 之前已有未定义 helper；单列最小修复，避免与证据检索契约混入同一提交。 | this commit |
| 2026-07-11 | V2-C2 | `active → review` | `0f8d592`、`8060137`、`2209b08`、`056d050`、`02940bd`、`2603bf5`、`0c495f1` 已实现 pair-scoped vector filter、canonical rehydrate、AnswerEnvelope、availability/error、exact-first 与 C1 citation endpoint 组合回归；等待文档和最终核验。 | `0c495f1` |
| 2026-07-11 | V2-M1 | `ready → active` | 按 §3.5 领取历史 `_text_overlap_score` 复原，文件范围与 C2 隔离。 | `c6e0880` |
| 2026-07-11 | V2-M1 | `active → complete` | `5b29a0d`；4 个 Jaccard/空输入回归通过，`ruff check app/services/retrieval.py tests/test_legacy_raw_text_retrieval.py` 通过。全量 mypy 既存 strict baseline 未在此任务修复。 | `5b29a0d` |
| 2026-07-11 | V2-C2 | `review → complete` | 50 个 C1/C2/M1 聚焦回归通过，相关 Ruff 通过，完整 backend pytest 已完成；定向 mypy 的新增 C2 行已清零。剩余 mypy 仅为 legacy/imported baseline，未宣称已修复。纯 service/schema/test，未接 chat/Agent/frontend。 | `2b1c319` |
| 2026-07-11 | V2-C3 | `ready → active` | 根据 C1/C2 API 审查领取前端真实证据状态和 evidence-aware citation 边界；范围、非目标、验收和成本限制见 §3.6。 | this commit |
| 2026-07-11 | V2-C3 | `active → review` | `da2a0b3`、`5355ece` 已完成 types/API、真实状态与 current-fragment citation 边界；对抗审查通过，`npm run typecheck`、`npm run build` 均通过。 | `5355ece` |
| 2026-07-11 | V2-C3 | `review → complete` | 临时 SQLite/Qdrant/uploads 的隔离浏览器验收：创建并直接刷新合成线性代数课程，SourcesPanel 显示 `尚无证据`、`已就绪 0/0`、`0 个片段` 和 `课程地图尚未编译`；`/api/courses/{course_id}/knowledge-status` 的四次请求均为 200，浏览器无错误。生产 chat 尚不产生 V2 citation，故该点击路径不伪称已人工验收。 | this commit |
| 2026-07-11 | V2-C | `active → complete` | C1～C3 的实现、定向测试、前端构建和隔离浏览器验收均完成；后续课程投影从 V2-D 开始。 | this commit |
| 2026-07-11 | V2-D / V2-D0 | `ready → active` | 领取 zero-model course compilation snapshot；范围、source identity、发布栅栏、非目标、验收和成本上限见 §3.7。当前 `compile_course` 尚无 handler，不能宣称已可运行。 | pending |
| 2026-07-11 | V2-D0 | `active → review` | `compile_course` 现在以 explicit source/knowledge target 入队，实际 worker handler 生成 deterministic CourseOutline；状态、API、stale fence、automatic enqueue 和跨课程隔离由合成线性代数回归覆盖。 | `33b3869` |
| 2026-07-11 | V2-D0 | `review → complete` | 56 个 D0/C1/C2 聚焦 backend tests、270 个完整 backend pytest 和相关 Ruff 通过；targeted mypy 没有 D0 新增错误，剩余 12 项为 `foxsay.py`、legacy `sqlite_store.py`、worker 的既有 strict baseline。未调用 DeepSeek、Qwen、embedding 或 Qdrant。 | this commit |
| 2026-07-11 | V2-D1a | `ready → active` | 领取持久 model-call audit 与 budget reservation；范围、非目标、验收和成本门见 §3.8。D1a 不得发起真实外部模型调用或写入语义知识投影。 | pending |
| 2026-07-11 | V2-D1a | `active → review` | `model_call_audits`/course-budget reservation、retry ceiling、audited DeepSeek wrapper 与 SourcesPanel 预算可见性已实现；fake-provider 覆盖成功、并发拒绝、timeout/429/5xx/4xx、invalid response、usage 缺失、失租、旧库迁移与 SDK retries=0。等待最终 diff/commit 核对。 | pending |
| 2026-07-11 | V2-D1a | `review → complete` | `d1ee488`；44 个 V2-D0/D1a 聚焦 backend tests、284 个 backend tests、相关 Ruff、前端 `typecheck`/`build` 通过。mypy 定向检查仅剩 `foxsay.py` 与 legacy `sqlite_store.py` 的 9 个既有 strict baseline；D1a 新文件/行无新增报错。Vite 仍报告既有 KaTeX font 和 chunk-size warning。 | `d1ee488` |
| 2026-07-11 | V2-D0a | `proposed → ready` | D1a lease 审查发现已提交 D0 的 publication guard 尚未验证 lease owner/expiry；按 §3.9 单列最小修复，避免和模型审计实现混写。 | pending |
| 2026-07-11 | V2-D0a | `ready → active` | 领取 publication lease/attempt fence；文件范围、非目标、验收和零成本限制见 §3.9。 | pending |
| 2026-07-11 | V2-D0a | `active → review` | `publish_course_compilation_if_current` 现在校验 attempt、lease owner、未过期 lease 与 revision；失租/owner 不匹配/attempt 被回收均无 snapshot 写入。34 个 D0/D1a 聚焦回归和相关 Ruff 通过。 | pending |
| 2026-07-11 | V2-D0a | `review → complete` | `3adfbf4`；26 个 compiler/worker/status/indexer 聚焦回归与相关 Ruff 通过。定向 mypy 仅为既有 `foxsay.py`、legacy `sqlite_store.py`、worker strict baseline，无本任务新增项。 | `3adfbf4` |
| 2026-07-11 | V2-D1b0 | `ready → active` | 领取 semantic-atom 独立 job type 与旧 SQLite enum migration；范围、非目标、验收与零成本限制见 §3.10。 | pending |
| 2026-07-11 | V2-D1b0 | `active → review` | schema/store 已接受独立 `extract_semantic_atoms`；D0/D1a facts 的合成旧 SQLite migration、course/source identity、未注册 handler 的可见失败均已回归覆盖。等待最终 diff/commit 核对。 | pending |
| 2026-07-11 | V2-D1b0 | `review → complete` | `0304f91`；38 个 job/worker/indexer/compiler/status 聚焦回归与相关 Ruff 通过。定向 mypy 仅为既有 `foxsay.py`、legacy `sqlite_store.py` strict baseline，无本任务新增项。 | `0304f91` |
| 2026-07-11 | V2-D1b1 | `ready → active` | 领取 SemanticAtom schema、candidate validation 与 revision/lease-pinned publication；范围、非目标、验收和零成本限制见 §3.11。 | pending |
| 2026-07-11 | V2-D1b1 | `active → review` | semantic atom candidate 只能由 current D0 outline section + canonical fragment 重水合；发布重复验证 succeeded audit、source target、attempt/owner/lease。合成线性代数成功、invalid candidate、stale、失租、错误 audit 和幂等回归已通过，等待最终 diff/commit 核对。 | pending |
| 2026-07-11 | V2-D1b1 | `review → complete` | `75a77c2`；44 个 D0/D1a/D1b1 聚焦 backend tests、相关 Ruff 通过；新 schema/compiler 定向 mypy 无错误。全量 pytest 曾出现一次非确定失败，立即 `-xvv` 重跑未复现且未归因于 D1b1；因此此项不声称全量套件绿，后续 G 基线需复跑并隔离。 | `75a77c2` |
| 2026-07-11 | V2-D1c | `ready → active` | 领取 audited semantic handler、strict JSON parsing 与 worker integration；范围、非目标、验收和成本限制见 §3.12。 | pending |
| 2026-07-11 | V2-D1c | `active → review` | explicit `extract_semantic_atoms` job 通过 audited wrapper 返回 JSON candidate，再经 D1b1 publish；fake model 成功/非 JSON failure 与无自动 enqueue 回归通过。等待最终 diff/commit 核对。 | pending |

## 6. 交接检查

开始新会话或替换协调者时，按此顺序恢复工作：

1. 阅读 `AGENTS.md`、ADR-0001、实施蓝图、本台账以及 `git status --short`；先区分已提交、staged 和未跟踪内容。
2. 找出所有 `active`/`review` 任务及其依赖和文件范围，不从聊天记录猜测当前阶段；如范围重叠，先由协调者重新拆分或串行化。
3. 对运行时问题查询 `knowledge_jobs`/`KnowledgeStatus` 和目标 revision；对工程问题查询本台账、相关 commit 和测试。
4. 先运行任务列出的最窄检查；若发现差异，追加 `proposed` 修复任务并报告协调者，而不是在别人的范围内顺手重构。
5. 只有在验证、文档和 commit 都到位后，迁移为 `complete` 并派发其依赖任务。
