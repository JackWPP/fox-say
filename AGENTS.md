# FoxSay Agent Operating Contract

本文件是 FoxSay 项目的最高优先级工程约束。后续任何 Agent、脚手架生成、功能实现、重构、测试和文档编写都必须先遵守本文件，再参考 `foxsay-prd.md`。

## Product Boundary
- FoxSay 是以“课程”为原子单位的 AI 学习 Copilot，不是通用问答工具。
- 每门课程必须完全隔离：材料、向量检索、知识图谱、骨架图、对话历史、复习计划都必须显式绑定 `course_id`。
- AI 只能基于当前课程已上传或已记录的材料回答。不得用模型常识补齐课程外内容。
- 每条课程内回答必须包含来源引用，引用格式必须能定位到材料和章节/片段，例如 `来自 [文件名] · 第X部分`。
- 当问题超出课程范围时，必须诚实拒答，不得编造、泛化或转向通用百科回答。

## MVP Scope
MVP 只包含以下功能：
- 课程表导入：从 CSV/Excel 课程表建立书架和考试倒计时。
- 手动创建课程：作为课程表导入失败或缺失时的兜底。
- 材料上传与处理：PDF、PPT、图片、文本备注进入课程材料库。
- 课程骨架图：材料首次处理完成后生成章节、核心概念、难点和先修链路。
- 课程内问答：使用 CRAG 边界控制，回答必须带来源引用。
- 超级备考模式：生成复习计划，支持陪伴复习和 `/btw` 插话。

默认不得实现以下后置功能：
- 诊断 15 题。
- 出卷功能。
- 多用户、权限、团队协作或账号体系。
- 课程胶囊分享、社区广场、社交传播。
- 全局日程智能体或学生版 Cowork。

## Technical Constraints
- Frontend: Vite + React + TypeScript + Tailwind.
- Backend: FastAPI + Python managed by `uv` and `pyproject.toml`.
- Vector store: Qdrant through Docker Compose.
- Knowledge graph: NetworkX for MVP. Do not introduce Neo4j before the post-MVP phase.
- RAG direction: LightRAG-style incremental retrieval. Avoid heavyweight full graph rebuilds for MVP paths.
- Boundary control: CRAG gate plus system-prompt hard constraints.
- LLM: DeepSeek OpenAI-compatible API, model string `deepseek-v4-flash`.
- Deployment baseline: Docker Compose.

## CRAG Policy
- `score >= 0.72`: answer normally with citations.
- `0.55 <= score < 0.72`: expand retrieval and answer cautiously with confidence status.
- `score < 0.55`: refuse to answer with the message shape `这个问题超出了[课程名]的范围，我不知道。`
- Production UI may hide debug confidence labels, but backend responses must preserve enough metadata for auditing.

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

## Design Direction
- Product voice: smart, mischievous fox; helpful but not generic.
- Visual direction: fox amber orange, midnight charcoal, warm white.
- Interaction principles: zero-friction capture, async processing, proactive “first surprise” after material digestion.
- Do not dilute the core experience into a generic chatbot UI.

