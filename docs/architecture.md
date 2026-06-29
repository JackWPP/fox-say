# FoxSay Architecture

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
Document parsing: pdfplumber (PDF), python-pptx (PPT), MinerU (PDF fallback, 当 pdfplumber 内容不足时)
Boundary control: CRAG 硬门控 (score < 0.55 代码级强制拒答) + 0.55-0.72 软引导 + system-prompt 硬约束
LLM: DeepSeek V4 Flash (生成端) + Qwen3.5-9B (Judge) + Qwen3-4b (批量轻活)
Deployment: Docker Compose (Qdrant container)
Pipeline: 7 步 (parsing → build_dmap → wiki_build → chunking → embedding → storing → skeleton_generating)
Knowledge graph: 从 ChapterWiki + KC 派生的关系图 (reactflow + dagre 布局, 非 Neo4j/NetworkX)
Notes: 课程级笔记 CRUD, 支持从聊天/引用保存
Review: 超级备考模式 (复习计划生成 + 状态机陪伴复习 + /btw 插话)
```

## Data Flow
```text
Course creation
  → material registration
  → async parsing (pdfplumber / python-pptx / MinerU fallback)
  → DMAP build (文档结构图)
  → Wiki build (4-stage LangGraph: Supervisor → Workers → Reducer → Reviewer)
  → KC extraction (Knowledge Component)
  → chunking
  → embedding (BGE-M3)
  → Qdrant storing (course-scoped collection)
  → skeleton generating (优先从 course_index 派生, fallback 到 LLM 生成)
  → course-bound Agent chat (11 工具 ReAct: 7 静态 + 4 动态 Skill) and review plan
```

## API Surface (39 endpoints)
```text
/courses                    课程 CRUD + import-timetable + build-wiki + kcs + chapter-wikis + course-index + summary/regenerate
/courses/{id}/materials     材料上传/列表/状态/重试/进度/source-preview
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
- MinerU fallback failures return (None, error_message) tuple — errors are visible, not silently swallowed (HEC-1).
- Retrieval failures must not fall back to model-only answers.
- CRAG score < 0.55: code-level forced refusal, LLM does not get to decide.
- Missing citations should block normal answers or mark them as invalid for debugging.

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
