# FoxSay

FoxSay is a course-scoped AI learning Copilot for Chinese university students. Its core promise is strict: answer only within the current course boundary, cite the uploaded course materials, and refuse questions that fall outside scope.

## Current State

FoxSay MVP is functional with NotebookLM-style three-column layout. It supports:

- Course creation (manual or CSV/Excel timetable import) with exam countdown
- Material upload (PDF, PPT, text) with async 7-step processing pipeline
- Course skeleton generation (from course_index, with LLM fallback)
- Course overview auto-generation with AI regenerate API
- Course-scoped CRAG chat with citation enforcement and source preview
- 11-tool ReAct Agent (7 static + 4 dynamic Skills: lecture/quiz/flashcards/concept graph)
- Knowledge graph visualization (reactflow + dagre, derived from ChapterWiki + KC)
- Course-level notes CRUD (save from chat/citations)
- Super exam mode (review plan + stateful study sessions + `/btw` interjection)
- Docker Compose deployment (frontend, backend, Qdrant)

## Quick Start

```bash
cp examples/env.example .env   # fill in DeepSeek API key and embedding API key
docker compose -f infra/docker-compose.yml up --build
# Frontend: http://localhost:3000
# Backend API docs: http://localhost:8000/docs
```

For local development:

```bash
# Backend
cd backend && uv sync && uv run uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

## Source Of Truth

- `AGENTS.md`: mandatory engineering and product constraints for future agents.
- `HANDOFF.md`: handoff document with current git state, architecture, and known issues.
- `docs/architecture.md`: MVP architecture overview (39 API endpoints, 11-tool Agent, testing).
- `docs/crag-policy.md`: retrieval confidence and refusal policy (0.72/0.55 thresholds).
- `docs/postmortem/verified.md`: verified external dependency identifiers (HEC-5).
- `docs/product-boundaries.md`: MVP and post-MVP scope.

## Project Structure

- `frontend/`: Vite + React + TypeScript + Tailwind (3 features: bookshelf, course, onboarding).
- `backend/`: FastAPI + Python managed by `uv` and `pyproject.toml` (17 services, 18 test files, 168 tests).
- `infra/`: Docker Compose (Qdrant, backend, frontend).
- `docs/`: Architecture, contracts, postmortem, gap analysis, roadmaps.
- `scripts/`: End-to-end test scripts (e2e_7tools, e2e_btw, playwright_frontend_audit).

## Implementation Rule

Before implementing any feature, check `AGENTS.md` and keep the work course-scoped. Any retrieval, answer, skeleton, review plan, or `/btw` interaction must explicitly bind to `course_id`.
