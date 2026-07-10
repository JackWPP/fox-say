# FoxSay Architecture

## Knowledge System V2 Foundation (2026-07-11)

> The active request path below is still the legacy pipeline. V2 has only established its
> durable job foundation so far; it does **not** yet replace material upload, parsing,
> Qdrant writes, Wiki build, or the frontend status UI.

- `knowledge_jobs` is a separate SQLite-backed, course-scoped queue for V2 work. It has
  explicit revision, idempotency key, attempt, lease, error and token-budget fields.
- `source_fragments` is the V2 material evidence fact layer. Each fragment has an explicit
  `fragment_id`, course/material/revision scope, title path, source offsets and page/slide
  location; `EvidenceRef` resolves material claims through that ID rather than a filename.
- Materials now expose an explicit revision and content hash. Revision-guarded status/text
  writes reject stale jobs, so an old parse result cannot overwrite a newer upload.
- The V2 Qdrant source-fragment index uses deterministic UUID5 point IDs and type-scoped
  deletion, so a retry replaces only the affected material evidence rather than notes, terms
  or legacy chunks.
- The current V2 job types are `index_material` and `compile_course`. Store operations can
  atomically enqueue, claim, reclaim an expired lease, complete, fail and requeue a job.
- `KnowledgeJobWorker` is a controlled, single-worker consumer with injected handlers and a
  managed lease heartbeat. It is not wired into the FastAPI lifespan or HTTP API yet; the next
  V2 milestone connects it to material revisions. Legacy in-process `asyncio.create_task()`
  work has not yet been removed.
- The target evidence-first model, incremental revision policy and migration sequence are in
  [knowledge-system-v2-implementation-plan.md](knowledge-system-v2-implementation-plan.md).

## MVP Architecture
```text
Frontend: Vite + React + TypeScript + Tailwind
  Layout: NotebookLM 风格三栏 (SourcesPanel | ChatWorkspace | StudioPanel)
  Features: 书架, 课程详情(聊天/材料/骨架/知识图谱/笔记/复习), Onboarding
Backend: FastAPI + Python + uv (pyproject.toml)
Vector store: Qdrant (course-scoped collections)
Knowledge representation: DMAP (文档结构图) + KC (Knowledge Component) + ChapterWiki
Wiki build: LangGraph 4 阶段 (Supervisor → Workers → Reducer → Reviewer)
RAG: 单层向量检索 + 三层混合检索 (macro=章节, micro=KC, all=合并) + CRAG 门控
Agent: 7 静态工具 + 4 动态 Skill (共 11 个) ReAct 循环, max 8 轮 (round 5 软性强制回答)
  静态: search_wiki, get_course_map, get_concept, get_chapter_outline, follow_prerequisite, get_source_content, get_review_plan
  Skill: generate_lecture, generate_quiz, generate_flashcards, show_concept_graph
Document parsing: MinerU V4/V1 hybrid (PRIMARY, 1000 pages/day quota) → Docling (电子版 PDF fallback) → pdfplumber (lightweight fallback) → python-pptx (PPT fallback) → MarkItDown (XLSX only)
  PDF 路由: PyMuPDF 探测电子/扫描件 → MinerU V4 primary → Docling/pdfplumber fallback
  Office 路由: DOCX/DOC/PPTX/PPT → MinerU V4 (native support) → MarkItDown (Word) / python-pptx (PPT) fallback
  XLSX 路由: MarkItDown only (MinerU V4 不支持 XLSX)
  支持格式: PDF / PPT / Word / HTML / 图片(PNG/JPG) / 文本(TXT/MD) / XLSX
  归一化: NormalizationEngine (页面锚定 + 表格保护 + 公式对齐 + 全局编号)
  切块: LangChain 语义切块 (MarkdownHeaderTextSplitter + 表格不可分割 + 上下文标题 prepend)
  批量上传: POST /materials/batch 最多 15 个文件, 后端 asyncio.Semaphore(3) 控制解析并发
Boundary control: CRAG 透明门控 (score < 0.55 允许补充回答, 强制标注 answer_source: "supplementary" + 声明课程材料未覆盖) + 0.55-0.72 软引导 + system-prompt 硬约束
LLM: DeepSeek V4 Flash (生成端) + Qwen3.5-9B (Judge) + Qwen3-4b (批量轻活)
VLM parser service: SiliconFlow `Qwen/Qwen3.6-27B` (独立 `VLM_*` 配置、data-URI 图片载荷、关闭 thinking、可配输出 token 上限)；legacy 图片路由当前仍使用 MinerU，尚未接入该服务
Deployment: Docker Compose (Qdrant container)
Pipeline: 7 步 (parsing[路由+归一化] → build_dmap → wiki_build → chunking[语义切块] → embedding → storing → skeleton_generating)
  解析子步: 文件类型路由 → MinerU V4/V1 primary (或 fallback 链) → NormalizationEngine 归一化 → extracted_assets 入库
  并发: asyncio.Semaphore(3) 限制同时解析的文件数
  持久化: materials.parsed_text 列存储解析文本, 进程重启不丢失 (course-level wiki build 可重新触发)
  超时保护: processing > 15min 自动标记 failed (批量上传排队更久, 阈值从 5min 提到 15min)
Knowledge graph: 从 ChapterWiki + KC 派生的关系图 (reactflow + dagre 布局, 非 Neo4j/NetworkX)
Notes: 课程级笔记 CRUD, 支持从聊天/引用保存
Review: 超级备考模式 (复习计划生成 + 状态机陪伴复习 + /btw 插话)
```

## Data Flow
```text
Course creation
  → material registration (单文件 POST /materials 或批量 POST /materials/batch 最多15个)
  → async parsing 路由 + 多层 fallback
    · PDF: PyMuPDF 探测类型 → MinerU V4 primary → Docling/pdfplumber fallback
    · Office (DOCX/DOC/PPTX/PPT): MinerU V4 primary → MarkItDown/python-pptx fallback
    · XLSX: MarkItDown only
    · 图片: MinerU V4/V1 为当前路由；独立配置的 VLM parser 已实现但尚未接入此 legacy 路由
    · 归一化: NormalizationEngine (页面锚定 + 表格保护 + 公式对齐 + 全局编号)
    · extracted_assets 写入 SQLite
    · 并发控制: asyncio.Semaphore(3) 限制同时解析的文件数
    · 持久化: 解析文本写入 materials.parsed_text 列 (进程重启不丢失)
  → DMAP build (文档结构图)
  → Wiki build (4-stage LangGraph: Supervisor → Workers → Reducer → Reviewer)
  → KC extraction (Knowledge Component)
  → semantic chunking (LangChain MarkdownHeaderTextSplitter + 表格保护)
  → embedding (BGE-M3)
  → Qdrant storing (course-scoped collection, chunk payload 含 heading_path)
  → skeleton generating (优先从 course_index 派生, fallback 到 LLM 生成)
  → course-bound Agent chat (11 工具 ReAct: 7 静态 + 4 动态 Skill) and review plan
```

## API Surface (40 endpoints)
```text
/courses                    课程 CRUD + import-timetable + build-wiki + kcs + chapter-wikis + course-index + summary/regenerate
/courses/{id}/materials     材料上传(单文件 + /batch 批量最多15个)/列表/状态/重试/进度/source-preview
/courses/{id}/chat          Agent SSE stream + sessions + history
/courses/{id}/skeleton      骨架图查询
/courses/{id}/review-plan   复习计划生成
/courses/{id}/review-session 超级备考状态机 (start/advance/generate-step/progress/complete)
/courses/{id}/btw           /btw 插话
/courses/{id}/notes         笔记 CRUD
/courses/{id}/knowledge-graph 知识图谱 + 节点详情
/events                     SSE 推送 (material_processed / skeleton_ready)
/settings                   设置 + 模式切换 + onboarding
/health                     健康检查
```

## Isolation Rules
- Use `course_id` as the primary partition key.
- Do not mix vectors, graph nodes, chat messages, or review plans across courses.
- Do not introduce multi-user ownership until the product explicitly leaves MVP scope.

## Failure Policy
- Parsing failures may degrade to basic text-based RAG if any extractable content exists.
- MinerU V4/V1 是 PRIMARY 解析器, 所有 PDF 和 Office 文档优先走 MinerU。
- MinerU 失败时回退: PDF → Docling → pdfplumber; Office → MarkItDown/python-pptx。
- MinerU V4 有 daily quota (1000 pages/day), 额度耗尽时自动降级到 V1 或 fallback 链。
- MinerU fallback failures return (None, error_message) tuple — errors are visible, not silently swallowed (HEC-1).
- Retrieval failures must not fall back to model-only answers.
- CRAG score < 0.55: 不再硬拒答。允许基于通用知识补充回答, 但必须强制标注 `answer_source: "supplementary"` + 声明"课程材料中未覆盖此内容, 以下为通用理解, 建议对照教材确认"。
- Missing citations should block normal answers or mark them as invalid for debugging.
- 批量上传中不支持的文件类型会被跳过并记录日志 (HEC-1), 不阻塞其他文件。

## Frontend Architecture
```text
features/
  bookshelf/     书架页 (课程列表 + 导入课程表 + 创建课程)
  course/        课程详情 (24 文件)
    ChatWorkspace.tsx     统一聊天工作区 (课程概述 + 对话 + 工具调用)
    SourcesPanel.tsx      左侧来源面板 (材料选择 + 进度)
    StudioPanel.tsx       右侧 Studio 面板 (课程详情 + 笔记 + 复习入口)
    KnowledgeGraphTab.tsx 知识图谱 (reactflow + dagre)
    ReviewTab.tsx         超级备考模式
  onboarding/   3 步引导
```

## Testing
- 168 tests (18 files) covering: API endpoints, Agent loop, query tools, wiki builder, DMAP, Merkle, CRAG, PR0 contracts, eval framework, prerequisites alignment.
- End-to-end scripts in `scripts/` (e2e_7tools, e2e_btw, e2e_errors, e2e_incremental, e2e_pdf, playwright_frontend_audit).
