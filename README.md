<br>

<p align="center">
  <img src="assets/readme/logo_foxsay.jpg" alt="FoxSay Logo" width="80" style="border-radius: 16px;">
</p>

<h1 align="center">
  <span style="color: #F59E0B;">Fox</span><span style="color: #111317;">Say</span>
</h1>

<p align="center">
  <strong style="font-size: 1.3em; color: #E8651A;">啃完一门课，带你过期末</strong>
</p>

<p align="center" style="color: #7A7A8E; font-size: 1.05em; max-width: 600px; margin: 0 auto;">
  面向中国本科生的课程级 AI 学习 Copilot<br>
  只在课程边界内回答 · 强制来源引用 · 超范围诚实拒答
</p>

<br>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-0.112-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Tests-168%20passing-22C55E?style=for-the-badge" alt="Tests">
  <img src="https://img.shields.io/badge/Status-MVP-F59E0B?style=for-the-badge" alt="MVP">
</p>

<br>

<p align="center">
  <img src="assets/readme/hero_1280x720.jpg" alt="FoxSay Hero" width="900" style="border-radius: 16px; box-shadow: 0 8px 32px rgba(0,0,0,0.1);">
</p>

<br>

---

## 🦊 FoxSay 是什么？

FoxSay 不是通用问答工具，是以**「课程」为原子单位**的 AI 学习 Copilot。每门课完全隔离——材料、向量检索、骨架图、对话历史、复习计划都绑定 `course_id`。AI 只基于你上传的课程材料回答，不用模型常识瞎编，每条回答都带来源引用。

<table>
<tr>
<td width="33%" align="center" style="background: #FFF7ED; border-radius: 12px; padding: 1.5rem;">
<div style="font-size: 2em;">🎯</div>
<h3 style="color: #E8651A; margin: 0.5rem 0;">课程边界</h3>
<p style="color: #7A7A8E; font-size: 0.9em; margin: 0;">只回答当前课程内的问题<br>超出范围诚实拒答，不泛化</p>
</td>
<td width="33%" align="center" style="background: #FFF7ED; border-radius: 12px; padding: 1.5rem;">
<div style="font-size: 2em;">📚</div>
<h3 style="color: #E8651A; margin: 0.5rem 0;">材料驱动</h3>
<p style="color: #7A7A8E; font-size: 0.9em; margin: 0;">每条回答带来源引用<br>能定位到具体文件和章节</p>
</td>
<td width="33%" align="center" style="background: #FFF7ED; border-radius: 12px; padding: 1.5rem;">
<div style="font-size: 2em;">🦊</div>
<h3 style="color: #E8651A; margin: 0.5rem 0;">狐狸陪伴</h3>
<p style="color: #7A7A8E; font-size: 0.9em; margin: 0;">不是冷冰冰的问答机器<br>是陪你啃书的调皮学长/学姐</p>
</td>
</tr>
</table>

---

## ✨ 功能一览

<table>
<tr>
<td width="50%" style="padding: 1rem;">
<div style="font-size: 1.5em;">📥</div>
<h3 style="margin: 0.3rem 0; color: #111317;">课程导入</h3>
<p style="color: #7A7A8E; font-size: 0.9em; margin: 0;">CSV/Excel 课程表导入，自动建立书架和考试倒计时；也支持手动创建课程作为兜底。</p>
</td>
<td width="50%" style="padding: 1rem;">
<div style="font-size: 1.5em;">📄</div>
<h3 style="margin: 0.3rem 0; color: #111317;">材料处理</h3>
<p style="color: #7A7A8E; font-size: 0.9em; margin: 0;">支持 PDF、PPT、图片、文本备注，走异步 7 步处理流水线，后台安静消化。</p>
</td>
</tr>
<tr>
<td width="50%" style="padding: 1rem;">
<div style="font-size: 1.5em;">🗺️</div>
<h3 style="margin: 0.3rem 0; color: #111317;">课程骨架图</h3>
<p style="color: #7A7A8E; font-size: 0.9em; margin: 0;">材料处理完成后自动生成章节、核心概念、难点和先修链路，一眼看清知识结构。</p>
</td>
<td width="50%" style="padding: 1rem;">
<div style="font-size: 1.5em;">💬</div>
<h3 style="margin: 0.3rem 0; color: #111317;">课程内问答</h3>
<p style="color: #7A7A8E; font-size: 0.9em; margin: 0;">CRAG 门控检索，置信度不够就拒答；回答强制附来源引用，点一下就能跳到原文。</p>
</td>
</tr>
<tr>
<td width="50%" style="padding: 1rem;">
<div style="font-size: 1.5em;">🧠</div>
<h3 style="margin: 0.3rem 0; color: #111317;">11 工具 ReAct Agent</h3>
<p style="color: #7A7A8E; font-size: 0.9em; margin: 0;">7 个静态工具 + 4 个动态 Skill：讲义生成、练习题、闪卡、概念图谱，随叫随到。</p>
</td>
<td width="50%" style="padding: 1rem;">
<div style="font-size: 1.5em;">🕸️</div>
<h3 style="margin: 0.3rem 0; color: #111317;">知识图谱</h3>
<p style="color: #7A7A8E; font-size: 0.9em; margin: 0;">reactflow + dagre 可视化章节知识网络，概念之间的先修关系一目了然。</p>
</td>
</tr>
<tr>
<td width="50%" style="padding: 1rem;">
<div style="font-size: 1.5em;">📝</div>
<h3 style="margin: 0.3rem 0; color: #111317;">课程笔记</h3>
<p style="color: #7A7A8E; font-size: 0.9em; margin: 0;">从聊天记录或引用片段一键保存笔记，按课程隔离，随时回看。</p>
</td>
<td width="50%" style="padding: 1rem;">
<div style="font-size: 1.5em;">🔥</div>
<h3 style="margin: 0.3rem 0; color: #111317;">超级备考模式</h3>
<p style="color: #7A7A8E; font-size: 0.9em; margin: 0;">根据考试日期生成复习计划，状态化陪伴复习，讲一节、练一题、总结一下；支持 <code>/btw</code> 随时插话。</p>
</td>
</tr>
</table>

---

## 🖼️ 两种模式

### 📖 日常学习

<p align="center">
  <img src="assets/readme/scenario_study_1280x720.jpg" alt="日常学习模式" width="800" style="border-radius: 14px; box-shadow: 0 4px 16px rgba(0,0,0,0.08);">
</p>

三栏 NotebookLM 风格布局：左边书架和课程列表，中间对话工作区，右边来源面板和 Studio 工具。材料消化完后，骨架图、知识图谱、笔记随时切换。

### 🔥 超级备考

<p align="center">
  <img src="assets/readme/scenario_exam_1280x720.jpg" alt="超级备考模式" width="800" style="border-radius: 14px; box-shadow: 0 4px 16px rgba(0,0,0,0.08);">
</p>

考试倒计时挂在顶部。狐狸根据剩余天数帮你拆复习计划，每天带你过几个概念，讲完就出题，做完再总结。临时想到什么问题，输入 `/btw` 随时插，不打断复习节奏。

---

## 🚀 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 1. 复制环境变量模板，填入 DeepSeek API Key
cp examples/env.example .env

# 2. 一键启动（前端 + 后端 + Qdrant）
docker compose -f infra/docker-compose.yml up --build
```

启动后访问：

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:3000 |
| 后端 API 文档 | http://localhost:8000/docs |
| Qdrant 面板 | http://localhost:6333/dashboard |

### 方式二：本地开发

```bash
# 后端（FastAPI + uv）
cd backend && uv sync && uv run uvicorn app.main:app --reload

# 前端（Vite + React）
cd frontend && npm install && npm run dev
```

> ⚠️ 本地开发同样需要 Qdrant 向量数据库，可以用 Docker 单独启动：
> ```bash
> docker run -d --name foxsay-qdrant -p 6333:6333 qdrant/qdrant:latest
> ```

---

## 🏗️ 技术栈

<p align="center">
  <table>
  <tr>
  <td align="center" width="200" style="border: 1px solid #E8DDD0; border-radius: 12px; padding: 1rem;">
    <div style="font-size: 2em;">⚛️</div>
    <strong>Frontend</strong>
    <p style="color: #7A7A8E; font-size: 0.85em; margin: 0.3rem 0 0;">Vite + React<br>TypeScript + Tailwind</p>
  </td>
  <td align="center" width="40" style="border: none;">
    <span style="color: #E8651A; font-size: 1.5em; font-weight: bold;">→</span>
  </td>
  <td align="center" width="200" style="border: 1px solid #E8DDD0; border-radius: 12px; padding: 1rem;">
    <div style="font-size: 2em;">⚡</div>
    <strong>Backend</strong>
    <p style="color: #7A7A8E; font-size: 0.85em; margin: 0.3rem 0 0;">FastAPI + Python<br>uv 包管理</p>
  </td>
  <td align="center" width="40" style="border: none;">
    <span style="color: #E8651A; font-size: 1.5em; font-weight: bold;">→</span>
  </td>
  <td align="center" width="200" style="border: 1px solid #E8DDD0; border-radius: 12px; padding: 1rem;">
    <div style="font-size: 2em;">🔍</div>
    <strong>Vector Store</strong>
    <p style="color: #7A7A8E; font-size: 0.85em; margin: 0.3rem 0 0;">Qdrant<br>单层 RAG + CRAG</p>
  </td>
  </tr>
  </table>
</p>

- **LLM**：DeepSeek API（V4 Flash / V4 Pro）
- **Embedding**：可配置（通过环境变量指定）
- **部署基线**：Docker Compose

---

## 📁 项目结构

```
fox-say/
├── frontend/          # Vite + React + TypeScript + Tailwind
│   └── src/
│       ├── features/  # bookshelf / course / onboarding
│       ├── components/ui/  # 基础 UI 组件
│       └── shared/    # API 客户端、类型、文案
├── backend/           # FastAPI + Python (uv + pyproject.toml)
│   └── app/
│       ├── api/       # 11 个 API 路由模块
│       ├── services/  # 17 个 service（agent/pipeline/retrieval/...）
│       ├── core/      # 配置、依赖
│       └── db/        # SQLite 存储
├── infra/             # Docker Compose（Qdrant + backend + frontend）
├── docs/              # 架构文档、CRAG 策略、postmortem
├── scripts/           # e2e 测试脚本
└── assets/readme/     # README 用图
```

当前测试覆盖：**18 个测试文件，168 个测试用例全部通过**。

---

## 📐 CRAG 边界控制

FoxSay 用 CRAG（Corrective RAG）做检索置信度门控，回答质量有硬阈值：

<table>
<tr>
<td align="center" width="25%" style="background: #E6F7F5; border-radius: 10px; padding: 1rem;">
<div style="font-size: 1.5em;">🟢</div>
<strong style="color: #0D9488;">score ≥ 0.72</strong>
<p style="color: #7A7A8E; font-size: 0.85em; margin: 0.3rem 0 0;">正常回答<br>带完整来源引用</p>
</td>
<td align="center" width="25%" style="background: #FFF7ED; border-radius: 10px; padding: 1rem;">
<div style="font-size: 1.5em;">🟡</div>
<strong style="color: #F59E0B;">0.55 ≤ score &lt; 0.72</strong>
<p style="color: #7A7A8E; font-size: 0.85em; margin: 0.3rem 0 0;">扩展检索<br>谨慎回答，标注低置信</p>
</td>
<td align="center" width="25%" style="background: #FEF2F2; border-radius: 10px; padding: 1rem;">
<div style="font-size: 1.5em;">🔴</div>
<strong style="color: #EF4444;">score &lt; 0.55</strong>
<p style="color: #7A7A8E; font-size: 0.85em; margin: 0.3rem 0 0;">诚实拒答<br>"这个问题超出了范围，不知道。"</p>
</td>
</tr>
</table>

---

## 📚 真相之源（Source of Truth）

所有工程约束和架构文档以这些文件为准：

| 文件 | 内容 |
|------|------|
| [AGENTS.md](AGENTS.md) | 最高优先级工程与产品约束，任何 agent 操作前必读 |
| [HANDOFF.md](HANDOFF.md) | 交接文档，记录当前 git 状态、架构、已知问题 |
| [docs/architecture.md](docs/architecture.md) | MVP 架构总览（API 端点、Agent、测试策略） |
| [docs/crag-policy.md](docs/crag-policy.md) | 检索置信度阈值与拒答策略细节 |
| [docs/product-boundaries.md](docs/product-boundaries.md) | MVP 范围与 post-MVP 规划 |
| [docs/postmortem/verified.md](docs/postmortem/verified.md) | 已验证的外部依赖标识符（模型名、API endpoint） |

---

## ⚠️ MVP 范围说明

FoxSay MVP **只做**课程级 AI 学习 Copilot，不包含：诊断 15 题、自动出卷、多用户/权限体系、课程胶囊分享、社区广场、全局日程智能体。这些是 post-MVP 才考虑的方向。

实现任何功能前，请先读 [AGENTS.md](AGENTS.md) 并确保所有操作都是 course-scoped 的——检索、回答、骨架、复习计划或 `/btw` 交互都必须显式绑定 `course_id`。

<br>

<p align="center">
  <span style="color: #F59E0B; font-size: 1.1em;">🦊</span>
  <br>
  <span style="color: #7A7A8E; font-size: 0.9em;">"材料扔进来，剩下的交给狐狸。"</span>
</p>

<br>
