# FoxSay

FoxSay is a course-scoped AI learning Copilot for Chinese university students. Its core promise is strict: answer only within the current course boundary, cite the uploaded course materials, and refuse questions that fall outside scope.

## Current State

FoxSay MVP is functional. It supports:

- Course creation (manual or CSV/Excel timetable import)
- Material upload (PDF, PPT, text) with async processing pipeline
- Course skeleton generation from materials
- Course-scoped CRAG chat with citation enforcement
- Review plan generation with "super exam mode"
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
- `foxsay-prd.md`: product specification source document.
- `docs/crag-policy.md`: retrieval confidence and refusal policy.
- `docs/architecture.md`: MVP architecture boundaries.
- `docs/product-boundaries.md`: MVP and post-MVP scope.

## Project Structure

- `frontend/`: Vite + React + TypeScript + Tailwind.
- `backend/`: FastAPI + Python managed by `uv` and `pyproject.toml`.
- `infra/`: Docker Compose (Qdrant, backend, frontend).
- `examples/env.example`: environment variable template.

## Implementation Rule

Before implementing any feature, check `AGENTS.md` and keep the work course-scoped. Any retrieval, answer, skeleton, review plan, or `/btw` interaction must explicitly bind to `course_id`.
