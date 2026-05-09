# FoxSay MVP 实现规格

## Why
FoxSay 项目目前仅是结构性脚手架：前后端均无安装依赖、无可运行代码、无可用的 API 端点。本变更将脚手架转化为可运行的 MVP 产品，覆盖 AGENTS.md 中定义的全部 MVP 功能。

## What Changes
- 安装前后端全部依赖并建立可运行的 dev server
- 实现 FastAPI 后端全部 MVP API 端点（8 个合约端点）
- 实现 Vite + React 前端全部 MVP 页面与交互
- 实现课程表 CSV/Excel 导入、手动创建课程
- 实现材料上传与异步处理管线（解析→分块→嵌入→Qdrant 存储）
- 实现课程骨架图生成（NetworkX 图 + LLM 提取）
- 实现 CRAG 边界控制的课程问答
- 实现超级备考模式（复习计划 + `/btw` 插话）
- Docker Compose 增加后端服务
- 补充端到端测试与单元测试

## Impact
- Affected specs: 全部 MVP 功能模块
- Affected code: `backend/`, `frontend/`, `infra/docker-compose.yml`

## ADDED Requirements

### Requirement: 项目引导与基础架构
系统 SHALL 提供可运行的前后端开发环境。

#### Scenario: 后端启动
- **WHEN** 开发者运行 `uv run uvicorn app.main:app --reload`（在 backend 目录下）
- **THEN** FastAPI 服务在 8000 端口启动，`/health` 返回 200

#### Scenario: 前端启动
- **WHEN** 开发者运行 `npm run dev`（在 frontend 目录下）
- **THEN** Vite dev server 在 5173 端口启动，浏览器可访问首页

#### Scenario: Docker Compose 启动
- **WHEN** 开发者运行 `docker compose up`
- **THEN** Qdrant 和后端服务均启动

---

### Requirement: 课程管理（书架）
系统 SHALL 支持课程表导入和手动创建课程。

#### Scenario: CSV 课程表导入
- **WHEN** 用户上传包含课程名、教师、考试日期列的 CSV 文件
- **THEN** 系统为每行创建一门课程，返回创建的课程列表

#### Scenario: 手动创建课程
- **WHEN** 用户提交课程标题（必填）、教师（可选）、考试日期（可选）
- **THEN** 系统创建一门新课程，初始状态为 `empty`

#### Scenario: 查看课程列表
- **WHEN** 用户请求课程书架
- **THEN** 返回所有课程及其状态和考试倒计时

---

### Requirement: 材料上传与处理
系统 SHALL 接收课程材料并异步处理为可检索的文本块和向量。

#### Scenario: 上传 PDF 材料
- **WHEN** 用户向某课程上传 PDF 文件
- **THEN** 系统注册材料记录，状态变为 `processing`，触发异步解析

#### Scenario: 查询处理状态
- **WHEN** 用户查询材料的处理状态
- **THEN** 返回当前状态（processing / ready / failed）

#### Scenario: 处理完成
- **WHEN** 异步处理完成（解析→分块→嵌入→写入 Qdrant）
- **THEN** 材料状态变为 `ready`，课程状态若为首次则更新为 `ready`

#### Scenario: 处理失败降级
- **WHEN** 材料解析部分失败但存在可提取文本
- **THEN** 降级为基础文本 RAG，标记为降级处理

---

### Requirement: 课程骨架图
系统 SHALL 在材料处理完成后生成课程骨架。

#### Scenario: 骨架生成
- **WHEN** 课程的全部材料首次处理完成
- **THEN** 系统使用 LLM 从材料中提取章节、核心概念、难点和先修链路，生成 CourseSkeleton

#### Scenario: 查看骨架
- **WHEN** 用户请求课程骨架
- **THEN** 返回章节列表、核心概念、难点区域和先修链路

---

### Requirement: CRAG 课程问答
系统 SHALL 使用 CRAG 边界控制回答课程内问题。

#### Scenario: 高置信度回答
- **WHEN** 检索分数 >= 0.72
- **THEN** 正常回答并附带来源引用，`confidence_status` 为 `grounded`

#### Scenario: 低置信度谨慎回答
- **WHEN** 0.55 <= 检索分数 < 0.72
- **THEN** 扩展检索后谨慎回答，`confidence_status` 为 `ambiguous`

#### Scenario: 超范围拒答
- **WHEN** 检索分数 < 0.55
- **THEN** 返回拒答消息 "这个问题超出了[课程名]的范围，我不知道。"，`confidence_status` 为 `out_of_scope`

#### Scenario: 来源引用
- **WHEN** 回答非拒答
- **THEN** 必须包含至少一条 Citation，格式为 "来自 [文件名] · 第X部分"

---

### Requirement: 超级备考模式
系统 SHALL 生成复习计划并支持陪伴复习。

#### Scenario: 生成复习计划
- **WHEN** 用户为有考试日期的课程请求复习计划
- **THEN** 系统基于课程骨架和考试倒计时生成每日复习计划

#### Scenario: /btw 插话
- **WHEN** 用户在复习过程中发送 /btw 问题
- **THEN** 系统用 CRAG 回答该问题，并在回答后返回当前复习步骤

---

### Requirement: 前端书架页面
前端 SHALL 提供课程书架作为主页面。

#### Scenario: 书架展示
- **WHEN** 用户打开应用
- **THEN** 显示课程卡片网格，每个卡片展示课程名、教师、考试倒计时和状态

#### Scenario: 创建课程
- **WHEN** 用户点击创建课程按钮并填写表单
- **THEN** 新课程卡片出现在书架中

#### Scenario: 导入课程表
- **WHEN** 用户点击导入按钮并上传 CSV
- **THEN** 批量创建课程并刷新书架

---

### Requirement: 前端课程详情页
前端 SHALL 提供课程详情页包含材料上传、骨架图、问答和备考模式。

#### Scenario: 材料上传与状态
- **WHEN** 用户在课程详情页上传材料
- **THEN** 显示材料列表及各材料处理状态

#### Scenario: 骨架图可视化
- **WHEN** 课程骨架已生成
- **THEN** 以层级结构展示章节、核心概念和难点

#### Scenario: 课程问答
- **WHEN** 用户在问答区输入问题
- **THEN** 显示 AI 回答、来源引用和置信度状态

#### Scenario: 超级备考
- **WHEN** 用户进入备考模式
- **THEN** 展示复习计划日历和 /btw 插话入口

## MODIFIED Requirements

### Requirement: Docker Compose
Docker Compose SHALL 包含后端服务，而不仅仅是 Qdrant。
- 新增 `backend` 服务构建自 `backend/` 目录
- 后端服务依赖 Qdrant 服务
- 后端服务暴露 8000 端口
- 前端开发阶段使用 Vite dev server 代理 API 请求到后端

## REMOVED Requirements
无移除项。
