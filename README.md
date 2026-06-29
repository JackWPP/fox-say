# FoxSay

FoxSay 是面向中国本科生的课程级 AI 学习 Copilot。核心承诺严格:只在当前课程边界内回答,引用已上传的课程材料,超出范围主动拒答。

## 当前状态

FoxSay MVP 已可用,采用 NotebookLM 风格三栏布局。支持:

- 课程创建(手动或 CSV/Excel 课程表导入)带考试倒计时
- 材料上传(PDF、PPT、文本)走异步 7 步处理流水线
- 课程骨架图生成(优先从 course_index 派生,带 LLM fallback)
- 课程概述自动生成 + AI 重新生成 API
- 课程级 CRAG 问答,强制引用 + 来源预览
- 11 工具 ReAct Agent(7 静态 + 4 动态 Skill:讲义/练习题/闪卡/概念图谱)
- 知识图谱可视化(reactflow + dagre,从 ChapterWiki + KC 派生)
- 课程级笔记 CRUD(从聊天/引用保存)
- 超级备考模式(复习计划 + 状态化陪伴复习 + `/btw` 插话)
- Docker Compose 部署(前端、后端、Qdrant)

## 快速开始

```bash
cp examples/env.example .env   # 填入 DeepSeek API key 和 embedding API key
docker compose -f infra/docker-compose.yml up --build
# 前端: http://localhost:3000
# 后端 API 文档: http://localhost:8000/docs
```

本地开发:

```bash
# 后端
cd backend && uv sync && uv run uvicorn app.main:app --reload

# 前端
cd frontend && npm install && npm run dev
```

## 真相之源(Source Of Truth)

- `AGENTS.md`:后续 agent 必须遵守的工程与产品约束。
- `HANDOFF.md`:交接文档,记录当前 git 状态、架构、已知问题。
- `docs/architecture.md`:MVP 架构总览(39 个 API 端点、11 工具 Agent、测试)。
- `docs/crag-policy.md`:检索置信度与拒答策略(0.72/0.55 阈值)。
- `docs/postmortem/verified.md`:已验证外部依赖标识符(HEC-5)。
- `docs/product-boundaries.md`:MVP 与 post-MVP 范围。

## 项目结构

- `frontend/`:Vite + React + TypeScript + Tailwind(3 个 feature:bookshelf、course、onboarding)。
- `backend/`:FastAPI + Python,由 `uv` 和 `pyproject.toml` 管理(17 个 service,18 个测试文件,168 个测试)。
- `infra/`:Docker Compose(Qdrant、backend、frontend)。
- `docs/`:架构、契约、postmortem、差距分析、路线图。
- `scripts/`:端到端测试脚本(e2e_7tools、e2e_btw、playwright_frontend_audit)。

## 实现规则

实现任何功能前,先查 `AGENTS.md` 并保持工作 course-scoped。任何检索、回答、骨架、复习计划或 `/btw` 交互都必须显式绑定 `course_id`。
