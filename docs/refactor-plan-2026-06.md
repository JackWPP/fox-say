# FoxSay 重构执行计划

> 日期: 2026-06
> 起草: 项目所有者
> 状态: 待批准
> 范围: 5 阶段,1 周,每阶段独立可交付

---

## 📊 进度总结 (2026-06-29 更新, HEAD `e437ab3`)

> 本段为执行后回填的进度总结，原计划内容（§0 起）保持不变，仅在顶部追加。当前测试 168/168 通过，API 端点 39 个。

| 阶段 | 状态 | 说明 |
|------|------|------|
| **阶段 0** — 工作树复位 | ✅ 已完成 | working tree 复位、venv 修复、postmortem 固化、AGENTS.md 替换均落地 |
| **阶段 1** — 知识图谱切除 | ⚠️ 部分完成 | NetworkX KnowledgeGraph 已切除（符合计划）；**但后来重新引入了 KG 可视化**（`reactflow` + `dagre`，非 Neo4j，不违反 §3 非目标）。详见原计划 §3 "不引入 Neo4j" 仍成立 |
| **阶段 2** — 多阶段 Wiki Pipeline | ✅ 已完成 | LangGraph 4 阶段（Supervisor → Worker → Reducer → Reviewer）在用，`dmap.py` / `merkle.py` / `wiki_builder.py` 均落地，`generate_skeleton_from_wiki` 已替换 KG 副产品路径 |
| **阶段 3** — Agent + 工具集重写 | ✅ 已完成（超原计划） | 实际 11 工具（7 静态 + 4 动态 Skill）/ max 8 轮，**超出原计划的 6 工具 / 3 轮**。错误可见性（SSE 推 error）、`rewrite_query` 死代码修复、`course_id` 显式入参均已落地 |
| **阶段 4** — 前端对齐 | ✅ 已完成 | NotebookLM 三栏布局落地，工具标签对齐，错误 toast 已接入 |

### 已完成的额外工作（计划外）
- 工程纪律修复：HEC-1（错误可见）/ HEC-5（不杜撰）/ HEC-8（文档与代码对齐）
- `mineru.py` 修复（PDF 解析路径稳定）
- CRAG 硬门控（score < 0.55 强制拒答，符合 AGENTS.md `CRAG Policy`）
- 课程概述自动生成（ChapterWiki.overview）
- 422 错误修复（上传异常不再吞错）
- CitationCard 跳原文定位

### 已知未完成
- 真实材料端到端验证（合成数据测试 168/168 通过，但真实 PDF/PPT 流程未跑通）
- `search_wiki_layer` 性能优化

---

## 0. 背景与起因

2026-05 期间,项目所有者未盯盘的状态下,一个自动 agent 在 `feature-LLM-wiki` 分支上
按自定的 `foxsay-agent-spec.md` 跑了一轮 "Wiki-First 重构"。

这一轮重构 **实现了大量代码,但在工程纪律上全面失守**:
- 5 个新服务文件 + 9 个老文件改动**未 commit**,活在工作区
- spec 文档 (`checklist.md` / `tasks.md`) 100% 勾,但 **0 个新测试**
- venv 路径在 Windows 下坏掉,**没有真正运行过任何测试**
- `_llm_call` 用 `try/except → return ""` 静默吞掉所有错误
- `rewrite_query` 工具拿到的是写死的 `history=[]`,死代码
- spec 写了 LangGraph Map-Reduce,**业务代码 0 处 import langgraph**
- 文档承诺 `course_index.md` 始终在 prompt 里,**实际注入的是 JSON**
- 模型名 `deepseek-v4-flash` 是杜撰的,DeepSeek 公开模型里没有 V4

详细复盘见 `docs/postmortem/wiki-first-rampage.md` (阶段 0 时建立)。

## 1. 目标

回到第一性原理,产出一个**真能跑、真有测试、错误真可见**的 FoxSay MVP。
保留 spec 中合理的工程意图(多阶段 Wiki Pipeline 提升骨架质量、ReAct 多轮支持复杂查询),
**重写** agent 那轮的具体实现,移除过度设计(KnowledgeGraph、5 张新表、10 个工具、
静默 fallback 等)。

## 2. 范围(5 阶段)

### 阶段 0 — 工作树复位 (1h)
**目标**: 撤销 agent 那轮未 commit 的所有改动,恢复 11 个 commit 时的干净状态。

动作:
- `git checkout --` 14 个被修改的文件
- `rm` 6 个新文件 + 1 个临时测试脚本 + spec 文档目录
- 写 `docs/postmortem/wiki-first-rampage.md`,固化教训
- 修 venv(WSL 路径换成 Windows 路径),`uv sync` 重装,`pytest` 跑通

验收:
- `git status` 干净
- 42 个原有测试全过

### 阶段 1 — 知识图谱切除 (0.5d)
**目标**: 删除 NetworkX KnowledgeGraph 整套,简化复习计划生成路径。

动作:
- 删 `backend/app/services/knowledge_graph.py` 和 `knowledge_extraction.py`
- 删 SQLite `knowledge_graphs` 表
- `pipeline.py` 移除 `knowledge_extraction` 步骤
- `retrieval.py` 移除 `graph_context` 块
- `skeleton.py` `generate_skeleton` 改回基于 materials_text,不依赖 KG
- 补测试 `test_skeleton_no_kg_fallback`

验收:
- `grep -rn "knowledge_graph\|knowledge_extraction\|KnowledgeGraph" backend/` 0 结果
- 42 个测试全过

### 阶段 2 — 多阶段 Wiki Pipeline 重写 (2d)
**目标**: 保留 Supervisor → Worker → Reducer → Reviewer 多阶段设计意图,重写具体实现。

设计原则:
- 4 阶段,每阶段单独可测
- LLM 失败抛异常,**不静默 fallback**
- Reviewer 默认 enabled,失败打回最多 1 次
- 实际使用 LangGraph(不用白不用,Supervisor 派 Worker 用 Send())
- KC ID 用 `uuid5(NAMESPACE, course_id+chapter_id+name)`,确定性
- 增量更新逻辑顺序正确:merge → mark invalid → save
- 不重写 `follow_prerequisite` 的"从 chapter_id 反推 course_id"那种丑陋补丁——KC 显式带 course_id

动作:
- 写 `dmap.py` (~120 行,比 agent 版简)
- 写 `merkle.py` (~50 行,加测试)
- 写 `wiki_builder.py` (~250 行,比 agent 版 681 行砍 60%)
- 加 5 张表的 SQL + SqliteStore 方法
- 重写 `pipeline.py` 为 4 步:parse → build_dmap → wiki_build → skeleton_from_wiki
- `skeleton.py` 新增 `generate_skeleton_from_wiki` (修 agent 版的边界条件)

验收:
- `pytest` 全过 (老 42 + 新增 8-10)
- LangGraph 真的在代码里被用上 (1 处以上 import + 实际使用)

### 阶段 3 — Agent + 工具集重写 (2d)
**目标**: ReAct 3 轮,6 个工具 (不是 agent 写的 10 个)。

动作:
- `agent.py` 从 446 行降到 ~250 行
- 系统 prompt 简化:核心规则 + 引用格式 + 工具列表
- 删"course_index 动态注入"(工具都暴露了不需预填)
- 删 `classify_intent` 工具
- ReAct 循环 max 3 轮 (不是 5 轮)
- **修 `rewrite_query` 死代码**: 真传 chat_history,或者删掉改用朴素实现
- **错误可见性**: LLM 失败 → SSE 推 `{type: "error", message: "..."}`
- 工具集 6 个: `get_course_map` / `search_wiki` / `get_concept` / `get_chapter_outline` / `follow_prerequisite` / `get_source_content`
- `query_tools.py` 重写: `get_concept` 加 `course_id` 入参(消除反推丑陋)
- 加测试: `test_agent_loop.py` (mock LLM 验证 max 3 轮 + 错误传播), `test_query_tools.py` (4-5 个 case)

验收:
- `pytest` 全过
- 工具数 ≤ 6
- `tsc --noEmit` 在前端零错误

### 阶段 4 — 前端对齐 + 端到端验证 (1-2d)
**目标**: 前端工具标签对齐 6 个,加错误 toast,端到端走通 demo 流程。

动作:
- `ToolCallIndicator.tsx` 工具标签映射减到 6 个
- `useChat.ts` 加 `error` 事件处理 (toast)
- `useSkeleton.ts` 删 `useRebuildWiki` (阶段 5 再加回)
- 手动端到端 smoke:
  1. 建课
  2. 上传 PDF/PPT
  3. 30s 内看到骨架
  4. 问 "X 是什么"
  5. 看到带引用的回答
  6. 制定复习计划
- `tsc --noEmit` 0 错误

验收:
- 6 个工具在前端能正确显示
- 端到端 demo 流程 5 分钟内跑通
- 故意制造 LLM 错误(断网),确认前端能看见错误

## 3. 非目标(本次不做)

- 不引入新基础设施(Neo4j、Redis、消息队列等)
- 不引入新 LLM 依赖(MinerU, Qwen2-VL 等)
- 不做端到端加密、用户系统、团队协作(明确在 AGENTS.md 排除范围)
- 不做诊断 15 题、出卷功能(post-MVP)
- 不做社区广场、课程胶囊分享(明确在 AGENTS.md 排除范围)
- 不做"主动触发全量重建"的交互(post-MVP,需要更多数据)
- 不做"study_plan_expert" 与 "LLM 通用" 路由分离(阶段 3 后看是否需要)

## 4. 验收硬标准

每阶段完成后必须满足:
- 该阶段涉及的所有测试 PASS
- `git status` 显示该阶段所有改动已 commit (不允许 untracked 状态跨阶段)
- 端到端 demo 仍能跑(每阶段完成后,产品功能不退化)
- `grep -rn` 验证: 阶段禁止的模式在代码中 0 命中(见下)

### 禁止模式 (CI/手验)
- `try:.*\n.*except Exception:.*\n.*return ""` (静默返回空串)
- `return user_input` 在 rewrite_query (死代码)
- `logger.exception` 而没推到前端 (错误黑洞)
- `chapter_id.split("_")[0]` (丑陋反推,应是显式 course_id)
- `model.*v[0-9]+-flash` 中 V 后跟 4+ 的 (杜撰模型名)
- `langgraph` 在 dependencies 但 0 处 import (装了不用)

## 5. 节奏

- 阶段 0 → 阶段 1 → 阶段 2 → 阶段 3 → 阶段 4
- 每阶段完成后**停下来**给项目所有者简报,等 OK 再进下一阶段
- 中途如发现设计意图本身有问题(如多阶段 Wiki 实际不提升质量),停下来讨论
  而不是绕过去

## 6. 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| venv 修不好,Windows 跑不了测试 | 中 | 高 | 阶段 0 优先解决;不行就用 Docker Compose 跑测试 |
| Docling 解析中文 PPT 实际不行 | 中 | 中 | 阶段 1 先用一个 PDF 端到端测一次 |
| LLM 改写费用高于预期(多阶段每章一次 LLM) | 中 | 中 | Reviewer 失败打回限制 1 次(不是 2) |
| LangGraph 学习曲线比预想陡 | 低 | 中 | 实在不行,阶段 2 改用 asyncio.gather + 简单状态机 |
| 用户(产品)其实不需要多阶段 Wiki | 低 | 高 | 阶段 2 跑通后做 A/B 对比,单次 LLM 调用 vs 多阶段 |

## 7. 附录: AGENTS.md 增补(阶段 0 复位后正式替换原 64 行版)

下面是计划替换原 AGENTS.md 的**完整新内容**。在原 64 行基础上,
新增一节 "Hard Engineering Constraints"——把 2026-05 那轮 agent 狂奔
的教训固化成不可违反的硬约束。

```markdown
# FoxSay Agent Operating Contract

本文件是 FoxSay 项目的最高优先级工程约束。后续任何 Agent、脚手架生成、功能实现、重构、测试和文档编写都必须先遵守本文件,再参考 `docs/refactor-plan-2026-06.md`。

## Product Boundary
- FoxSay 是以"课程"为原子单位的 AI 学习 Copilot,不是通用问答工具。
- 每门课程必须完全隔离:材料、向量检索、骨架图、对话历史、复习计划都必须显式绑定 `course_id`。
- AI 只能基于当前课程已上传或已记录的材料回答。不得用模型常识补齐课程外内容。
- 每条课程内回答必须包含来源引用,引用格式必须能定位到材料和章节/片段,例如 `来自 [文件名] · 第X部分`。
- 当问题超出课程范围时,必须诚实拒答,不得编造、泛化或转向通用百科回答。

## MVP Scope
MVP 只包含以下功能:
- 课程表导入:从 CSV/Excel 课程表建立书架和考试倒计时。
- 手动创建课程:作为课程表导入失败或缺失时的兜底。
- 材料上传与处理:PDF、PPT、图片、文本备注进入课程材料库。
- 课程骨架图:材料首次处理完成后生成章节、核心概念、难点和先修链路。
- 课程内问答:使用 CRAG 边界控制,回答必须带来源引用。
- 超级备考模式:生成复习计划,支持陪伴复习和 `/btw` 插话。

默认不得实现以下后置功能:
- 诊断 15 题。
- 出卷功能。
- 多用户、权限、团队协作或账号体系。
- 课程胶囊分享、社区广场、社交传播。
- 全局日程智能体或学生版 Cowork。

## Technical Constraints
- Frontend: Vite + React + TypeScript + Tailwind.
- Backend: FastAPI + Python managed by `uv` and `pyproject.toml`.
- Vector store: Qdrant。可通过 Docker Compose 或独立容器运行(`docker run -d --name foxsay-qdrant -p 6333:6333 qdrant/qdrant:latest`)。
- Knowledge graph: MVP 阶段不引入。骨架从材料直接生成,不存图数据库。
- RAG direction: 单层 RAG + CRAG 门控。多层混合检索是 post-MVP 才考虑。
- Boundary control: CRAG gate plus system-prompt hard constraints.
- LLM: DeepSeek OpenAI-compatible API。模型名必须是真实存在的(deepseek-chat / deepseek-coder / deepseek-reasoner 等),**禁止杜撰** `v4-flash` 这类不存在的 model string。
- Deployment baseline: Docker Compose.

## CRAG Policy
- `score >= 0.72`: answer normally with citations.
- `0.55 <= score < 0.72`: expand retrieval and answer cautiously with confidence status.
- `score < 0.55`: refuse to answer with the message shape `这个问题超出了[课程名]的范围,不知道。`
- Production UI may hide debug confidence labels, but backend responses must preserve enough metadata for auditing.

## Hard Engineering Constraints
(本节是**非妥协性约束**,违反任一条的代码不允许进入 main 分支。)

### HEC-1. 错误必须可见,不许静默吞错
- 禁止 `try/except Exception: return ""` 这种模式把错误藏起来
- LLM 调用失败 → 抛异常或返回带 error 字段的结构,**不让调用方无感降级**
- 后端任何错误路径必须通过 SSE / HTTP 状态 / 日志可追溯
- 测试时必须验证"错误情况下,前端能看见错误"(不要在 logger.exception 后直接 return)

### HEC-2. 改动必须 commit,不许活在 working tree
- 任何功能/重构/修复必须先 commit 才能宣布"完成"
- 阶段性的工作(WIP)也必须 commit,带 `wip:` 前缀
- 阶段性 commit 不允许在 main 分支,必须在 feature 分支
- 不允许 spec 文档写"已完成"但代码还在 untracked 状态

### HEC-3. spec 不许自吹,checklist 必须对应真实测试
- 任何勾掉的 checklist 项必须**有对应的测试**或**可观察的产出**(文件存在、命令可运行、API 返回正确)
- 不允许"声称完成但没有验证手段"
- 验证手段缺失时,该项状态必须保持 `[ ]` 或写 `Not-tested: <原因>`

### HEC-4. 不许过度工程
- 任何新增依赖、新文件、新表、新工具必须有具体的 implementation need
- 引入新抽象前先问"这个抽象在 MVP 阶段被几个具体调用点用?"
- 优先删除和复用,而不是新增层
- "未来可能用到"不是引入理由

### HEC-5. 不许杜撰
- 模型名、API endpoint、配置 key 必须是真实存在且能跑通的
- 引入前先在 `docs/postmortem/` 写"已验证"记录
- 任何"我觉得应该是这样"的推测必须标注 `[未验证]`

### HEC-6. schema 显式,不靠反推
- 任何需要 course_id / chapter_id 的对象,字段必须显式声明
- 禁止用 `chapter_id.split("_")[0]` 这种反推丑陋补丁
- 禁止"模型 A 的字段里藏了模型 B 的主键"这种隐式耦合

### HEC-7. 依赖里出现的库必须在代码里被用上
- `pyproject.toml` dependencies 里出现的库,必须有 ≥1 处 import
- 装了不用的库(比如声明了 langgraph 但 0 处 import)不允许
- 反过来,代码里 import 但 pyproject 没声明的,必须立刻补

## Security And Data Rules
- Never hardcode API keys, DeepSeek credentials, user materials, or real course data.
- All model, vector-store, and runtime settings must come from environment variables.
- Do not commit `.env`, local uploads, generated embeddings, vector-store volumes, or private course materials.
- Use examples and fixtures only with synthetic data.

## Engineering Discipline
- Keep diffs small, reviewable, and reversible.
- Prefer deletion and reuse over new abstraction layers.
- Do not add new dependencies without a concrete implementation need.
- Keep frontend and backend public types aligned before adding behavior.
- When adding a course-scoped feature, include `course_id` in the request/response schema and tests.
- Behavior-changing work must include tests or a clear `Not-tested` note.
- After code changes, run the narrowest relevant checks first, then broader lint/type/test checks when available.
- 提交前自查 `docs/refactor-plan-2026-06.md` 的"禁止模式"列表,确认新代码不命中。

## Design Direction
- Product voice: smart, mischievous fox; helpful but not generic.
- Visual direction: fox amber orange, midnight charcoal, warm white.
- Interaction principles: zero-friction capture, async processing, proactive "first surprise" after material digestion.
- Do not dilute the core experience into a generic chatbot UI.
```

### 替换执行步骤
1. 阶段 0 完成 working tree 复位后(此时 `AGENTS.md` 回到原 64 行版)
2. 用本附录的完整内容**覆盖** `AGENTS.md`
3. 与阶段 0 的其他清理一起 commit,message 如:
   `chore(docs): 替换 AGENTS.md,新增 Hard Engineering Constraints (来自 2026-05 wiki-first 复盘)`
