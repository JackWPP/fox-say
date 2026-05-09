# FoxSay Architecture

## MVP Architecture
```text
Frontend: Vite + React + TypeScript + Tailwind
Backend: FastAPI + uv + pyproject.toml
Vector store: Qdrant
Knowledge graph: NetworkX
Document parsing: Docling for structured documents, Marker for formula-heavy material
RAG: LightRAG-style incremental retrieval
Boundary control: CRAG gate plus system-prompt hard constraints
LLM: DeepSeek OpenAI-compatible API, deepseek-v4-flash
Deployment: Docker Compose
```

## Data Flow
```text
Course creation
  -> material registration
  -> async parsing
  -> text chunks and embeddings
  -> course-scoped Qdrant collection
  -> knowledge extraction
  -> NetworkX graph
  -> course skeleton
  -> course-bound chat and review plan
```

## Isolation Rules
- Use `course_id` as the primary partition key.
- Do not mix vectors, graph nodes, chat messages, or review plans across courses.
- Do not introduce multi-user ownership until the product explicitly leaves MVP scope.

## Failure Policy
- Parsing failures may degrade to basic text-based RAG if any extractable content exists.
- Retrieval failures must not fall back to model-only answers.
- Missing citations should block normal answers or mark them as invalid for debugging.

