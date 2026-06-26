# FoxSay Architecture

## MVP Architecture
```text
Frontend: Vite + React + TypeScript + Tailwind
Backend: FastAPI + Python + uv (pyproject.toml)
Vector store: Qdrant (course-scoped collections)
Knowledge representation: DMAP (文档结构图) + KC (Knowledge Component) + ChapterWiki
Wiki build: LangGraph 4 阶段 (Supervisor → Workers → Reducer → Reviewer)
RAG: 单层向量检索 + 三层混合检索 (macro=章节, micro=KC, all=合并) + CRAG 门控
Agent: 7 静态工具 + 4 动态 Skill (共 11 个) ReAct 循环, max 8 轮 (round 5 软性强制回答)
  静态: search_wiki, get_course_map, get_concept, get_chapter_outline, follow_prerequisite, get_source_content, get_review_plan
  Skill: generate_lecture, generate_quiz, generate_flashcards, show_concept_graph
Document parsing: pdfplumber (PDF), python-pptx (PPT), MinerU (PDF fallback, 当 pdfplumber 内容不足时)
Boundary control: CRAG gate (0.72/0.55 阈值) + system-prompt hard constraints
LLM: DeepSeek V4 Flash (生成端) + Qwen3.5-9B (Judge) + Qwen3-4b (批量轻活)
Deployment: Docker Compose (Qdrant container)
Pipeline: 7 步 (parsing → build_dmap → wiki_build → chunking → embedding → storing → skeleton_generating)
```

## Data Flow
```text
Course creation
  → material registration
  → async parsing (pdfplumber / python-pptx)
  → DMAP build (文档结构图)
  → Wiki build (4-stage LangGraph: Supervisor → Workers → Reducer → Reviewer)
  → KC extraction (Knowledge Component)
  → chunking
  → embedding (BGE-M3)
  → Qdrant storing (course-scoped collection)
  → skeleton generating
  → course-bound Agent chat (11 工具 ReAct: 7 静态 + 4 动态 Skill) and review plan
```

## Isolation Rules
- Use `course_id` as the primary partition key.
- Do not mix vectors, graph nodes, chat messages, or review plans across courses.
- Do not introduce multi-user ownership until the product explicitly leaves MVP scope.

## Failure Policy
- Parsing failures may degrade to basic text-based RAG if any extractable content exists.
- Retrieval failures must not fall back to model-only answers.
- Missing citations should block normal answers or mark them as invalid for debugging.

