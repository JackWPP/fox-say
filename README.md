# FoxSay

FoxSay is a course-scoped AI learning Copilot for Chinese university students. Its core promise is strict: answer only within the current course boundary, cite the uploaded course materials, and refuse questions that fall outside scope.

The current repository state is a structural scaffold. It defines project constraints, interfaces, and subsystem boundaries, but it does not implement a runnable product.

## Source Of Truth
- `AGENTS.md`: mandatory engineering and product constraints for future agents.
- `foxsay-prd.md`: product specification source document.
- `docs/crag-policy.md`: retrieval confidence and refusal policy.
- `docs/architecture.md`: MVP architecture boundaries.
- `docs/product-boundaries.md`: MVP and post-MVP scope.

## Scaffold
- `frontend/`: Vite + React + TypeScript + Tailwind structural placeholder.
- `backend/`: FastAPI-oriented Python package managed by `uv` and `pyproject.toml`.
- `infra/`: Docker Compose infrastructure placeholder, currently focused on Qdrant.
- `examples/env.example`: environment variable template with no real secrets.

## Current Non-Goals
- No installed dependencies.
- No lockfiles.
- No runnable API handlers.
- No runnable frontend pages.
- No real course data, embeddings, or vector-store content.

## Implementation Rule
Before implementing any feature, check `AGENTS.md` and keep the work course-scoped. Any retrieval, answer, skeleton, review plan, or `/btw` interaction must explicitly bind to `course_id`.

