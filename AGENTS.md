# FoxSay Agent Operating Contract

本文件是 FoxSay 项目的最高优先级工程约束。后续任何 Agent、脚手架生成、功能实现、重构、测试和文档编写都应先遵守本文件,再参考 `docs/refactor-plan-2026-06.md`。

## Product Boundary

FoxSay 是以"课程"为原子单位的 AI 学习 Copilot。课程是核心组织单元,所有数据和交互都围绕课程展开。

- **课程隔离**:每门课程的材料、向量检索、骨架图、对话历史、复习计划都必须显式绑定 `course_id`,确保数据不会跨课程泄漏。
- **材料优先**:AI 回答应优先基于当前课程已上传的材料,确保内容与课程高度相关。
- **来源引用**:基于课程材料的回答应包含来源引用,格式需能定位到具体材料和章节/片段,例如 `来自 [文件名] · 第X部分`。
- **透明补充**:当课程材料不足以回答时,AI 可以用通用知识补充,但必须明确标注哪些内容来自课程材料、哪些是补充说明,让学生能区分信息来源。
- **诚实边界**:如果 AI 不确定答案的准确性,应主动说明置信度,而不是给出可能误导的确定性回答。

## MVP Scope

MVP 聚焦以下六个核心功能:

- **课程表导入**:从 CSV/Excel 课程表建立书架和考试倒计时。
- **手动创建课程**:作为课程表导入失败或缺失时的兜底。
- **材料上传与处理**:PDF、PPT、图片、文本备注进入课程材料库。
- **课程骨架图**:材料首次处理完成后生成章节、核心概念、难点和先修链路。
- **课程内问答**:使用 CRAG 边界控制,回答带来源引用。
- **超级备考模式**:生成复习计划,支持陪伴复习和 `/btw` 插话。

新增功能应有具体的用户需求支撑,优先服务于上述核心功能的完善和体验提升,避免投机性开发分散精力。

## Technical Constraints

- Frontend: Vite + React + TypeScript + Tailwind.
- Backend: FastAPI + Python,由 `uv` 和 `pyproject.toml` 管理。
- Vector store: Qdrant,可通过 Docker Compose 或独立容器运行。
- Knowledge graph: MVP 阶段暂不引入,骨架从材料直接生成。
- RAG direction: 单层 RAG + CRAG 门控。
- Boundary control: CRAG 置信度门控 + system prompt 引导。
- LLM: DeepSeek OpenAI-compatible API。当前已知可用:`deepseek-v4-flash` / `deepseek-v4-pro`(2026 V4),以及到 2026/07/24 之前兼容的 `deepseek-chat` / `deepseek-reasoner`。引入新的模型或外部服务前需验证可用性(见 HEC-5)。
- Deployment baseline: Docker Compose.

## CRAG Policy

CRAG(Confidence-based Retrieval-Augmented Generation)是 FoxSay 的边界控制机制,根据检索结果的置信度决定回答策略:

- **`score >= 0.72`(grounded)**:材料充分,正常回答并附来源引用。
- **`0.55 <= score < 0.72`(ambiguous)**:材料部分相关,扩大检索范围后谨慎回答,标注置信度状态。
- **`score < 0.55`(out_of_scope)**:课程材料中没有相关内容。AI 可以基于通用知识回答,但必须明确声明"课程材料中未覆盖此内容,以下为通用理解,建议对照教材确认",并在响应中标注 `answer_source: "supplementary"`。

后端响应须保留 `confidence_status` 和 `answer_source` 等元数据,供审计和前端展示使用。

## 知识体系 V2 与持久化任务调度

知识体系以可追溯的课程材料证据为先,异步处理必须是可恢复的持久工作流,不能依赖单个 Web 请求或进程内内存。

- **证据优先**:材料解析、标准化、切块、向量化、课程结构、KC 与关系的每一层都必须显式关联 `course_id` 和来源材料。基于材料的 KC、关系、回答与引用应能回溯到具体 `material_id`、`chunk_id`/片段、标题路径及页码或幻灯片位置；骨架图、ChapterWiki、CourseIndex、知识图谱均是可重建的派生产物,不得成为相互矛盾的事实源。
- **显式版本**:会影响知识产物的材料或课程处理输入必须有显式 `revision` / 内容 hash。不得通过文件名、章节字符串或当前内存状态反推版本；旧 revision 的任务和产物不得覆盖新 revision。
- **关键任务必须持久化**:解析、切块、embedding、向量写入、知识提取、结构/投影重建等关键异步任务必须持久化 `job_id`、`course_id`、`material_id`(如适用)、`revision`、步骤、状态、尝试次数、时间戳和可展示的 `error`。进程或容器重启后,系统必须能够领取、恢复、重试或明确标记这些任务,不能把它们遗忘为 `processing`。
- **SSE 不是事实源**:SSE 只用于通知 UI。任务真实状态、错误、产物计数和可恢复性必须从持久化存储读取；断线、重连或漏事件不得改变任务事实。
- **禁止裸后台关键任务**:不得以裸 `asyncio.create_task()` 承载会改变课程知识状态的关键工作。Web 层只能创建持久任务；受控 worker 再从持久队列领取并执行。仅限不影响事实状态的瞬时 UI 通知可使用进程内 fire-and-forget。
- **领取与 lease**:worker 领取任务时必须有原子状态迁移和有限期 lease/心跳；lease 过期的 running 任务必须可被安全回收。MVP 若使用 SQLite,应明确单 worker/并发边界,避免多进程重复消费。
- **幂等与重试**:每一步必须以 `course_id + material_id + revision + step` 或等价稳定键幂等执行。向量与派生产物写入应使用稳定标识或受控替换；失败重试不得重复累计知识点、关系或费用。不可恢复错误必须暴露给用户并提供受控重试入口。
- **预算可审计**:所有模型调用应记录任务/请求关联、模型、用途、输入输出 token、耗时、重试次数和预算消耗。课程级、任务级和单次问答的预算上限必须可配置；达到上限时暂停并显式报告,不得静默降级为无证据知识。
- **Agent 与 worker 共用边界**:Agent 只能读取与当前 `course_id` 和有效 revision 匹配的已完成证据；worker 只能为领取到的课程任务写入对应 revision。二者不得跨课程复用缓存、向量、KC、关系或任务状态。
- **失败与完成定义**:材料或课程只有在对应 revision 的必要步骤完成且产物可验证时才能标记 ready。LLM、embedding、向量库或解析失败不得伪造成功；回答若无足够课程证据,必须走 CRAG 的透明补充路径并保留审计元数据。

## Hard Engineering Constraints

本节约束是代码合入 main 分支的基本要求。

### HEC-1. 错误必须可见

错误不应被静默吞掉,调用方需要知道发生了什么。

- 避免 `try/except Exception: return ""` 这种隐藏错误的模式。
- LLM 调用失败时,抛异常或返回带 error 字段的结构,让调用方能感知并处理。
- 后端的错误路径通过 SSE / HTTP 状态码 / 日志可追溯。
- 测试时验证"错误情况下,前端能看见错误"。

### HEC-2. 改动需要 commit

重要改动应 commit 后再标记为完成,确保工作不会因意外丢失。

- 功能/重构/修复的完成代码需要 commit。
- 探索性/原型工作可以留在 working tree,但应明确标注为 WIP。
- WIP 代码建议放在 feature 分支,避免污染 main 的历史。
- spec 文档标记"已完成"时,对应的代码应已 commit 或可运行。

### HEC-3. checklist 对应真实验证

文档中声称完成的事项需要有对应的验证手段。

- 勾掉的 checklist 项应有对应的测试或可观察的产出(文件存在、命令可运行、API 返回正确)。
- 验证手段缺失时,保持 `[ ]` 或标注 `Not-tested: <原因>`。
- 小型重构和纯文档改动不要求新测试,但应确认现有测试仍通过。

### HEC-4. 避免过度工程

保持简洁,只引入当前需要的东西。

- 新增依赖、文件、表、工具应有具体的实现需求。
- 引入新抽象前确认它在当前阶段有多个具体调用点。
- 优先删除和复用,而不是新增抽象层。

### HEC-5. 不杜撰外部依赖

模型名、API endpoint、配置 key 等必须是真实存在且能跑通的。

- 常见成熟库(如标准 FastAPI 生态的包)能 import 并跑通即可。
- 新颖或不熟悉的工具、模型、API 需要在 `docs/postmortem/` 写验证记录。
- 不确定的推测标注 `[未验证]`。

### HEC-6. schema 显式声明

数据模型的字段应显式声明,避免隐式耦合。

- 需要 `course_id` / `chapter_id` 的对象,字段显式声明。
- 避免 `chapter_id.split("_")[0]` 这类反推主键的写法。
- 避免在一个模型的字段里藏另一个模型的主键。

### HEC-7. 依赖声明与使用一致

`pyproject.toml` 中的依赖和代码中的 import 应保持同步。

- 声明的依赖应在代码中有至少一处 import。
- 代码中 import 但 pyproject 未声明的,应及时补充。
- 零 import 的依赖应在合理周期内清理,不阻塞其他工作。

### HEC-8. 文档与代码对齐

文档应反映实际情况,让新人(包括 AI agent)能直接上手。

- `docs/architecture.md` 反映实际代码架构。架构变更后同步更新。
- 过时文档在顶部标注 `已过时` + 日期 + 原因。
- HANDOFF.md 的架构描述与 architecture.md 保持一致。

## Security And Data Rules

- 不硬编码 API key、DeepSeek 凭证、用户材料或真实课程数据。
- 模型、向量库、运行时配置通过环境变量注入。
- 不提交 `.env`、本地上传、生成的 embeddings、向量库卷或私有课程材料。
- 示例和 fixture 使用合成数据。

## Engineering Discipline

- 保持 diff 小而可审查,改动可逆。
- 优先删除和复用,而不是新增抽象层。
- 新增依赖应有具体实现需求。
- 前后端 public types 在新增行为前保持对齐。
- 新增 course-scoped 功能时,request/response schema 和测试中包含 `course_id`。
- 行为变更应有测试或 `Not-tested` 说明。
- 代码改动后,先跑最窄的相关检查,再跑更广泛的 lint/type/test。
- 架构变更在同一 commit 中更新 `docs/architecture.md`。

## Design Direction

- Product voice: smart, mischievous fox; helpful but not generic.
- Visual direction: fox amber orange, midnight charcoal, warm white.
- Interaction principles: zero-friction capture, async processing, proactive "first surprise" after material digestion.
- 保持产品个性,不要稀释成通用聊天机器人 UI。
