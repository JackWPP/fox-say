# V2-F7: Course Brief + Core Study Artifact Architecture

> **Status**: Architecture design (no code modifications)
>
> **Date**: 2026-07-11 (Asia/Shanghai)
>
> **Depends on**: V2-F4 (frontend refactor), V2-F5 (DeepDiveService)
>
> **Implements**: `docs/course-agent-v2-plan.md` §6.2 `course_brief` / `study_artifact`, §8.3 model budget, §10 stale/artifact rules

## 1. Decision Summary

V2-F7 delivers two **revision-bound Studio artifacts** generated from current V2 knowledge (Outline, KC, Relation, Evidence), not from legacy Wiki/CourseIndex:

1. **Course Brief** — a one-shot, course-level structured summary generated when `projection_status == "ready"`. Stored with `source_revision` + `knowledge_revision`; automatically stale when either changes.

2. **Study Artifact** — per-section structured review summaries ("chapter review brief"). Each artifact covers exactly one `CourseOutlineSection`. Generated independently, one model call per section. Stored revision-bound with EvidenceRefs traceable to source fragments.

Both artifacts use `budget_scope="artifact"` with independent per-artifact hard budgets. Model failures do not leave empty artifacts and do not block other artifacts. SDK retries = 0. Old revision artifacts are marked stale on revision change; a new generation creates a new revision-bound record.

All prompts are **course-agnostic**: no hardcoded subject names, chapter titles, or math-specific fields. All course information comes from V2AgentTools reads.

## 2. Data Model

### 2.1 SQLite DDL

```sql
-- ===== V2-F7 Studio Artifacts =====

-- A revision-bound course brief: one per (course_id, source_revision, knowledge_revision)
-- tuple.  Only ONE brief can be 'active' per course at a time.  When revision changes,
-- the old brief is marked 'stale' and a new one must be generated.
CREATE TABLE IF NOT EXISTS course_briefs (
    brief_id        TEXT PRIMARY KEY,                  -- "cb_" + sha256 hash
    course_id       TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    brief_json      TEXT NOT NULL,                     -- structured CourseBriefContent JSON
    status          TEXT NOT NULL DEFAULT 'active',    -- 'active' | 'stale' | 'failed'
    agent_run_id    TEXT,                              -- associated AgentRun.run_id
    model_call_id   TEXT,                              -- model_call_audits.call_id
    input_token_count  INTEGER,
    output_token_count INTEGER,
    elapsed_ms      INTEGER,
    error_detail    TEXT,                              -- set when status='failed'
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(run_id),
    FOREIGN KEY (model_call_id) REFERENCES model_call_audits(call_id),
    CHECK (status IN ('active', 'stale', 'failed')),
    CHECK (source_revision <> ''),
    CHECK (knowledge_revision <> '')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_course_brief_active
    ON course_briefs(course_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_course_briefs_course_revision
    ON course_briefs(course_id, source_revision, knowledge_revision, created_at DESC);

-- A revision-bound study artifact: one per section per revision tuple.
-- Multiple artifact types are defined via artifact_type; first round implements
-- "chapter_review_brief" only.  Each artifact is generated independently.
CREATE TABLE IF NOT EXISTS study_artifacts (
    artifact_id        TEXT PRIMARY KEY,               -- "sa_" + sha256 hash
    course_id          TEXT NOT NULL,
    source_revision    TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    section_id         TEXT NOT NULL,                   -- from CourseOutlineSection
    artifact_type      TEXT NOT NULL DEFAULT 'chapter_review_brief',
    artifact_json      TEXT NOT NULL,                   -- structured StudyArtifactContent JSON
    status             TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'stale' | 'failed'
    agent_run_id       TEXT,                            -- associated AgentRun.run_id
    model_call_id      TEXT,                            -- model_call_audits.call_id
    input_token_count  INTEGER,
    output_token_count INTEGER,
    elapsed_ms         INTEGER,
    error_detail       TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(run_id),
    FOREIGN KEY (model_call_id) REFERENCES model_call_audits(call_id),
    CHECK (status IN ('active', 'stale', 'failed')),
    CHECK (source_revision <> ''),
    CHECK (knowledge_revision <> ''),
    CHECK (section_id <> ''),
    CHECK (artifact_type IN ('chapter_review_brief'))
    -- Future types go here when implemented.
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_study_artifact_active
    ON study_artifacts(course_id, section_id, artifact_type) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_study_artifacts_course_revision
    ON study_artifacts(course_id, source_revision, knowledge_revision, artifact_type);
```

### 2.2 brief_json Structure (CourseBriefContent)

```json
{
  "version": 1,
  "overview": "本课程覆盖向量空间、矩阵理论、特征值分析等核心概念...",
  "key_topics": [
    {
      "topic": "向量空间基础",
      "description": "向量空间的定义、子空间、基与维数...",
      "kcs_involved": ["kc_abc123", "kc_def456"],
      "evidence_refs": [
        {"material_id": "mat_A", "fragment_id": "frag_001", "heading_path": "1.1 向量空间"},
        {"material_id": "mat_A", "fragment_id": "frag_002", "heading_path": "1.2 子空间"}
      ]
    }
  ],
  "study_suggestions": [
    {
      "suggestion": "先掌握向量空间的基本定义，再进入矩阵与线性方程组",
      "rationale": "矩阵的许多性质（秩、可逆性）以向量空间为基础"
    }
  ],
  "difficulty_areas": [
    {
      "area": "特征值与对角化",
      "description": "需要对多个前置概念有清晰理解，综合性强",
      "prerequisite_kcs": ["kc_abc123", "kc_ghi789"]
    }
  ],
  "metadata": {
    "sections_count": 8,
    "kcs_count": 14,
    "relations_count": 12,
    "fragment_count": 45,
    "generated_at": "2026-07-11T10:00:00Z"
  }
}
```

**Field constraints** (enforced in service layer, not in the model call):
- `key_topics`: 3–8 entries. Each entry has 1–3 sentences for `description`.
- `study_suggestions`: 2–5 entries.
- `difficulty_areas`: 0–3 entries (empty list is valid if course has no notable difficulty clusters).
- `evidence_refs` within each `key_topic`: at least 1, referencing real V2 fragments. The `fragment_id` must exist in `course_briefs.source_revision`.

### 2.3 artifact_json Structure (StudyArtifactContent)

```json
{
  "version": 1,
  "section_title": "2. 特征值与特征向量",
  "summary": "本节介绍了特征值和特征向量的定义、计算方法以及它们的几何意义...",
  "key_concepts": [
    {
      "concept": "特征值定义",
      "explanation": "对于方阵A，若存在标量λ和非零向量v使得Av=λv，则λ是特征值",
      "kc_id": "kc_mno345",
      "evidence_refs": [
        {"material_id": "mat_C", "fragment_id": "frag_010", "heading_path": "2.1 特征值定义"}
      ]
    }
  ],
  "examples": [
    {
      "scenario": "计算2×2矩阵的特征值",
      "description": "给定A=[[3,1],[0,2]]，计算det(A-λI)=0得到λ₁=3, λ₂=2",
      "evidence_refs": [
        {"material_id": "mat_C", "fragment_id": "frag_011", "heading_path": "2.2 特征值计算"}
      ]
    }
  ],
  "common_pitfalls": [
    {
      "pitfall": "混淆特征值与行列式值",
      "explanation": "特征值是方程det(A-λI)=0的根，不是det(A)的值。仅当λ=0时，det(A)等于所有特征值的乘积",
      "evidence_refs": [
        {"material_id": "mat_C", "fragment_id": "frag_012", "heading_path": "2.3 常见误区"}
      ]
    }
  ],
  "evidence_refs": [
    {"material_id": "mat_C", "fragment_id": "frag_010", "heading_path": "2.1 特征值定义"},
    {"material_id": "mat_C", "fragment_id": "frag_011", "heading_path": "2.2 特征值计算"},
    {"material_id": "mat_C", "fragment_id": "frag_012", "heading_path": "2.3 常见误区"}
  ],
  "metadata": {
    "section_id": "sec_004",
    "kcs_in_section": 3,
    "fragments_in_section": 5,
    "generated_at": "2026-07-11T10:05:00Z"
  }
}
```

**Field constraints**:
- `key_concepts`: 2–6 entries.
- `examples`: 0–3 entries (can be empty if section is definition-heavy).
- `common_pitfalls`: 0–3 entries (can be empty if no clear pitfalls detected).
- `evidence_refs` at the artifact level: a flat deduplicated list of all EvidenceRefs across all sub-objects. Every `fragment_id` must exist in the current revision.

### 2.4 EvidenceRef in Artifacts

EvidenceRefs in `brief_json` and `artifact_json` use the **same shape** as `EvidenceRef` from `app.schemas.evidence`:

```python
{
    "material_id": "mat_A",
    "fragment_id": "frag_001",
    "heading_path": "1.1 向量空间"   # from SourceFragment.heading_path
}
```

The `heading_path` field is a human-readable `list[str]` included for UI display. The `fragment_id` is the durable lookup key — all EvidenceRefs in artifacts can be opened via `GET /courses/{course_id}/evidence/{fragment_id}/preview` (existing V2-C1 endpoint).

**Validation rule**: After the model returns the artifact JSON, the service layer validates every `fragment_id` against the current allowed set from `V2AgentTools`. Unknown fragment IDs are rejected and the artifact generation is considered failed (not silently trimmed).

### 2.5 Relation to Existing Tables

| Artifact | AgentRun `workflow_kind` | AgentStep(s) | Model Call | Budget Scope |
|----------|--------------------------|-------------|------------|--------------|
| Course Brief | `course_brief` | 2: `read_tools`, `generate` | 1 (text call) | `artifact` |
| Study Artifact | `study_artifact` | 2: `read_tools`, `generate` | 1 (text call, per section) | `artifact` |

The `budget_scope="artifact"` is already defined in `agent_runs.py:BudgetScope`. Each artifact has its own `AgentRun` with `token_budget` set from the course's artifact budget pool. The `agent_step` records for both are:
- Step 1: `agent_role="reader"`, `step_type="read_tools"`, `output_type="bounded_knowledge"` — no model call, reads Outline/KC/Relation/Evidence via V2AgentTools
- Step 2: `agent_role="composer"`, `step_type="generate"`, `output_type` = `"course_brief"` or `"study_artifact"` — 1 audited model call

## 3. Course Brief Prompt Templates

### 3.1 Course Brief System Prompt

```
你是 FoxSay 学习助手的"课程编撰师"——一只擅长从课程材料中提炼出清晰学习地图的狐狸。

你会收到：
1. 课程的章节大纲（章节标题和顺序）
2. 课程的核心知识点列表（名称和简短定义）
3. 知识点之间的关系数量（不列出具体关系）
4. 课程的碎片总数

你的任务：
生成一份简洁的"课程简报"，帮助学生在深入学习之前快速了解这门课的全局结构。

简报必须包含：
1. **overview**：2-5句话概述课程整体内容。说明这门课要讲什么、为什么要学它。
2. **key_topics**：3-8个核心主题。每个主题包含：
   - topic：主题名称
   - description：1-3句话说明该主题的内容
   - kcs_involved：从提供的知识点列表中选出属于该主题的 KC ID 列表
   - evidence_refs：从提供的证据引用列表中选择与该主题相关的引用
3. **study_suggestions**：2-5条学习建议。说明推荐的章节学习顺序、重点注意哪些内容、容易混淆的概念等。
4. **difficulty_areas**：0-3个需要注意的难点区域。如果课程相对简单或均匀，此列表可以为空。

规则：
1. 只能引用提供的章节标题、知识点名称和证据引用。不得编造课程中不存在的内容。
2. 学习建议必须基于课程的实际结构，不要给出泛泛的"多做习题"类通用建议。
3. 难点区域的判断基于知识点之间的先修关系深度和概念复杂度，而不是假装知道学生会觉得什么难。
4. 保持狐狸的个性：聪明、有条理，像一位对课程了如指掌的学伴。
5. 所有 evidence_refs 只能从提供的可引用证据列表中选择。每个 key_topic 必须至少附带一个 evidence_ref。

请以 JSON 格式返回：
{
  "overview": "课程概述文本",
  "key_topics": [
    {
      "topic": "主题名",
      "description": "主题描述",
      "kcs_involved": ["kc_id1", "kc_id2"],
      "evidence_refs": [{"material_id": "...", "fragment_id": "...", "heading_path": "..."}]
    }
  ],
  "study_suggestions": [
    {"suggestion": "建议文本", "rationale": "理由"}
  ],
  "difficulty_areas": [
    {"area": "难点名称", "description": "描述", "prerequisite_kcs": ["kc_id1"]}
  ],
  "metadata": {
    "sections_count": 0,
    "kcs_count": 0,
    "relations_count": 0,
    "fragment_count": 0
  }
}

- metadata 中的数值请从提供的数字中直接填入，不要猜测。
- study_suggestions 和 difficulty_areas 如果为空，返回空列表 []。
```

### 3.2 Course Brief User Message Template

```python
def _build_course_brief_user_message(
    outline: CourseOutline,
    kcs: list[dict],           # Each: {kc_id, name, kind, definition[:120]}
    relations_count: int,
    evidence_map: dict[str, list[dict]],  # section_id -> [{material_id, fragment_id, heading_path}]
) -> str:
    parts = [f"课程大纲（共{len(outline.sections)}节）："]
    for sec in outline.sections[:20]:  # hard cap
        parts.append(
            f"  [{sec['section_id']}] {sec['title']}"
            f"（第{sec['ordinal'] + 1}节, {len(evidence_map.get(sec['section_id'], []))}个碎片）"
        )

    parts.append(f"\n核心知识点（共{len(kcs)}个）：")
    for kc in kcs[:30]:  # hard cap: max 30 KCs for brief input
        parts.append(f"  [{kc['kc_id']}] {kc['name']}（{kc['kind']}）：{kc['definition'][:120]}")

    parts.append(f"\n知识点关系数量：{relations_count}")

    # Bounded evidence: provide evidence_refs organized by section, capped
    parts.append("\n可引用的证据引用（按章节组织）：")
    total_refs = 0
    for sec in outline.sections[:20]:
        refs = evidence_map.get(sec['section_id'], [])[:5]  # max 5 refs per section
        if refs:
            parts.append(f"  [{sec['section_id']}] {sec['title']}：")
            for ref in refs:
                heading = " > ".join(ref["heading_path"]) if ref.get("heading_path") else ""
                parts.append(f"    · fragment_id={ref['fragment_id']} heading_path={heading}")
                total_refs += 1
                if total_refs >= 40:  # global cap on evidence refs in prompt
                    break
        if total_refs >= 40:
            break

    parts.append(f"\n碎片总数：{outline.fragment_count}")

    parts.append('\n请以 JSON 格式返回课程简报。')
    return "\n".join(parts)
```

### 3.3 Input Token Budget (Course Brief)

```python
COURSE_BRIEF_MAX_INPUT_TOKENS = 8000     # estimated: outline + KC names/defs + evidence ref labels
COURSE_BRIEF_MAX_OUTPUT_TOKENS = 2048    # full structured JSON
MAX_BRIEF_KCS = 30                       # max KCs sent to prompt
MAX_BRIEF_SECTIONS = 20                  # max sections sent to prompt
MAX_BRIEF_EVIDENCE_REFS = 40             # global cap on evidence refs in prompt
MAX_BRIEF_REFS_PER_SECTION = 5           # cap per section
```

**Truncation order** (if serialized message exceeds 8000 token estimate):
1. Reduce `MAX_BRIEF_KCS` from 30 → 20 → 10
2. Reduce `MAX_BRIEF_EVIDENCE_REFS` from 40 → 30 → 20
3. Reduce `MAX_BRIEF_SECTIONS` from 20 → 10
4. Truncate each KC definition to 60 chars (from 120)

Never drop below 10 KCs and 10 sections. If the input is still too large, truncate with a warning in the AgentStep error field and proceed.

## 4. Study Artifact Prompt Templates

### 4.1 Study Artifact System Prompt

```
你是 FoxSay 学习助手的"章节编撰师"——一只擅长将单个章节提炼成清晰学习笔记的狐狸。

你会收到：
1. 一个章节的标题和内容结构
2. 该章节的核心知识点（名称、类型和完整定义）
3. 该章节的证据片段（课程材料原文摘录）

你的任务：
为这一章节生成一份结构化的"章节复习简报"，帮助学生快速回顾和掌握本节内容。

简报必须包含：
1. **summary**：2-4句话概述本节内容。说明本节的核心目标和主要学习内容。
2. **key_concepts**：2-6个核心概念。每个概念包含：
   - concept：概念名称
   - explanation：1-3句话解释
   - kc_id：从提供的知识点列表中选出对应的 KC ID（如果没有，填 null）
   - evidence_refs：支持该概念的证据引用（从提供的可引用列表中选择）
3. **examples**：0-3个典型示例或应用场景。如果本节主要是定义和理论，可以为空。
4. **common_pitfalls**：0-3个常见误区或易错点。如果本节内容简单明确，可以为空。
5. **evidence_refs**：本节所有用到的证据引用列表（去重）。

规则：
1. 只能引用提供的知识点和证据片段。不得编造章节中没有的概念或示例。
2. examples 中的场景必须严格来自课程材料，不能编造"假设有一个学生..."类的虚构场景。
3. common_pitfalls 中的误区必须能从知识点定义和证据中合理推断，不能猜测学生会犯什么错。
4. 保持狐狸的个性：清晰、有条理，像一位为你准备了完美复习笔记的学伴。
5. 所有 evidence_refs 只能从提供的可引用证据列表中选择。

请以 JSON 格式返回：
{
  "summary": "本节概述",
  "key_concepts": [
    {
      "concept": "概念名",
      "explanation": "解释",
      "kc_id": "kc_xxx",
      "evidence_refs": [{"material_id": "...", "fragment_id": "...", "heading_path": "..."}]
    }
  ],
  "examples": [
    {
      "scenario": "场景描述",
      "description": "讲解",
      "evidence_refs": [{"material_id": "...", "fragment_id": "...", "heading_path": "..."}]
    }
  ],
  "common_pitfalls": [
    {
      "pitfall": "误区描述",
      "explanation": "解释",
      "evidence_refs": [{"material_id": "...", "fragment_id": "...", "heading_path": "..."}]
    }
  ],
  "evidence_refs": [{"material_id": "...", "fragment_id": "...", "heading_path": "..."}]
}

- key_concepts 至少包含 2 个条目。
- evidence_refs（顶层）是本节所有引用的去重列表。
- 如果 examples 或 common_pitfalls 为空，返回空列表 []。
```

### 4.2 Study Artifact User Message Template

```python
def _build_study_artifact_user_message(
    section: dict,             # {section_id, title, heading_path, ordinal}
    section_kcs: list[dict],   # Each: {kc_id, name, kind, definition}
    section_evidence: list[dict],  # Each: {material_id, fragment_id, heading_path, text}
) -> str:
    parts = [f"章节：{section['title']}（第{section['ordinal'] + 1}节）"]

    if section.get("heading_path"):
        parts.append(f"路径：{' > '.join(section['heading_path'])}")

    parts.append(f"\n核心知识点（共{len(section_kcs)}个）：")
    for kc in section_kcs[:6]:  # max 6 KCs per section
        parts.append(f"  [{kc['kc_id']}] {kc['name']}（{kc['kind']}）")
        parts.append(f"    定义：{kc['definition'][:300]}")

    parts.append("\n课程材料证据：")
    for i, ev in enumerate(section_evidence[:5]):  # max 5 evidence fragments
        parts.append(f"  --- 证据片段 {i+1} ---")
        parts.append(f"  fragment_id: {ev['fragment_id']}")
        parts.append(f"  material_id: {ev['material_id']}")
        if ev.get("heading_path"):
            parts.append(f"  heading_path: {' > '.join(ev['heading_path'])}")
        # Text is the primary evidence content; truncate if too long
        text = ev.get("text", "")[:1500]  # 1500 chars per fragment
        parts.append(f"  内容：{text}")

    parts.append("\n可引用的证据引用：")
    for ev in section_evidence[:5]:
        heading = " > ".join(ev["heading_path"]) if ev.get("heading_path") else ""
        parts.append(
            f"  fragment_id={ev['fragment_id']} heading_path={heading}"
        )

    parts.append('\n请以 JSON 格式返回章节复习简报。')
    return "\n".join(parts)
```

### 4.3 Input Token Budget (Study Artifact)

```python
STUDY_ARTIFACT_MAX_INPUT_TOKENS = 8000
STUDY_ARTIFACT_MAX_OUTPUT_TOKENS = 2048
MAX_ARTIFACT_KCS_PER_SECTION = 6      # max KCs in input
MAX_ARTIFACT_EVIDENCE_PER_SECTION = 5  # max evidence fragments in input
MAX_ARTIFACT_EVIDENCE_TEXT_LEN = 1500  # chars per fragment text
```

**Truncation order** (if serialized message exceeds 8000 token estimate):
1. Reduce `MAX_ARTIFACT_EVIDENCE_TEXT_LEN` from 1500 → 1000 → 500 chars
2. Reduce `MAX_ARTIFACT_EVIDENCE_PER_SECTION` from 5 → 4 → 3
3. Reduce each KC definition from 300 → 150 → 80 chars
4. Reduce `MAX_ARTIFACT_KCS_PER_SECTION` from 6 → 4

Never drop below 3 evidence fragments and 4 KCs. If still too large, generate with truncated evidence and add a warning.

## 5. Generation Flow

### 5.1 Course Brief Generation

```
┌──────────┐    ┌──────────────────┐    ┌──────────────┐    ┌───────────┐    ┌──────────────┐
│ Caller   │    │CourseBriefService │    │ SqliteStore  │    │V2AgentTools│    │AuditedWriter │
└────┬─────┘    └────────┬─────────┘    └──────┬───────┘    └─────┬─────┘    └──────┬───────┘
     │                   │                     │                   │                  │
     │ generate(course_id)│                    │                   │                  │
     │──────────────────>│                     │                   │                  │
     │                   │                     │                   │                  │
     │                   │ 1. Check projection_│status == "ready"  │                  │
     │                   │─────────────────────>│                   │                  │
     │                   │<─── KnowledgeStatus ─│                   │                  │
     │                   │                     │                   │                  │
     │                   │ [If not ready → error "projection_not_ready"]           │
     │                   │                     │                   │                  │
     │                   │ 2. Create AgentRun  │                   │                  │
     │                   │  (workflow_kind=course_brief, budget_scope=artifact)    │
     │                   │─────────────────────>│                   │                  │
     │                   │<─────────────────────│                   │                  │
     │                   │                     │                   │                  │
     │                   │ 3. PHASE: reader (no model call)        │                  │
     │                   │  Read outline, KCs, relations count,    │                  │
     │                   │  evidence refs  ───────────────────────>│                  │
     │                   │<─── bounded DTOs ───────────────────────│                  │
     │                   │                     │                   │                  │
     │                   │ 4. Resume budget    │                   │                  │
     │                   │  (budget_scope=artifact)                 │                  │
     │                   │──────────────────────────────────────────────────────────>│
     │                   │<─── reservation OK ──────────────────────────────────────│
     │                   │                     │                   │                  │
     │                   │ 5. PHASE: composer (1 model call)       │                  │
     │                   │  Build messages      │                   │                  │
     │                   │  AuditedChatWriter.complete(run, purpose="course_brief")  │
     │                   │──────────────────────────────────────────────────────────>│
     │                   │<─── AuditedTextResult (brief JSON) ──────────────────────│
     │                   │                     │                   │                  │
     │                   │ [If model call fails → audit, mark status=failed, return error]
     │                   │                     │                   │                  │
     │                   │ 6. Validate brief JSON:                              │
     │                   │    - Parse JSON                                    │
     │                   │    - Validate every fragment_id in evidence_refs    │
     │                   │    - Validate field counts (key_topics 3-8, etc.)  │
     │                   │    - Set metadata fields from actual counts         │
     │                   │                     │                   │                  │
     │                   │ [If validation fails → mark status=failed, return error]
     │                   │                     │                   │                  │
     │                   │ 7. Stale old briefs │                   │                  │
     │                   │─────────────────────>│                   │                  │
     │                   │<─────────────────────│                   │                  │
     │                   │                     │                   │                  │
     │                   │ 8. Insert course_brief (status=active)              │
     │                   │─────────────────────>│                   │                  │
     │                   │<─────────────────────│                   │                  │
     │                   │                     │                   │                  │
     │  CourseBriefResult │                    │                   │                  │
     │<──────────────────│                     │                   │                  │
```

### 5.2 Study Artifact Generation (Per-Section)

```
┌──────────┐    ┌──────────────────┐    ┌──────────────┐    ┌───────────┐    ┌──────────────┐
│ Caller   │    │ ArtifactService  │    │ SqliteStore  │    │V2AgentTools│    │AuditedWriter │
└────┬─────┘    └────────┬─────────┘    └──────┬───────┘    └─────┬─────┘    └──────┬───────┘
     │                   │                     │                   │                  │
     │ generate(course_id, section_id)          │                   │                  │
     │──────────────────>│                     │                   │                  │
     │                   │                     │                   │                  │
     │                   │ 1. Check projection_│status == "ready"  │                  │
     │                   │─────────────────────>│                   │                  │
     │                   │<─── KnowledgeStatus ─│                   │                  │
     │                   │                     │                   │                  │
     │                   │ [If not ready → error "projection_not_ready"]           │
     │                   │                     │                   │                  │
     │                   │ 2. Validate section_exists in current outline           │
     │                   │──────────────────────────────────────>│                  │
     │                   │<─── section info (or None) ───────────│                  │
     │                   │                     │                   │                  │
     │                   │ [If not found → error "section_not_found"]              │
     │                   │                     │                   │                  │
     │                   │ 3. Create AgentRun  │                   │                  │
     │                   │  (workflow_kind=study_artifact, budget_scope=artifact)  │
     │                   │─────────────────────>│                   │                  │
     │                   │<─────────────────────│                   │                  │
     │                   │                     │                   │                  │
     │                   │ 4. PHASE: reader (no model call)        │                  │
     │                   │  Read section KCs, evidence fragments   │                  │
     │                   │──────────────────────────────────────>│                  │
     │                   │<─── bounded DTOs ───────────────────────│                  │
     │                   │                     │                   │                  │
     │                   │ 5. Resume budget    │                   │                  │
     │                   │  (budget_scope=artifact)                 │                  │
     │                   │──────────────────────────────────────────────────────────>│
     │                   │<─── reservation OK ──────────────────────────────────────│
     │                   │                     │                   │                  │
     │                   │ 6. PHASE: composer (1 model call)       │                  │
     │                   │  Build messages      │                   │                  │
     │                   │  AuditedChatWriter.complete(run, purpose="study_artifact")│
     │                   │──────────────────────────────────────────────────────────>│
     │                   │<─── AuditedTextResult (artifact JSON) ───────────────────│
     │                   │                     │                   │                  │
     │                   │ 7. Validate, stale old, persist (same as course brief)   │
     │                   │─────────────────────>│                   │                  │
     │                   │<─────────────────────│                   │                  │
     │                   │                     │                   │                  │
     │  StudyArtifactResult                   │                   │                  │
     │<──────────────────│                     │                   │                  │
```

### 5.3 Batch Generation

When the caller requests all sections (e.g., `POST /courses/{id}/study-artifacts` without a `section_id`), the service generates artifacts **sequentially** (not in parallel), one section at a time. This avoids concurrent model calls competing for budget and simplifies error handling.

```python
async def generate_all_section_artifacts(
    self, course_id: str
) -> list[StudyArtifactResult]:
    outline = self._tools.get_current_outline(course_id)
    results = []
    for section in outline.sections:
        result = await self.generate_one(course_id, section.section_id)
        results.append(result)
        if result.status == "failed":
            # Log and continue to next section
            pass
    return results
```

The API returns results as each section completes (SSE-friendly: each artifact's `done` event includes the section). Or, for simplicity, return all results in a single response after the batch completes.

### 5.4 Evidence Collection for Artifacts

The "reader" phase collects evidence for a section by:

1. **Find KCs in section**: Query `knowledge_components` where `section_id == target_section_id` AND `knowledge_revision == current_revision`.
2. **Collect evidence fragments**: For each KC, read its EvidenceRefs (stored in `knowledge_components.evidence_json`). Deduplicate by `fragment_id`.
3. **Read fragment texts**: For each unique fragment, read `source_fragments.text` for the current revision. Truncate to `MAX_ARTIFACT_EVIDENCE_TEXT_LEN` (1500 chars).
4. **Sort**: Sort fragments by `heading_path` / `ordinal` for coherent reading order.

For the course brief, evidence collection gathers a broader but bounded view:

1. **KCs**: All KCs for the current revision, capped at `MAX_BRIEF_KCS` (30).
2. **Evidence map**: For each section, collect up to `MAX_BRIEF_REFS_PER_SECTION` (5) evidence refs. These are only their labels (`fragment_id`, `material_id`, `heading_path`), not their full text — keeping the course brief prompt token-efficient.
3. **Counts**: `relations_count` from `kc_relations` (just the count, not the relations themselves).

## 6. Budget Enforcement

### 6.1 Per-Artifact Budget Isolation

Each artifact (course brief or study artifact) creates its own `AgentRun` with `budget_scope="artifact"`. The course-level artifact budget pool is checked via `reserve_agent_run_model_call` in `audited_text_model.py`.

| Artifact | `token_budget` | Model Calls | Max Output Tokens |
|----------|---------------|-------------|-------------------|
| Course Brief | 12000 | 1 | 2048 |
| Study Artifact (per section) | 12000 | 1 | 2048 |

The `token_budget` is set at `AgentRun` creation. It covers input + output tokens for that single artifact. A higher budget accommodates the input (up to 8000 token estimate) plus output (2048).

### 6.2 Budget Exhaustion

If `reserve_agent_run_model_call` returns `status="rejected"`:

1. The `AgentRun` is marked `failed` with `error_code="budget_exhausted"`.
2. The artifact record (in `course_briefs` or `study_artifacts`) is saved with `status="failed"` and the error detail.
3. The failure does NOT affect other artifacts.
4. The frontend shows "预算已用尽，请联系管理员或等待预算重置" with a visible error state.

### 6.3 Failure Isolation

Artifacts are fully independent:

- A failed course brief does not block study artifact generation.
- A failed study artifact for section 3 does not block section 4.
- A model call failure (provider error, timeout, malformed JSON) for any artifact does not block other artifacts.
- Each artifact's failure state is independently visible in the UI.

### 6.4 No Retry

Following the plan's `max_retries=0` rule: if the model call fails, the artifact is marked `failed`. The user must explicitly trigger a retry via the "重新生成" button in the UI. There is no automatic retry.

The only exception: if the model returns *valid JSON* but the service's fragment_id validation rejects unknown IDs, the artifact is also marked `failed` (not silently trimmed). This encourages the model to respect the provided evidence list.

## 7. Stale Handling

### 7.1 Stale Detection

Staleness is determined by comparing the artifact's stored revisions with the current course revisions:

```python
def _check_artifact_staleness(
    store: SqliteStore,
    course_id: str,
    artifact_source_revision: str,
    artifact_knowledge_revision: str,
) -> bool:
    status = build_knowledge_status(store, course_id)
    current_source = status.source_revision
    current_knowledge = status.knowledge_revision

    if artifact_source_revision != current_source:
        return True
    if artifact_knowledge_revision != current_knowledge:
        return True
    return False
```

### 7.2 Actions on Stale Detection

| Trigger | Action |
|---------|--------|
| GET course brief | If stale, set `status="stale"` in DB, return brief with `is_stale=true` + `stale_reason` |
| GET study artifact list | Each stale artifact returned with `is_stale=true`; stale status is computed per-artifact |
| New generation requested | Old artifact with same `(course_id, section_id, artifact_type)` tuple is marked `stale`; new record inserted with `status="active"` |
| New material uploaded → source_revision advances | On next read of any artifact, staleness is detected. Old artifacts are NOT eagerly marked stale — detection happens at read time (lazy). |
| New KC projection compiled → knowledge_revision advances | Same lazy detection as above. |

### 7.3 Stale Record Retention

Stale artifact records are **retained** in the database, not deleted. They provide an audit trail and allow comparing "what did the brief look like under the old revision." The unique index `uq_course_brief_active` and `uq_study_artifact_active` enforce the constraint that only ONE record per (course_id, section_id, artifact_type) can be `active` — but multiple `stale` records for the same key are allowed (they differ by `source_revision`/`knowledge_revision`).

### 7.4 Force Regenerate

Even if an artifact is not stale (revisions match), the user can request a forced regeneration. This:
1. Creates a new `AgentRun`.
2. On success, marks the existing `active` artifact as `stale` and inserts the new record.
3. This enables the "刷新课程简报" use case where the user wants a fresh perspective even though the material hasn't changed.

## 8. API Contract

### 8.1 POST /courses/{course_id}/course-brief

Generate (or regenerate) the course brief.

**Request**: Empty body (or `{"force": true}` to force regeneration even if not stale).

**Response** (200):
```json
{
  "brief": {
    "brief_id": "cb_a1b2c3",
    "course_id": "cs_linear_algebra",
    "source_revision": "src_20260711_001",
    "knowledge_revision": "kn_20260711_001",
    "status": "active",
    "brief_json": { /* CourseBriefContent */ },
    "created_at": "2026-07-11T10:00:00Z",
    "is_stale": false
  }
}
```

**Response** (200, pre-existing active brief without force):
Returns the existing brief (same as GET response). No generation occurs.

**Errors**:
- `400`: `course_brief_already_active` — an active brief exists. Include `{"existing_brief_id": "cb_...", "force_allowed": true}`. Client can retry with `force: true`.
- `422`: `projection_not_ready` — course projection is not ready (no current outline/KCs).
- `422`: `budget_exhausted` — artifact budget pool exhausted.
- `500`: `generation_failed` — model call or validation failed. Include `{"error_detail": "..."}`.

**SSE events** (if async is preferred, but MVP uses synchronous HTTP):
```
phase {run_id, phase="reader", agent_role="reader", display_message="读取课程结构..."}
phase {run_id, phase="composer", agent_role="composer", display_message="正在生成课程简报..."}
done  {run_id, message_id=null, envelope=null, artifact={brief_id, brief_json}}
error {run_id, error_code, message}
```

MVP implementation can return HTTP 200 on completion or a 202 + `brief_id` for polling. SSE is optional for F7 since generation is typically <10 seconds.

### 8.2 GET /courses/{course_id}/course-brief

Get the current course brief.

**Response** (200):
```json
{
  "brief": {
    "brief_id": "cb_a1b2c3",
    "course_id": "cs_linear_algebra",
    "source_revision": "src_20260711_001",
    "knowledge_revision": "kn_20260711_001",
    "status": "active",
    "brief_json": { /* CourseBriefContent */ },
    "created_at": "2026-07-11T10:00:00Z",
    "is_stale": false,
    "stale_reason": null
  }
}
```

**Response** (200, stale):
```json
{
  "brief": {
    "...": "...",
    "status": "stale",
    "is_stale": true,
    "stale_reason": "Source revision changed from src_old to src_new. 3 materials added/modified."
  }
}
```

**Response** (200, failed):
```json
{
  "brief": {
    "status": "failed",
    "error_detail": "Model call failed: timeout after 30s"
  }
}
```

**Response** (404): No brief exists for this course.

### 8.3 POST /courses/{course_id}/study-artifacts

Generate study artifacts. Can target a single section or all sections.

**Request**:
```json
{
  "section_id": "sec_004",       // optional: generate for specific section
  "force": false                  // optional: force regenerate
}
```

If `section_id` is omitted, generates artifacts for **all** sections in the current outline. Batch generation proceeds sequentially; each artifact is independently persisted.

**Response** (200, single section):
```json
{
  "artifact": {
    "artifact_id": "sa_d4e5f6",
    "course_id": "cs_linear_algebra",
    "source_revision": "src_20260711_001",
    "knowledge_revision": "kn_20260711_001",
    "section_id": "sec_004",
    "artifact_type": "chapter_review_brief",
    "status": "active",
    "artifact_json": { /* StudyArtifactContent */ },
    "created_at": "2026-07-11T10:05:00Z",
    "is_stale": false
  }
}
```

**Response** (200, all sections batch):
```json
{
  "artifacts": [
    { "artifact_id": "sa_...", "section_id": "sec_001", "status": "active", "...": "..." },
    { "artifact_id": "sa_...", "section_id": "sec_002", "status": "failed", "error_detail": "..." },
    { "artifact_id": "sa_...", "section_id": "sec_003", "status": "active", "...": "..." }
  ],
  "summary": {
    "total_sections": 8,
    "generated": 7,
    "failed": 1,
    "skipped_existing": 0
  }
}
```

**Errors**:
- `404`: `section_not_found` — the requested `section_id` is not in the current course outline.
- `422`: `projection_not_ready`
- `422`: `budget_exhausted`

### 8.4 GET /courses/{course_id}/study-artifacts

List all study artifacts for the course.

**Response** (200):
```json
{
  "artifacts": [
    {
      "artifact_id": "sa_d4e5f6",
      "section_id": "sec_001",
      "section_title": "向量空间基础",
      "artifact_type": "chapter_review_brief",
      "status": "active",
      "is_stale": false,
      "kcs_count": 3,
      "fragments_count": 5,
      "created_at": "2026-07-11T10:05:00Z"
    }
  ],
  "is_stale": false,       // true if ANY artifact is stale
  "total_active": 7,
  "total_stale": 1,
  "total_failed": 0
}
```

### 8.5 GET /courses/{course_id}/study-artifacts/{artifact_id}

Get a specific artifact's full content.

**Response** (200):
```json
{
  "artifact": {
    "artifact_id": "sa_d4e5f6",
    "course_id": "cs_linear_algebra",
    "source_revision": "src_20260711_001",
    "knowledge_revision": "kn_20260711_001",
    "section_id": "sec_004",
    "section_title": "特征值与特征向量",
    "artifact_type": "chapter_review_brief",
    "status": "active",
    "artifact_json": { /* StudyArtifactContent */ },
    "created_at": "2026-07-11T10:05:00Z",
    "is_stale": false,
    "stale_reason": null
  }
}
```

**Response** (404): Artifact not found.

### 8.6 EvidenceRef Open

EvidenceRefs in artifacts are opened via the existing V2 endpoint:

```
GET /courses/{course_id}/evidence/{fragment_id}/preview
```

Response: `SourceFragmentPreview` (from `app.schemas.evidence`), same as used by CitationCard.

The frontend renders an artifact's `evidence_refs[]` as clickable links that open the source fragment preview panel inline or in a side panel.

## 9. Service Class Design

### 9.1 CourseBriefService

```python
class CourseBriefService:
    """Revision-bound course brief generation from V2 knowledge projection."""

    def __init__(
        self,
        store: SqliteStore,
        writer: AuditedChatWriter,
        tools: V2AgentTools,
        *,
        max_input_tokens: int = 8000,
        max_output_tokens: int = 2048,
        max_brief_kcs: int = 30,
        max_brief_sections: int = 20,
        max_brief_evidence_refs: int = 40,
        temperature: float | None = 0.3,
        default_token_budget: int = 12000,
    ) -> None: ...

    async def generate(
        self,
        *,
        course_id: str,
        session_id: str,
        turn_id: str,
        force: bool = False,
    ) -> CourseBriefResult: ...

    async def get_current(
        self, course_id: str
    ) -> CourseBriefResult | None: ...

    # Internal
    def _build_messages(
        self,
        outline: CourseOutline,
        kcs: list[dict],
        relations_count: int,
        evidence_map: dict[str, list[dict]],
    ) -> list[dict]: ...

    def _validate_brief_json(
        self,
        raw_json: dict,
        allowed_fragment_ids: set[str],
    ) -> dict: ...

    def _mark_stale(self, course_id: str) -> None: ...

    def _check_staleness(
        self, store: SqliteStore, brief: dict, course_id: str
    ) -> bool: ...
```

### 9.2 ArtifactService

```python
class ArtifactService:
    """Revision-bound study artifact generation per course section."""

    def __init__(
        self,
        store: SqliteStore,
        writer: AuditedChatWriter,
        tools: V2AgentTools,
        *,
        max_input_tokens: int = 8000,
        max_output_tokens: int = 2048,
        max_artifact_kcs: int = 6,
        max_artifact_evidence: int = 5,
        max_evidence_text_len: int = 1500,
        temperature: float | None = 0.3,
        default_token_budget: int = 12000,
    ) -> None: ...

    async def generate(
        self,
        *,
        course_id: str,
        session_id: str,
        turn_id: str,
        section_id: str,
        force: bool = False,
    ) -> StudyArtifactResult: ...

    async def generate_all(
        self,
        *,
        course_id: str,
        session_id: str,
        force: bool = False,
    ) -> BatchArtifactResult: ...

    async def get_artifact(
        self, course_id: str, artifact_id: str
    ) -> StudyArtifactResult | None: ...

    async def list_artifacts(
        self, course_id: str
    ) -> ArtifactListResult: ...

    # Internal
    def _build_messages(
        self,
        section: dict,
        section_kcs: list[dict],
        section_evidence: list[dict],
    ) -> list[dict]: ...

    def _collect_section_evidence(
        self, course_id: str, section_id: str
    ) -> tuple[list[dict], list[dict]]: ...

    def _validate_artifact_json(
        self,
        raw_json: dict,
        allowed_fragment_ids: set[str],
    ) -> dict: ...
```

### 9.3 Result Dataclasses

```python
@dataclass(frozen=True)
class CourseBriefResult:
    brief_id: str | None = None
    course_id: str = ""
    status: Literal["active", "stale", "failed", "not_found"] = "not_found"
    brief_json: dict | None = None
    source_revision: str = ""
    knowledge_revision: str = ""
    is_stale: bool = False
    stale_reason: str | None = None
    agent_run_id: str | None = None
    model_call_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    created_at: str = ""

@dataclass(frozen=True)
class StudyArtifactResult:
    artifact_id: str | None = None
    course_id: str = ""
    section_id: str = ""
    section_title: str = ""
    artifact_type: str = "chapter_review_brief"
    status: Literal["active", "stale", "failed", "not_found"] = "not_found"
    artifact_json: dict | None = None
    source_revision: str = ""
    knowledge_revision: str = ""
    is_stale: bool = False
    stale_reason: str | None = None
    agent_run_id: str | None = None
    model_call_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    created_at: str = ""

@dataclass(frozen=True)
class BatchArtifactResult:
    artifacts: list[StudyArtifactResult] = field(default_factory=list)
    total_sections: int = 0
    generated: int = 0
    failed: int = 0
    skipped_existing: int = 0

@dataclass(frozen=True)
class ArtifactListResult:
    artifacts: list[dict] = field(default_factory=list)
    is_stale: bool = False
    total_active: int = 0
    total_stale: int = 0
    total_failed: int = 0
```

### 9.4 What to Reuse

| Component | Reused from | Notes |
|-----------|------------|-------|
| `V2AgentTools.get_current_outline()` | `v2_agent_tools.py` | Read course outline |
| `V2AgentTools.get_current_kcs()` | `v2_agent_tools.py` | Read KCs with evidence |
| `V2AgentTools.get_current_relations()` | `v2_agent_tools.py` | Count relations only |
| `V2AgentTools.open_evidence()` | `v2_agent_tools.py` | Fragment text for study artifacts |
| `AuditedChatWriter.complete()` | `audited_chat_writer.py` | Model call with `budget_scope="artifact"` |
| `build_knowledge_status()` | `knowledge_status.py` | Stale detection |
| `AgentRun` / `AgentStep` schema | `agent_runs.py` | Already includes `workflow_kind="course_brief"` and `"study_artifact"` |
| `EvidenceRef` model | `evidence.py` | Reuse in artifact JSON validation |
| `SourceFragmentPreview` | `evidence.py` | Opening artifact evidence refs |

### 9.5 What to Create New

| Component | File | Notes |
|-----------|------|-------|
| `CourseBriefService` | `backend/app/services/course_brief_service.py` | Main brief service |
| `ArtifactService` | `backend/app/services/artifact_service.py` | Main artifact service |
| Result dataclasses | Same files as services | Or `backend/app/schemas/artifacts.py` |
| SQLite migration + store methods | `backend/app/db/sqlite_store.py` | New tables, indexes, CRUD |
| API router | `backend/app/api/artifacts.py` | New endpoints |
| Tests | `backend/tests/test_course_brief_service.py` | 8 test scenarios |
| Tests | `backend/tests/test_artifact_service.py` | 6 test scenarios |

### 9.6 File Organization

Two separate service files to avoid bloat:
- `course_brief_service.py` — CourseBriefService + CourseBriefResult + prompt templates
- `artifact_service.py` — ArtifactService + StudyArtifactResult + BatchArtifactResult + ArtifactListResult + prompt templates

If either file exceeds ~500 lines, extract prompt templates into a shared `artifact_prompts.py`.

## 10. Test Scenarios

### Scenario 1: Course brief — happy path

**Setup**: Course "线性代数" with 4 materials, projection ready (Outline + 14 KCs + 12 Relations + 45 fragments).

**Mock**: Fake provider returns valid CourseBriefContent JSON:
```json
{
  "overview": "...",
  "key_topics": [4 topics, each with evidence_refs],
  "study_suggestions": [3 suggestions],
  "difficulty_areas": [1 area],
  "metadata": {"sections_count": 8, "kcs_count": 14, "relations_count": 12, "fragment_count": 45}
}
```

**Expected**:
- `CourseBriefResult.status == "active"`
- `brief_json.key_topics` has 4 entries, each with ≥1 evidence_ref
- `brief_json.study_suggestions` has 3 entries
- `brief_json.difficulty_areas` has 1 entry
- `brief_json.metadata.kcs_count == 14` (overwritten by service with actual count)
- AgentRun created with `workflow_kind="course_brief"`, status="completed"
- 2 AgentSteps: reader (completed), composer (completed)
- 1 model_call_audit record with `budget_scope="artifact"`
- `course_briefs` table has 1 row with `status="active"`

### Scenario 2: Course brief — force regenerate

**Setup**: An active brief already exists for `source_revision="A"`. Revision has not changed. Call generate with `force=true`.

**Expected**:
- Old brief marked `stale`
- New brief inserted with `status="active"` and `source_revision="A"` (same revision)
- Both records retained in DB
- `uq_course_brief_active` unique constraint satisfied (only one `active`)

### Scenario 3: Course brief — stale detection

**Setup**: Active brief with `source_revision="A"`. A new material is uploaded, advancing `source_revision` to "B". Call `GET /course-brief`.

**Expected**:
- Service detects staleness: `current_source_revision != brief.source_revision`
- Brief record's `status` updated from `active` to `stale` in DB
- `CourseBriefResult.is_stale == true`
- `CourseBriefResult.status == "stale"`
- `CourseBriefResult.stale_reason` is set
- `CourseBriefResult.brief_json` still returned (stale content is readable)

### Scenario 4: Course brief — projection not ready

**Setup**: Course has source fragments but `projection_status != "ready"` (KCs not compiled yet). Call `POST /course-brief`.

**Expected**:
- `CourseBriefResult.status == "not_found"` or service raises with `error_code="projection_not_ready"`
- No AgentRun created
- No model call made
- HTTP 422 returned

### Scenario 5: Course brief — model call failure

**Setup**: Fake provider raises `FakeProviderError("Rate limit", status_code=429)` on the brief generation call.

**Expected**:
- `CourseBriefResult.status == "failed"`
- `CourseBriefResult.error_code == "generation_failed"`
- `CourseBriefResult.error_detail` contains the provider error message
- AgentRun status = "failed", error fields set
- 2 AgentSteps: reader (completed), composer (failed)
- 1 model_call_audit with error fields (the failed call is still audited)
- `course_briefs` table has 1 row with `status="failed"`
- No other course state is affected

### Scenario 6: Course brief — budget exhausted

**Setup**: Course's artifact budget is exhausted. `reserve_agent_run_model_call` returns `status="rejected"`.

**Expected**:
- `CourseBriefResult.status == "failed"`
- `CourseBriefResult.error_code == "budget_exhausted"`
- AgentRun status = "failed"
- No model call made
- `course_briefs` row exists with `status="failed"`
- Subsequent API calls for other artifacts or brief regeneration fail with the same budget error until budget is reset

### Scenario 7: Study artifact — happy path (single section)

**Setup**: Course "线性代数", section "特征值与特征向量" with 3 KCs and 5 fragments.

**Mock**: Fake provider returns valid StudyArtifactContent JSON.

**Expected**:
- `StudyArtifactResult.status == "active"`
- `artifact_json.key_concepts` has 3 entries (matching the 3 KCs)
- Each `key_concept.evidence_refs` has ≥1 entry
- `artifact_json.evidence_refs` (top-level) is a deduplicated list of all refs
- All `fragment_id` values exist in the section's evidence
- AgentRun created with `workflow_kind="study_artifact"`
- 1 model_call_audit with `budget_scope="artifact"`
- `study_artifacts` table has 1 row with `status="active"`, `section_id="sec_004"`

### Scenario 8: Study artifact — fragment_id validation failure

**Setup**: Fake provider returns valid JSON but includes a `fragment_id="fake_frag_999"` which is NOT in the section's allowed fragment set.

**Expected**:
- Service validation detects the unknown fragment ID
- Artifact is marked `status="failed"` (not silently trimmed)
- `error_detail` includes which fragment IDs were unknown
- The full original model output is NOT saved (to avoid persisting invalid refs)
- The `artifact_json` in the failed record is `None` or contains only the validation error metadata
- AgentRun status = "failed"

### Scenario 9: Study artifact — batch generation with partial failure

**Setup**: Course with 3 sections. Provider succeeds for sections 1 and 3, fails (rate limit) for section 2.

**Expected**:
- `BatchArtifactResult.total_sections == 3`
- `BatchArtifactResult.generated == 2`
- `BatchArtifactResult.failed == 1`
- Section 1 and 3 artifacts are `status="active"` and persisted
- Section 2 artifact is `status="failed"` and persisted
- Failed section 2 does NOT block section 3 (independent budgets, independent model calls)
- Each section has its own AgentRun (3 runs total)

### Scenario 10: Stale old artifacts on new generation

**Setup**: Section "向量空间基础" has an active artifact from `source_revision="A"`. Revision advances to "B". API called to generate new artifact for the same section.

**Expected**:
- Old artifact marked `stale`
- New artifact inserted with `status="active"` and `source_revision="B"`
- `GET /study-artifacts` returns both: one stale, one active
- `uq_study_artifact_active` unique constraint satisfied (only one `active` per course/section/type)
- Evidence refs in new artifact reference fragments from revision "B" (the service collects them from current revision)

### Scenario 11: Study artifact — section not found

**Setup**: Call `POST /study-artifacts` with `section_id="sec_nonexistent"`.

**Expected**:
- HTTP 404 with `error_code="section_not_found"`
- No AgentRun created
- No model call made

## 11. UI Integration Notes

### 11.1 StudioPane Layout

Course brief and study artifacts appear in the `StudioPane` (the right-side panel in CourseWorkspace), alongside the existing KnowledgeGraph/Outline displays.

```
StudioPane
  ├─ KnowledgeStatusBar        (existing: fragment count, processing status)
  ├─ CourseBriefCard           (NEW)
  │   ├─ Status badge (active / stale / failed / generating)
  │   ├─ Overview text
  │   ├─ KeyTopics (expandable list with evidence links)
  │   ├─ StudySuggestions (numbered list)
  │   ├─ DifficultyAreas (collapsible, if any)
  │   └─ Action: [重新生成] button (visible when stale)
  └─ ArtifactList              (NEW)
      ├─ Title: "学习产物" with count badge
      ├─ Section artifact cards:
      │   ├─ Section title
      │   ├─ Status badge
      │   ├─ Preview: summary text (first 2 lines)
      │   ├─ [打开] button → expands inline or opens detail pane
      │   └─ [重新生成] button (visible when stale)
      └─ [全部生成] button (when no artifacts exist)
```

### 11.2 State Indicators

| State | Badge | Color | Action |
|-------|-------|-------|--------|
| Active (current revision) | "最新" | Green | None |
| Active (generating) | "生成中..." | Amber (animated) | None (show spinner in card) |
| Stale | "已过时" | Amber | "重新生成" button |
| Failed | "生成失败" | Red | "重试" button + error detail |
| Not generated | — | Gray | "生成课程简报" / "生成章节复习" button |

### 11.3 EvidenceRef Click Handling

When a user clicks an `evidence_ref` within an artifact (course brief or study artifact):

1. Frontend extracts `fragment_id` from the EvidenceRef.
2. Calls `GET /courses/{course_id}/evidence/{fragment_id}/preview` (existing V2-C1 endpoint).
3. Renders `SourceFragmentPreview` inline in a side panel or overlay (same component as CitationCard in chat).
4. The preview shows `file_name`, `heading_path`, `text`, and `locator`.

This is the same mechanism used by the V2 CitationCard for chat responses — no new endpoint needed.

### 11.4 "第一个惊喜" (First Surprise)

The plan (§12.2 P1) calls the course brief a "first surprise." Implementation guidance:

- On first course load when `projection_status == "ready"` and no brief exists, **auto-generate** the course brief (with a visible "正在为你准备课程简报..." loading state).
- The brief card should animate in after generation completes (e.g., a subtle fade-in or slide-in).
- The brief card should be positioned prominently at the top of the StudioPane, above the artifact list.
- Fox persona: include a small fox mascot or playful text like "狐狸帮你梳理好了这门课的结构" with the brief.

### 11.5 Empty States

| Empty State | Display |
|-------------|---------|
| No brief, projection not ready | "课程知识体系构建完成后，狐狸会为你生成课程简报。" + disabled [生成] button |
| No brief, projection ready | "狐狸已经读完了课程材料，准备好为你生成课程简报。" + enabled [生成课程简报] button |
| No artifacts, projection ready | "还没有生成任何学习产物。点击「全部生成」为每个章节创建复习简报。" + [全部生成] button |
| Brief generation in progress | Card with spinner + "狐狸正在整理课程结构..." |
| Artifact generation in progress | Per-section card with spinner + "正在生成..." |

## 12. Implementation Notes

### 12.1 Generation Timing

- Course brief generation typically takes 5–10 seconds (1 model call + evidence collection).
- Study artifact generation per section typically takes 3–8 seconds each.
- Batch generation of 8 sections ≈ 24–64 seconds total (sequential).
- The API returns HTTP 202 with `agent_run_id` for async monitoring if the service layer takes >30s; otherwise returns HTTP 200 synchronously. MVP can use synchronous HTTP 200 for simplicity (acceptable for <10s responses).

### 12.2 Evidence Collection Performance

- **Course brief**: Reading KCs (up to 30) and counting relations requires 2–3 SQL queries. Extremely fast (<50ms).
- **Study artifact**: Reading section KCs + deduplicating evidence refs + reading fragment texts requires 3–5 SQL queries per section. Estimated <100ms per section.
- Both evidence collection phases are synchronous (no external model calls) and complete within the request cycle.

### 12.3 Model Choice

Use the standard `AuditedChatWriter` which picks the model from configuration. The brief and artifact generation are simple structured generation tasks — `deepseek-v4-flash` is suitable (faster, cheaper). For the initial F7 implementation, use the same model as `quick_answer`, with temperature 0.3.

### 12.4 Idempotency

- `POST /course-brief`: If an active brief already exists and `force=false`, return 200 with the existing brief. No duplicate AgentRun.
- `POST /study-artifacts`: If an active artifact already exists for the given `section_id` and `force=false`, skip generation and return the existing artifact (in batch mode, count it as `skipped_existing`).
- Force flag: always generates a new record, even if active exists.

### 12.5 Error Visibility (HEC-1)

All error states are persisted and visible:
- Failed briefs/artifacts are saved with `status="failed"` and `error_detail`.
- The API returns the error detail to the frontend.
- The frontend displays "生成失败" with the error detail and a retry button.
- Model call failures are audited in `model_call_audits` with the error.
- No silent `try/except: return ""` patterns.

### 12.6 Edge Cases

1. **Empty course (zero KCs, zero relations)**: Course brief generation still runs. `difficulty_areas` will be empty. `study_suggestions` will be based on section order only. Valid outcome for simple courses.

2. **Single-section course**: Course brief generates normally. Study artifact list has exactly 1 entry. Both are valid.

3. **Very large section (100+ fragments)**: Evidence collection caps at `MAX_ARTIFACT_EVIDENCE_PER_SECTION` (5). The model only sees the top 5 fragments (sorted by ordinal/heading). A warning is added to the AgentStep if fragments were truncated.

4. **Model returns valid JSON but empty lists**: Treated as valid. `key_topics` with 3 entries is validated against the minimum (3). If the model returns 2, validation fails and artifact is marked `failed`.

5. **Model returns non-JSON**: The service attempts to find JSON within the response text. If that fails, artifact is marked `failed`. No retry (per `max_retries=0` rule).

6. **Concurrent generation for same course**: The store methods use the unique index `uq_course_brief_active` / `uq_study_artifact_active` to prevent two active records. If a race occurs, the second insertion fails with a constraint violation, which is caught and returned as a 409 conflict error.

7. **SQLite single-worker constraint**: MVP uses SQLite; all artifact generation is sequential within a single request cycle. No lease mechanism needed (agent runs are within the request lifecycle, not persistent worker jobs).

## 13. Open Questions

1. **Async generation for large courses**: For courses with 20+ sections, batch artifact generation could take 2+ minutes. Should the API accept a `background=true` flag and return a `knowledge_jobs`-style persistent task with SSE progress? Recommendation: not for MVP. Implement synchronous HTTP for V2-F7; add async batching if user feedback indicates it's needed.

2. **Artifact types beyond chapter_review_brief**: Future types (concept_relation_handout, exam_review_guide, flash_card_set) use the same `study_artifacts` table with different `artifact_type` values. The unique constraint already handles this. No need to design a polymorphic artifact system.

3. **Pagination for artifact list**: For courses with 20+ sections, the artifact list could be large. Recommendation: no pagination for MVP. The list is at most ~20 items.

4. **Artifact JSON versioning**: The `version` field in `brief_json` and `artifact_json` allows forward compatibility. If the schema changes, increment the version; old artifacts with version=1 remain readable; new generations use version=2.

