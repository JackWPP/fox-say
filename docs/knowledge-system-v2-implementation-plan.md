# FoxSay 知识体系 V2：实施蓝图

> 状态：**阶段 A、B、C1、C2、C3、D0 已完成；D0 提供零模型、source-pinned 的 CourseOutline snapshot 与读取边界。`AnswerEnvelope` 仍未接入 chat / Agent / SSE；精确状态以任务台账为准。**
>
> 基准课程：**线性代数**
>
> 关联决策：[ADR-0001](adr/0001-evidence-first-knowledge-v2.md)
>
> 本文不把现有 Wiki / KC / DMAP 管线视为 V2 的事实基础；它们只是在迁移期间可读取的旧投影。

## 1. 要解决的不是“做一个 RAG”，而是“替学生先读懂课程”

用户上传的材料已经会被归一化为 Markdown，并保留图片等资产。V2 要把这些输入变成一个可检索、可解释、可增量维护的课程知识底座，使 Fox 能够：

- 像用 `grep` 一样准确定位课程原文、标题和公式；
- 像语义检索一样理解同义表达、术语别名和跨章节提问；
- 给出的材料性结论都能回到具体文件、页/幻灯片、标题路径和原文片段；
- 材料变化后只重建受影响部分，不把旧知识误装成最新知识；
- 在材料不足时坦白地给出标记清楚的通用补充，而不是伪造引用；
- 让后续 Agent、复习、讲义、闪卡、图谱都消费同一套证据，而非各造一套知识。

“课程骨架”“术语表”“KC”“知识图谱”都很有价值，但它们都不是原始事实。V2 的唯一事实基础是可定位的课程证据。

## 2. 已确定的架构选择

| 决策 | 选择 | 原因 |
| --- | --- | --- |
| 标杆课 | 线性代数 | 公式、定义、定理、例题、先修关系和图示都具备，能验证完整链路。 |
| 文本模型 | DeepSeek | 承担基于已检索文本的抽取、归纳、问答和教学表达。 |
| VLM | `Qwen/Qwen3.6-27B`，SiliconFlow OpenAI 兼容端点 `https://api.siliconflow.cn/v1` | 只负责必要的视觉理解，不能成为所有材料的默认处理步骤。具体可用性须按 HEC-5 留验证记录。 |
| 向量库 | Qdrant | 存放 course-scoped 的 fragment 向量和术语索引，不把它当事实库。 |
| 持久化队列 | SQLite 的 `knowledge_jobs` + 受控 worker（MVP 单 worker） | 先以最小可靠实现保证重启恢复、幂等和可观察性；以后可替换为专用队列。 |
| 旧体系 | 可删除/迁移，不要求版本永久并存 | 新体系形成后，旧的并列事实源不再继续写入。 |

## 3. 事实模型与数据契约

### 3.1 四层数据，而不是四套真相

```text
原始文件 / 图片
        │
        ▼
ParsedDocument（归一化 Markdown、页/幻灯片锚点、资产）
        │
        ▼
SourceFragment ──► 向量 / 全文 / 标题索引
        │                   │
        ├────────► SemanticAtom / VisualAtom
        │                   │
        └────────► Outline / Term / KC / Relation / 摘要 / 骨架 / 图谱
                                            │
                                            ▼
                                      检索与 AnswerEnvelope
```

1. **材料事实层**：原始文件、解析后的 Markdown、图片/表格/公式资产。不可由 LLM 覆盖。
2. **证据层**：`SourceFragment` 是可定位、可索引的原文单元；`EvidenceRef` 是所有下游对象的统一引用。
3. **知识投影层**：`SemanticAtom`、`VisualAtom`、`CourseOutline`、`Term`、`KC` 和关系均由证据派生，可重建、可失效。
4. **体验层**：章节 Wiki、骨架图、复习计划、讲义、聊天回答和 Agent 工具都读取投影与证据，不再反写“知识事实”。

### 3.2 `SourceFragment`：V2 的最小证据单元

每一个 fragment 至少包含：

- `id`：稳定 ID；由 `course_id + material_id + material_revision + ordinal + content_hash` 确定。
- `course_id`、`material_id`、`material_revision`：全程显式，绝不从字符串反推。
- `text`：归一化后的原文；必要时保留公式/表格的原始 Markdown。
- `heading_path`、`page_start/page_end` 或 `slide_start/slide_end`、字符范围。
- `kind`：`paragraph | formula | table | figure_context | visual_derived`。
- `asset_id`（如适用）、`parser_name`、`content_hash`、`created_at`。

fragment 必须按标题、页/幻灯片和语义边界切分。它可以在过长段落处再切分，但绝不把两个无关章节拼成一个 blob；表格和公式不能在中间被截断。初版保持“一条可检索记录对应一条可引用 fragment”，先保证准确和可解释，再考虑独立的 retrieval chunk 层。

### 3.3 `EvidenceRef`：唯一可进入课程结论的引用

材料性对象至少携带：

```json
{
  "course_id": "...",
  "material_id": "...",
  "fragment_id": "...",
  "material_revision": "...",
  "locator": "第 4 章 > 4.2 特征值；p.142",
  "quote": "可选的短原文预览"
}
```

人类可读的 `file_name/locator` 只用于展示，不能替代 `fragment_id`。前端点击引用应当按 fragment ID 打开原文，不再依赖字符串模糊搜索。

### 3.4 最小知识对象，先删去投机字段

- `SemanticAtom`：从证据中提取的概念、定义、公式、条件、定理、步骤、例子或易混点候选。
- `VisualAtom`：从原始图片/图表/公式截图中得到的候选解释，带 `generation_method`、置信度和原资产引用。
- `Term`：课程术语的规范名、别名、类型、简短释义和证据。术语表是检索路由器，不是无来源百科。
- `CourseOutline`：唯一的课程导航投影。初始由 Markdown 标题和页/幻灯片结构确定；只有结构置信不足时才由模型补充候选。
- `KC`：面向学习体验的精简投影，必须引用 Atom/证据。现有未使用的认知维度、学情、复杂图谱字段不进入 V2 首批写路径。
- `Relation`：`prerequisite | depends_on | related`，必须带证据和置信度；没有足够材料依据的关系只作为“建议关联”，不能展示成定论。

## 4. 处理流程：先确定性处理，再把 LLM 用在有价值的位置

### 4.1 每份材料的流程

```text
上传文件
  → 创建 material revision 与持久化 job
  → 解析 / 归一化 Markdown（保留页、标题、资产）
  → 确定性构建 SourceFragment
  → embedding + Qdrant upsert（稳定 fragment ID）
  → [条件满足时] VLM 生成 VisualAtom 候选
  → 标记该材料 revision ready
```

不允许把所有 Markdown 合并后作为一个“未分章”的 chunk。课程级工作读取 material/fragment 列表和显式结构，而不是失去来源的拼接文本。

### 4.2 课程级编译流程

```text
有效 fragments
  → 确定性 Outline（标题树、材料覆盖、页/幻灯片顺序）
  → 低成本术语候选（标题、加粗、公式符号、重复短语）
  → 按 Outline 分组的 SemanticAtom 提取（DeepSeek）
  → 代码验证 EvidenceRef；局部修复无效候选
  → Term 归一化 / 别名消歧（仅对高相似候选调用模型）
  → KC / 关系 / 章节摘要投影
  → 建立检索索引与 KnowledgeStatus 快照
```

模型的输出始终是候选，而不是数据库事实。代码必须校验：

- 输出中的 `fragment_id` 必须来自本次 prompt 允许的 fragment 集合；
- `course_id`、revision、材料归属必须匹配；
- 无效引用会从该对象中移除；若对象因此没有任何有效证据，则不写入课程知识投影；
- 这只使**该候选**失败，不使整门课的生成失败。原文 fragment 检索仍可正常回答问题；
- 需要时对失败候选做一次小范围 repair job，超过上限就显式保留 warning，不进行无限重试。

这样既避免“LLM 自造引用”，也不会因为一条坏引用导致整门课的 Wiki 全部失败。

### 4.3 VLM 的条件调用策略

Qwen VLM 不是默认 OCR，也不是每页 PDF 都要调用。

| 场景 | 是否调用 VLM | 说明 |
| --- | --- | --- |
| 用户直接上传图片 | 是 | 图片本身没有可靠文字层；输出须回链到原图。 |
| PDF/PPT 内的公式、表格、图示 | 条件调用 | 仅当解析器未恢复足够文字/结构，或检测到与课程内容相关的视觉资产。 |
| 已有高质量文本层、纯装饰图片 | 否 | 不付出视觉 token。 |
| 问答检索命中一个尚未理解的视觉资产 | 可按需调用 | 创建可审计的补充 job；结果先是 VisualAtom 候选。 |

视觉结论的回答权重低于直接文字证据。若图像解释没有可靠文本/人工可验证上下文，回答应说明“来自图示解读”，不伪装成教材明确表述。

## 5. 术语表与检索：把“grep”与“语义理解”合在一起

术语表是高价值的中间层，但不应独立生成一堆无来源定义。它承担三件事：

1. **精确入口**：术语名、别名、符号和标题进入全文/标题查找，例如“特征根”“eigenvalue”“λ”。
2. **查询扩展**：查询命中有证据的术语后，只扩展到该术语已经证实的别名和相邻章节。
3. **解释锚点**：回答可先展示“课程中的术语定义”，并继续引用其原文 fragment。

检索顺序如下：

```text
问题
  → 术语 / 标题 / 全文精确召回（像 grep）
  → fragment 向量召回（语义表达）
  → 同一 Outline 邻域补全上下文
  → 去重与重排（证据质量、标题匹配、revision、覆盖度）
  → CRAG 充分性判断
  → AnswerEnvelope（后端组装有效引用）
```

向量检索解决“换一种说法还能找到”；全文和术语检索解决“精确、可解释、可复现”。二者都只返回当前 `course_id`、有效 revision 的 fragments。未来可加入 reranker，但它不是 V2 首批阻塞项。

**C2 当前边界**：先做 `SourceFragment` 的标题/原文精确召回；只有精确结果未同时满足 `grounded` 与请求数量时，才生成 query embedding 并查询 Qdrant。该短路不消耗模型 token，也避免 embedding 与向量查询等待。Qdrant 是候选索引而非事实库，最终 hit 必须回到 current-ready SQLite fragment 重新水合。术语别名路由与完整 Outline 邻域仍属于后续课程编译；C2 的上下文补全仅限同 material/revision/heading path 的 ordinal ±1，且不能抬高 CRAG 档位。

## 6. 问答、引用与 CRAG

模型不负责发明 citation。后端将本轮允许使用的 `EvidenceRef` 传入生成上下文，并从实际采用的 fragment 映射到展示引用。

- `grounded`：材料证据充分，回答正文使用材料结论，带系统组装的引用。
- `ambiguous`：扩大到标题邻域/同义术语后仍只部分覆盖；说明不确定点并列出证据边界。
- `out_of_scope`：材料没有覆盖。可给通用补充，但明确标识 `answer_source: "supplementary"`，不展示伪造的课程引用。

`AnswerEnvelope` 至少保留 `course_id`、`source_revision`、`knowledge_revision`、`confidence_status`、`answer_source`、`citations`、`coverage` 与结构化错误。前端把“材料依据”和“Fox 补充”分段呈现。

**C2 不是问答接入**：当前 `RetrievalOutcome` 与 `AnswerEnvelope` 是纯服务端 DTO/组装函数，不调用 LLM、也不产生 HTTP、SSE、chat、Agent 或前端响应。后续消费者只能从本轮 canonical hits 中提交 opaque `fragment_id`；未知或重复 ID 会丢弃并留下 warning，材料型回答没有有效选择时回退到本轮允许的 canonical evidence。`out_of_scope` 与 `unavailable` 均不得带材料 citation。

`out_of_scope` 是 `retrieval_availability="available"` 的 CRAG 结论：检索已完成而材料没有充分覆盖，可走透明补充。`unavailable` 不是第四个 CRAG 档位，而是未就绪或操作失败：`confidence=null`、带 `error`、无 material hit/citation，必须提示重试或恢复，不能说成课程未覆盖。精确证据存在时的向量故障只作为 warning 保留。

**C3 的已交付前端边界**：课程详情页从 `KnowledgeStatus` API 读取材料证据快照；`SourcesPanel` 展示覆盖度、material/job 错误和“材料证据已就绪，课程地图尚未编译”的真实状态。SSE 只触发刷新提示，处理中的轮询只在任一材料证据仍为 `processing` 时进行。`CitationCard` 只有在收到显式 `EvidenceRef.fragment_id` 的 V2 citation 时才按 current fragment endpoint 打开预览，并校验 course/material/revision/fragment 四元组；404、范围不匹配和瞬态失败不会回退到 legacy locator 预览。现有 chat 不产生该 V2 citation，也不渲染 `AnswerEnvelope` 的 `material`/`supplementary`/`unavailable` 分支；这仍属于 V2-F。

## 7. 增量更新与自然生长

### 7.1 revision 规则

- 每份材料有独立 `material_revision`（内容 hash / 解析版本）。
- 课程当前 `source_revision` 由有效材料 revision 集合确定；添加、替换、删除材料都会产生新的目标 revision。
- `knowledge_revision` 只在一个课程级编译成功后推进，并明确指向它基于的 source revision。
- 当两者不一致，课程状态为 `stale`；已完成材料可以在 `partial` 状态下参与检索，但 UI 和回答必须说明覆盖范围。

### 7.2 最小失效范围

1. 新/变材料只重建该 material 的 parsed document、fragments、视觉候选与向量。
2. 利用 fragment → Outline section → Atom/KC/Term 的依赖记录找出受影响章节。
3. 只重编译这些章节及受影响的跨章节术语/关系；未变化的 fragment ID 和索引保持稳定。
4. 所有写入带目标 revision 条件，旧 job 即使晚完成也不能覆盖新 revision。

“是否全量重建”由系统基于变化覆盖度决定：小范围更新走增量；标题树大幅变化、材料批量替换、或依赖校验无法闭合时，创建显式的 `course_rebuild` job。决定及原因应写入 job detail，用户可以看见。

## 8. 持久化 job 与统一调度

关键工作不再附着在 HTTP 请求或 `asyncio.create_task()` 上。Web 层只写入 job，受控 worker 从数据库领取。

### 8.1 `knowledge_jobs` 的最小契约

- 身份：`job_id`、`idempotency_key`、`job_type`。
- 范围：`course_id`、可空的 `material_id`、`target_source_revision`、`target_knowledge_revision`。
- 状态：`queued | running | succeeded | failed | retry_wait | cancelled`。
- 可靠性：`attempt`、`max_attempts`、`lease_owner`、`lease_expires_at`、`not_before`、可展示的 `error_code/error_message/error_retriable`。
- 成本：`model`、`token_budget`、实际输入/输出 token、耗时。超过课程或 job 预算时暂停并显示原因。

SQLite MVP 采用单受控 worker。它通过原子 claim + 有限 lease 领取任务；进程重启后，过期的 `running` job 可回收。多个进程并行消费在没有数据库/队列升级前不得默认开启。

### 8.2 最先落地的 job 类型

1. `index_material`：解析、fragment、embedding、向量写入的材料级幂等工作。
2. `compile_course`：基于一个明确 source revision 的课程级知识投影工作。
3. `visual_analysis`：按需 VLM 处理指定资产，独立预算、独立可重试。
4. `repair_evidence`：仅修复无效证据候选，不重跑整门课。

SSE 只推“建议刷新”的事件。前端真正显示的进度、失败、可重试按钮和产物数量来自 `KnowledgeStatus`/job 查询 API。

## 9. 成本与等待时间控制

V2 用“分层 + 缓存 + 预算”控制成本，不用牺牲可溯源性来换速度。

| 环节 | 默认策略 | 成本控制 |
| --- | --- | --- |
| 解析、fragment、标题树 | 本地/确定性 | 不调 LLM。 |
| embedding | 批量、仅变更 fragment | 用内容 hash 跳过重复。 |
| 视觉理解 | 条件/按需 Qwen VLM | 图像数和视觉 token 有 job 上限。 |
| 术语候选 | 规则 + 轻量聚合 | 只对疑似同义词做模型消歧。 |
| Atom/KC 抽取 | 按章节批处理 DeepSeek | 输入长度、章节数、重试次数均有预算。 |
| 摘要/骨架 | 从已验证投影生成 | 不再为相同事实反复调用模型。 |
| 问答 | 只携带 top evidence | 限制上下文和输出；引用由代码组装。 |

用户体验分两段：上传完成后立即可看到材料和“正在建立索引”；当基础 fragment 索引 ready 时可以先问原文；课程级知识投影在后台完成后再解锁完整课程地图。这样不会把用户卡在一次冗长的全课程生成上。

首批实现不承诺一个虚假的固定价格。每一轮真实运行记录 token、模型、时长和 job 类型后，再以线性代数的实测分位数配置默认预算和前端预计等待时间。

## 10. 线性代数验收标准

不提交真实用户材料；仓库测试使用合成的线性代数 Markdown/图片 fixture，本地演示可使用用户材料。

### 必须通过的工程验收

- 两门课程存在相同术语时，检索和引用绝不跨 `course_id`。
- 上传“向量空间/线性无关/特征值”材料后，每个返回 citation 都能按 fragment ID 打开正确文件和位置。
- 同一内容重复上传/重试不重复写向量、术语或 KC。
- 修改一个“特征值”片段只使相关材料/章节失效，不重建无关“矩阵运算”片段。
- worker 中断后，lease 过期 job 能恢复；前端重连后由状态 API 得到真实结果。
- 无效 LLM fragment 引用只丢弃对应候选并留下可见 warning，不使整个课程构建伪成功或全量失败。
- VLM 未配置或失败时，受影响视觉任务明确失败/可重试，文本材料仍可用。

### 必须通过的产品验收

- “什么是特征值？”能检索到课程定义并引用正确 fragment。
- “对角化需要什么条件？”能同时给出条件和它们的来源，必要时说明课程材料未充分覆盖的部分。
- “线性无关和满秩有什么关系？”能结合多个 fragments 回答，并显示跨章节来源。
- “光电效应是什么？”走 CRAG 的透明补充分支，明确课程材料没有覆盖。
- 知识状态分别可见：`empty / processing / partial / ready / stale / failed`；不把“材料上传完成”伪装成“课程已经吃透”。

## 11. 实施顺序与提交边界

| 阶段 | 产物 | 完成判据 |
| --- | --- | --- |
| A. 契约与调度地基 | ADR、AGENTS 约束、`knowledge_jobs` schema/store/tests | 可可靠 enqueue、claim、lease 回收、重试和幂等。 |
| B. 可恢复材料索引 | 受控 worker、`index_material` job、fragment 持久化和稳定 Qdrant ID | 重启后材料索引不会丢；不再裸起关键任务。 |
| C. 证据检索与状态 | `EvidenceRef`、fragment preview、KnowledgeStatus、混合检索 | C1～C3 已完成：后端 evidence/status 契约与前端真实状态、fragment-only citation 边界均可验证。chat/Agent 对 V2 evidence 的迁移留待 V2-F；不得把 C2 服务函数视为用户已经可通过聊天得到 V2 答案。 |
| D. 课程知识编译 | Outline、Atom、Term、KC、关系和 revision 依赖 | D0 已完成确定性 Outline、source/knowledge revision、持久 snapshot 和 stale 发布栅栏；Atom、Term、KC、关系与模型审计仍按后续子任务推进。所有投影由证据生成，引用经代码校验。 |
| E. 视觉与成本 | SiliconFlow Qwen VLM 条件 job、使用审计、预算 UX | 必要图像可理解且成本、失败都可见。 |
| F. 迁移与 Agent 消费 | 切换前端/Agent，删除旧并列事实写路径 | 旧 Wiki/DMAP/KC 不再作为独立事实源。 |
| G. 线性代数验收 | 合成测试集 + 本地实材演示记录 | 达成第 10 节的工程和产品验收。 |

每个阶段单独 commit，在 `feature/knowledge-system-v2` 分支完成；阶段完成前不把文档标成“已实现”。架构实际变化时，同一 commit 更新 `docs/architecture.md` 与必要的前端公共类型。

## 12. 明确不在首批实现的范围

- 不引入图数据库、跨课程知识图谱或多用户权限。
- 不把所有图片、所有 PDF 页或所有原文都交给 VLM。
- 不用复杂 ReAct Agent 掩盖基础检索和引用没有跑通的问题。
- 不基于材料猜测学生个人薄弱项；记忆/学习画像是后续 Agent 体系的消费者。
- 不永久保留旧体系的每一个版本；保留必要审计 revision，删除会制造双事实源的旧投影。
