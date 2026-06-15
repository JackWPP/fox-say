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
- LLM: DeepSeek OpenAI-compatible API(实际可用的 model string 必须是**先在 `docs/postmortem/verified.md` 写"已验证"记录**才能用,见 HEC-5)。当前已知可用:`deepseek-v4-flash` / `deepseek-v4-pro`(2026 V4),以及到 2026/07/24 之前兼容的 `deepseek-chat` / `deepseek-reasoner`。
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

### HEC-8. 文档必须与代码对齐
- `docs/architecture.md` 必须反映实际代码架构,不是理想架构
- 架构变更后必须同步更新 architecture.md
- 过时文档必须在顶部标注 `⚠️ 已过时` + 日期 + 原因
- 新 agent 读到的文档必须能直接指导代码修改,不需要"先猜再验证"
- HANDOFF.md 的架构描述必须与 architecture.md 一致

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
- Architecture changes must update `docs/architecture.md` in the same commit.

## Design Direction
- Product voice: smart, mischievous fox; helpful but not generic.
- Visual direction: fox amber orange, midnight charcoal, warm white.
- Interaction principles: zero-friction capture, async processing, proactive "first surprise" after material digestion.
- Do not dilute the core experience into a generic chatbot UI.
