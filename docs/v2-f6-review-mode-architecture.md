# V2-F6: Conversational Review Mode + /btw + LearnerObservation Architecture

> **Status**: Architecture design (no code modifications)
>
> **Date**: 2026-07-11 (Asia/Shanghai)
>
> **Depends on**: V2-F3 (Chat API), V2-F5 (DeepDiveService), current V2 KC/Relation projection
>
> **Implements**: `docs/course-agent-v2-plan.md` §6.2 `review_plan` / `review_session` / `btw`, §7.4 `LearnerObservation`, §8.3 review model budget

## 1. Decision Summary

V2-F6 delivers a revision-bound conversational review mode that uses current V2 knowledge (Outline, KC, Relation) to drive a teach → attempt → feedback → recap state machine. Key architectural decisions:

1. **Plan generation is deterministic + model-organized, not model-generated**: A deterministic scheduler computes day-to-item mapping from hard constraints (days remaining, KC topology, material coverage). A single model call per day organizes the teaching plan into a human-friendly expression. This ensures the plan is reproducible and auditable.

2. **Session is a state machine, not free-form chat**: The state machine `briefing → teach → attempt → feedback → recap → next_day → ... → done` is enforced server-side. The UI never lets the user "free jump" to arbitrary KC IDs — the coach selects the next item from the plan.

3. **Examiner, Grader, and Tutor are separate model calls with distinct budgets**: Each review turn involves exactly 1 Examiner call (generate question), 1 Grader call (evaluate answer), and optionally 1 Tutor call (make-up for verified gaps). Maximum 2–3 text model calls per attempt.

4. **/btw is a child turn, not a state transition**: /btw reuses `QuickAnswerService` or `DeepDiveService` wholesale. It persists a `return_anchor` pointing to `{session_id, day, item_id, step_id}`. Answer success/failure/cancel does NOT advance the main review state machine. When /btw completes, the UI returns to the anchored step.

5. **LearnerObservation is traceable, not yet personalizing**: Observations are created on grading results as audit records. They are displayed in the Studio panel but are NOT used by the plan generation algorithm (until V2-F8+ or later).

6. **Existing `review_plans` / `review_sessions` tables are legacy**: The current blob-as-JSON tables are replaced by V2-style normalized tables with explicit revision fields.

## 2. Sequence Diagram

### 2.1 Full Review Flow (Plan Generation + Session Lifecycle)

```
┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐  ┌─────────────┐
│ Frontend │  │ ReviewService │  │SqliteStore│  │ V2 Tools  │  │AuditedWriter │  │QuickAnswerSvc│
└────┬─────┘  └──────┬───────┘  └─────┬─────┘  └─────┬─────┘  └──────┬───────┘  └──────┬──────┘
     │               │                │               │               │                 │
     │ POST /review/plan               │               │               │                 │
     │──────────────>│                │               │               │                 │
     │               │                │               │               │                 │
     │               │ 1. Read current│               │               │                 │
     │               │    Outline, KC,│               │               │                 │
     │               │    Relation    │               │               │                 │
     │               │───────────────>│               │               │                 │
     │               │<───────────────│               │               │                 │
     │               │                │               │               │                 │
     │               │ 2. Deterministic scheduler:   │               │                 │
     │               │    Compute days, distribute   │               │                 │
     │               │    KCs per day by topology    │               │                 │
     │               │    and material coverage      │               │                 │
     │               │                │               │               │                 │
     │               │ 3. Create review_plan record  │               │                 │
     │               │───────────────>│               │               │                 │
     │               │<───────────────│               │               │                 │
     │               │                │               │               │                 │
     │    plan_json  │                │               │               │                 │
     │<──────────────│                │               │               │                 │
     │               │                │               │               │                 │
     │ POST /review/session/start      │               │               │                 │
     │──────────────>│                │               │               │                 │
     │               │                │               │               │                 │
     │               │ 4. Validate plan not stale    │               │                 │
     │               │    Create session (day=1,     │               │                 │
     │               │    step="briefing")            │               │                 │
     │               │───────────────>│               │               │                 │
     │               │<───────────────│               │               │                 │
     │               │                │               │               │                 │
     │               │ 5. briefing step (no model)   │               │                 │
     │               │    Return: day plan, total     │               │                 │
     │               │    days, today's topics        │               │                 │
     │               │                │               │               │                 │
     │  session_state│                │               │               │                 │
     │<──────────────│                │               │               │                 │
     │               │                │               │               │                 │
     │ POST /review/session/{sid}/advance   (step: "teach")          │                 │
     │──────────────>│                │               │               │                 │
     │               │                │               │               │                 │
     │               │ 6. teach step (Coach: no model call)          │                 │
     │               │    Select current item from plan               │                 │
     │               │    Read item's KCs + evidence refs             │                 │
     │               │    Build teaching brief (from KC definitions   │                 │
     │               │    + evidence text, no model generation)       │                 │
     │               │                │               │               │                 │
     │  teaching_view│                │               │               │                 │
     │<──────────────│                │               │               │                 │
     │               │                │               │               │                 │
     │ POST /review/session/{sid}/advance   (step: "attempt")        │                 │
     │──────────────>│                │               │               │                 │
     │               │                │               │               │                 │
     │               │ 7. attempt step: Examiner (1 model call)      │                 │
     │               │    Input: item KC IDs, evidence refs,         │                 │
     │               │           prior feedback (if retry)             │                 │
     │               │    Call examiner writer        │               │                 │
     │               │───────────────────────────────────────────────>│                 │
     │               │<─── Structured Question ────────────────────────│                 │
     │               │    (question + rubric + kc_ids + evidence_refs) │                 │
     │               │                │               │               │                 │
     │               │ 8. Create review_attempt (status="awaiting")   │                 │
     │               │───────────────>│               │               │                 │
     │               │<───────────────│               │               │                 │
     │               │                │               │               │                 │
     │  question_view│                │               │               │                 │
     │<──────────────│                │               │               │                 │
     │               │                │               │               │                 │
     │ POST /review/session/{sid}/answer                                 │                 │
     │──────────────>│                │               │               │                 │
     │               │                │               │               │                 │
     │               │ 9. Grade step: Grader (1 model call)            │                 │
     │               │    Input: user answer, rubric, evidence         │                 │
     │               │    [Trivial case: empty answer → skip model]    │                 │
     │               │    Call grader writer            │               │                 │
     │               │───────────────────────────────────────────────>│                 │
     │               │<─── GradingResult ───────────────────────────────│                 │
     │               │    (correct/missing/error/uncertain)             │                 │
     │               │                │               │               │                 │
     │               │ 10. Create LearnerObservation (if gap found)    │                 │
     │               │───────────────>│               │               │                 │
     │               │<───────────────│               │               │                 │
     │               │                │               │               │                 │
     │               │ 11. [If gaps] Tutor make-up (1 model call)     │                 │
     │               │     Input: wrong KC IDs, evidence               │                 │
     │               │───────────────────────────────────────────────>│                 │
     │               │<─── make-up explanation ────────────────────────│                 │
     │               │                │               │               │                 │
     │               │ 12. Advance to feedback / next item             │                 │
     │               │───────────────>│               │               │                 │
     │               │<───────────────│               │               │                 │
     │               │                │               │               │                 │
     │  feedback_view│                │               │               │                 │
     │<──────────────│                │               │               │                 │
     │               │                │               │               │                 │
     │               │ ...continue until day's items done...          │                 │
     │               │ Then: recap → next_day → ... → done            │                 │
     │               │                │               │               │                 │
     │ POST /review/session/{sid}/complete                              │                 │
     │──────────────>│                │               │               │                 │
     │               │ 13. Mark session completed, return summary     │                 │
     │               │───────────────>│               │               │                 │
     │               │<───────────────│               │               │                 │
     │  summary_view │                │               │               │                 │
     │<──────────────│                │               │               │                 │
     │               │                │               │               │                 │
```

### 2.2 /btw Child Turn

```
┌──────────┐  ┌──────────────┐  ┌──────────────────┐  ┌───────────┐
│ Frontend │  │ ReviewService │  │ QuickAnswerSvc /  │  │SqliteStore│
│          │  │               │  │ DeepDiveSvc       │  │           │
└────┬─────┘  └──────┬────────┘  └────────┬─────────┘  └─────┬─────┘
     │               │                    │                   │
     │ POST /review/session/{sid}/btw     │                   │
     │──────────────>│                    │                   │
     │               │                    │                   │
     │               │ 1. Validate session is active          │
     │               │    and current step is "attempt"       │
     │               │    or "feedback"                       │
     │               │                    │                   │
     │               │ 2. Build return_anchor:                │
     │               │    {session_id, day, item_id, step_id} │
     │               │───────────>│        │                   │
     │               │            │        │                   │
     │               │ 3. Create AgentRun (workflow="btw")    │
     │               │    with review_context containing      │
     │               │    the return_anchor                   │
     │               │───────────>│        │                   │
     │               │            │        │                   │
     │               │            │ 4. Run quick_answer or    │
     │               │            │    deep_dive (same as     │
     │               │            │    normal chat)           │
     │               │            │────────>│                   │
     │               │            │<────────│                   │
     │               │            │        │                   │
     │               │ 5. Return answer + return_anchor        │
     │  answer_view  │                    │                   │
     │  + "返回复习" │                    │                   │
     │<──────────────│                    │                   │
     │               │                    │                   │
     │               │ 6. Main review state NOT advanced      │
     │               │    Session remains at same step        │
     │               │                    │                   │
```

## 3. Data Model

### 3.1 SQLite DDL (V2-style, explicit revision, course-scoped)

All new tables replace the existing `review_plans` (blob-as-JSON) and `review_sessions` (minimal fields) tables. Migration must back up existing data but does not need to convert the old blob format.

```sql
-- ===== V2-F6 Review Tables =====

-- A revision-bound review plan generated from the current knowledge projection.
-- One active plan per course at a time. Old plans are marked stale when
-- source_revision or knowledge_revision changes.
CREATE TABLE IF NOT EXISTS review_plans_v2 (
    id              TEXT PRIMARY KEY,                  -- "rp_" + sha256 hash
    course_id        TEXT NOT NULL,
    exam_date        TEXT NOT NULL,                     -- ISO-8601 date
    source_revision  TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    plan_json        TEXT NOT NULL,                     -- deterministic scheduler output
    plan_summary     TEXT,                              -- human-friendly summary (optional model output)
    status           TEXT NOT NULL DEFAULT 'active',    -- 'active' | 'stale' | 'completed'
    days_count       INTEGER NOT NULL,
    total_kcs        INTEGER NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
CREATE INDEX IF NOT EXISTS idx_review_plans_v2_course ON review_plans_v2(course_id, status);

-- A single review session: one execution of the plan state machine.
-- Only one active session per course at a time.
CREATE TABLE IF NOT EXISTS review_sessions_v2 (
    id              TEXT PRIMARY KEY,                  -- "rs_" + sha256 hash
    plan_id         TEXT NOT NULL,
    course_id        TEXT NOT NULL,
    source_revision  TEXT NOT NULL,
    knowledge_revision TEXT NOT NULL,
    current_day      INTEGER NOT NULL DEFAULT 1,
    current_step     TEXT NOT NULL DEFAULT 'briefing',  -- state machine step
    current_item_id  TEXT,                              -- current plan item being worked on
    status           TEXT NOT NULL DEFAULT 'active',    -- 'active' | 'paused' | 'completed' | 'stale' | 'cancelled'
    started_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (plan_id) REFERENCES review_plans_v2(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
CREATE INDEX IF NOT EXISTS idx_review_sessions_v2_course ON review_sessions_v2(course_id, status);

-- A single review attempt: one question → answer → grading cycle.
CREATE TABLE IF NOT EXISTS review_attempts (
    id              TEXT PRIMARY KEY,                  -- "ra_" + sha256 hash
    session_id      TEXT NOT NULL,
    course_id        TEXT NOT NULL,
    day             INTEGER NOT NULL,
    item_id         TEXT NOT NULL,                     -- from plan's items[]
    kc_ids_json     TEXT NOT NULL,                     -- JSON array of KC IDs in scope
    question_json   TEXT NOT NULL,                     -- Examiner output (Question + Rubric + EvidenceRefs)
    user_answer     TEXT,                              -- student's submitted answer
    grade_json      TEXT,                              -- Grader output JSON
    status          TEXT NOT NULL DEFAULT 'awaiting',  -- 'awaiting' | 'submitted' | 'graded' | 'retrying' | 'skipped'
    is_retry        INTEGER NOT NULL DEFAULT 0,        -- 0=first attempt, 1=retry after gap make-up
    agent_run_id    TEXT,                              -- associated AgentRun ID
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT,
    FOREIGN KEY (session_id) REFERENCES review_sessions_v2(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
CREATE INDEX IF NOT EXISTS idx_review_attempts_session ON review_attempts(session_id, day, item_id);

-- Minimal LearnerObservation: traceable audit record, not yet used for personalization.
CREATE TABLE IF NOT EXISTS learner_observations (
    id              TEXT PRIMARY KEY,                  -- "lo_" + sha256 hash
    course_id        TEXT NOT NULL,
    session_id       TEXT NOT NULL,
    kc_id            TEXT NOT NULL,
    observation_type TEXT NOT NULL,                    -- 'explicit_difficulty' | 'correct_attempt' |
                                                      -- 'incorrect_attempt' | 'missing_condition' |
                                                      -- 'repeated_clarification'
    confidence       REAL NOT NULL DEFAULT 1.0,        -- Grader confidence in this observation
    source_attempt_id TEXT NOT NULL,                    -- review_attempts.id
    source_run_id    TEXT,                              -- agent_runs.run_id
    detail           TEXT,                              -- human-readable detail (e.g., "Missing: existence condition")
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (session_id) REFERENCES review_sessions_v2(id),
    FOREIGN KEY (source_attempt_id) REFERENCES review_attempts(id)
);
CREATE INDEX IF NOT EXISTS idx_learner_obs_course ON learner_observations(course_id, kc_id);
CREATE INDEX IF NOT EXISTS idx_learner_obs_session ON learner_observations(session_id);
```

### 3.2 plan_json Structure

The `plan_json` field in `review_plans_v2` stores the deterministic scheduler output:

```json
{
  "version": 1,
  "algorithm": "topological_weighted_2026_07",
  "days": [
    {
      "day": 1,
      "title": "向量空间基础",
      "items": [
        {
          "item_id": "day1_item1",
          "kc_ids": ["kc_abc123", "kc_def456"],
          "evidence_refs": [
            {"material_id": "mat_A", "fragment_id": "frag_001", "heading_path": "1.1 向量空间"},
            {"material_id": "mat_A", "fragment_id": "frag_002", "heading_path": "1.2 子空间"}
          ],
          "topic": "向量空间与子空间的定义",
          "priority": 1,
          "estimated_minutes": 15
        },
        {
          "item_id": "day1_item2",
          "kc_ids": ["kc_ghi789"],
          "evidence_refs": [
            {"material_id": "mat_A", "fragment_id": "frag_003", "heading_path": "1.3 线性组合"}
          ],
          "topic": "线性组合与线性无关",
          "priority": 2,
          "estimated_minutes": 15
        }
      ],
      "daily_summary": "掌握向量空间基本定义和线性组合概念"
    }
  ],
  "metadata": {
    "total_days": 5,
    "total_kcs": 14,
    "exam_date": "2026-08-15",
    "generated_at": "2026-07-11T10:00:00Z",
    "has_learning_history": false
  }
}
```

### 3.3 question_json Structure (Examiner Output)

```json
{
  "question_text": "判定下列向量组是否线性无关：v1 = (1, 2, 3), v2 = (4, 5, 6), v3 = (7, 8, 9)",
  "question_type": "判定",
  "rubric": {
    "correct_answer": "线性相关。因为 v1 + v3 - 2v2 = 0，或行列式为零。",
    "key_points": [
      "计算行列式或构造线性方程组",
      "得到的行列式为零表明线性相关",
      "解释线性相关的含义"
    ],
    "acceptable_variants": [
      "用初等变换判定",
      "用秩判定"
    ]
  },
  "kc_ids": ["kc_ghi789"],
  "evidence_refs": [
    {"material_id": "mat_A", "fragment_id": "frag_003", "heading_path": "1.3 线性组合"}
  ],
  "difficulty": "medium"
}
```

### 3.4 grade_json Structure (Grader Output)

```json
{
  "overall": "partial",
  "correct_points": [
    "正确计算了行列式",
    "得出了行列式为零的结论"
  ],
  "missing_points": [
    "未解释行列式为零为什么意味着线性相关"
  ],
  "error_points": [],
  "uncertain_points": [],
  "kc_assessment": {
    "kc_ghi789": "partial"
  },
  "learner_observations": [
    {
      "kc_id": "kc_ghi789",
      "type": "missing_condition",
      "confidence": 0.9,
      "detail": "Student computed determinant correctly but didn't articulate the connection to linear dependence"
    }
  ]
}
```

### 3.5 Relation to Existing Tables

| Event | AgentRun | AgentSteps | Model Calls |
|-------|----------|-----------|-------------|
| Plan generation (model summary) | Yes (`workflow_kind="review_plan"`) | 2: `read_tools`, `generate` | 1 (plan summary) |
| Examiner question | Yes (`workflow_kind="review_session"`) | 1: `generate` | 1 (examiner) |
| Grader evaluation | (same run) | 1: `grade` | 1 (grader) |
| Tutor make-up | (same run) | 1: `generate` | 0-1 (tutor, only if gaps) |
| /btw child turn | Yes (`workflow_kind="btw"`) | As per QuickAnswer/DeepDive | As per QuickAnswer/DeepDive |

## 4. State Machine

### 4.1 States and Transitions

```
                    ┌──────────┐
                    │ briefing │  ◄─── session start, or page refresh restore
                    └────┬─────┘
                         │ advance
                         ▼
                    ┌──────────┐
              ┌─────│  teach   │
              │     └────┬─────┘
              │          │ advance
              │          ▼
              │     ┌──────────┐
              │     │ attempt  │◄──── retry (after tutor make-up)
              │     └────┬─────┘
              │          │ submit answer
              │          ▼
              │     ┌──────────┐
              │     │ grading  │  (transient, auto-advances)
              │     └────┬─────┘
              │          │
              │    ┌─────┴─────┐
              │    │           │
              │  gaps        no gaps
              │    │           │
              │    ▼           │
              │ ┌──────────┐   │
              │ │  tutor   │   │
              │ │ (make-up)│   │
              │ └────┬─────┘   │
              │      │         │
              │      ▼         │
              │ ┌──────────┐   │
              └─│ feedback │◄──┘
                └────┬─────┘
                     │ advance
                     ▼
               ┌──────────┐    ┌────────────┐    ┌──────┐
               │ next_item│───>│ next_day   │───>│ done │
               │          │ or │ (recap)    │    │      │
               └──────────┘    └────────────┘    └──────┘
```

### 4.2 Transition Rules

| From | To | Trigger | Side Effects |
|------|----|---------|--------------|
| `briefing` | `teach` | User clicks "开始复习" → `POST .../advance` | Session persisted with `current_step="teach"` |
| `teach` | `attempt` | User finishes reading → `POST .../advance` | Examiner call made; `review_attempt` created (`status="awaiting"`); `current_item_id` set |
| `attempt` | `grading` | User submits answer → `POST .../answer` | `user_answer` saved; Grader call made; `grade_json` written |
| `grading` | `tutor` | Grader found gaps AND user requests make-up | Tutor call made; `review_attempt.status="retrying"` |
| `grading` | `feedback` | Grader found gaps but user skips make-up, OR no gaps found | Grading result displayed; LearnerObservations created |
| `tutor` | `feedback` | Make-up explanation rendered | `review_attempt.is_retry=1` persists |
| `feedback` | `next_item` | Current item done, more items in plan for today | `current_item_id` → next item; `current_step="teach"` for next item |
| `feedback` | `next_day_recap` | All items for current day complete | Day recap generated; `current_step="recap"` |
| `next_day_recap` | `next_day` | User clicks "下一天" → `POST .../advance` | `current_day += 1`; `current_step="briefing"` for new day |
| `next_day_recap` | `done` | Current day was the last day | Session `status="completed"` |
| Any | `stale` | `source_revision` changed mid-session (detected on next advance) | Session marked stale; new plan offered |

### 4.3 State Validation

The `advance` endpoint validates:
1. Current state is one from which advancing is legal
2. Target state exists in the transition map
3. Plan and session are not stale (`source_revision == current`)
4. `current_item_id` exists in the plan for the current day
5. If transitioning from `grading`, the grade result must exist

### 4.4 Grade Result Decision Logic

The `grading` → `tutor` or `feedback` decision is server-side (deterministic from `grade_json`):

```python
def _has_gaps(grade_json: dict) -> bool:
    """Returns True if the grading found gaps worth making up."""
    return bool(
        grade_json.get("missing_points")
        or grade_json.get("error_points")
    )

def _needs_tutor_makeup(grade_json: dict) -> bool:
    """Returns True if gaps are about course material (not just formatting)."""
    if not _has_gaps(grade_json):
        return False
    # If all errors are "uncertain_points" (grader unsure), still offer tutor
    # If errors are concrete missing/incorrect, always offer tutor
    return True
```

## 5. Examiner + Grader + Tutor Prompt Templates

### 5.1 Examiner System Prompt (course-agnostic)

All prompts are **course-agnostic**: no hardcoded subject names, chapter titles, or math-specific fields. All course information comes from the template parameters.

```
你是 FoxSay 学习助手的"狐狸考官"——一只会出题、但不会刁难学生的狐狸。

你会收到：
1. 当前复习的知识点列表（每个知识点有名称、定义和类型）
2. 课程材料中的证据片段（用于验证题目正确性）

你的任务：
生成一道能够检验学生对知识点理解程度的题目。

规则：
1. 题目类型根据知识点类型选择：
   - concept/definition：出"请解释..."或"什么是..."题目
   - formula：出计算或应用题目
   - theorem：出"请判断对错并说明理由"或"在什么条件下..."题目
   - procedure：出步骤类题目

2. 题目必须严格基于提供的知识点和证据，不要编造知识点中不包含的条件或概念。
3. rubric（评分标准）必须包含：
   - correct_answer：参考答案
   - key_points：评分要点列表（2-5条）
   - acceptable_variants：可接受的替代解法（1-3条）

4. 题目难度适中，应该能检验学生对核心概念的理解，而不是记忆细节。
5. 如果是重试（retry），题目应该针对上次缺失的知识点，而不是完全换一道新题。

请以 JSON 格式返回：
{
  "question_text": "题目文本",
  "question_type": "类型",
  "rubric": {
    "correct_answer": "参考答案",
    "key_points": ["要点1", "要点2"],
    "acceptable_variants": ["替代解法1"]
  },
  "kc_ids": ["知识点ID列表"],
  "evidence_refs": [{"material_id": "...", "fragment_id": "...", "heading_path": "..."}],
  "difficulty": "easy|medium|hard"
}
```

### 5.2 Examiner User Message Template

```python
def _build_examiner_message(
    item_kcs: list[dict],        # Each: {kc_id, name, kind, definition}
    evidence_text: str,          # Concatenated evidence (already truncated)
    retry_context: dict | None,  # Prior feedback if retry
) -> str:
    parts = []

    kc_list = []
    for kc in item_kcs:
        kc_list.append(
            f"  · [{kc['kc_id']}] {kc['name']}（{kc['kind']}）：{kc['definition'][:200]}"
        )
    parts.append(f"复习知识点：\n" + "\n".join(kc_list))

    if evidence_text:
        parts.append(f"\n课程材料证据：\n{evidence_text[:2000]}")

    if retry_context:
        parts.append(f"\n⚠️ 这是重试题目。上次缺失的知识点：")
        for gap in retry_context.get("missing_points", []):
            parts.append(f"  - {gap}")
        parts.append("\n请针对上述缺口出题，不要完全换新题。")

    parts.append('\n请以 JSON 格式返回：{"question_text": "...", ...}')
    return "\n".join(parts)
```

### 5.3 Grader System Prompt (course-agnostic)

```
你是 FoxSay 学习助手的"狐狸评卷官"——一只公正客观、善于发现细节的狐狸。

你会收到：
1. 题目的评分标准（rubric），包括参考答案和评分要点
2. 课程材料的证据片段
3. 学生的作答文本

你的任务：
对照评分标准，评价学生的作答，识别正确点、缺失点和错误点。

规则：
1. 逐条对照 key_points 检查学生作答。
2. 如果学生的表达不同但意思正确，计入 correct_points。
3. 如果 rubric 中有 acceptable_variants，接受学生的替代解法。
4. 不确定的地方（学生的表达模糊、无法确定对错）放入 uncertain_points。
5. 只评价学生对知识点的掌握，不评价语言表达、格式或拼写。
6. 如果学生作答完全空白，直接标记所有 key_points 为 missing。
7. 对于学生的错误点，尽量指出具体错误原因。

请以 JSON 格式返回：
{
  "overall": "correct|partial|incorrect",
  "correct_points": ["正确点1"],
  "missing_points": ["缺失点1"],
  "error_points": ["错误点1"],
  "uncertain_points": ["不确定点1"],
  "kc_assessment": {
    "kc_id_1": "correct|partial|incorrect"
  },
  "learner_observations": [
    {
      "kc_id": "知识点ID",
      "type": "correct_attempt|incorrect_attempt|missing_condition",
      "confidence": 0.0-1.0,
      "detail": "简短说明"
    }
  ]
}

- overall：correct（全部正确）、partial（部分正确）、incorrect（完全没有掌握）
- incorrect_attempt：学生尝试了但答错
- missing_condition：学生遗漏了关键条件或步骤
```

### 5.4 Grader User Message Template

```python
def _build_grader_message(
    question: dict,             # Parsed question_json
    user_answer: str,
    evidence_text: str,
) -> str:
    parts = []
    parts.append(f"题目：{question['question_text']}")
    parts.append(f"参考答案：{question['rubric']['correct_answer']}")
    parts.append(f"评分要点：")
    for i, kp in enumerate(question['rubric']['key_points'], 1):
        parts.append(f"  {i}. {kp}")

    if question['rubric'].get('acceptable_variants'):
        parts.append(f"可接受替代解法：")
        for v in question['rubric']['acceptable_variants']:
            parts.append(f"  · {v}")

    if evidence_text:
        parts.append(f"\n课程材料证据：\n{evidence_text[:1500]}")

    parts.append(f"\n学生作答：\n{user_answer}")

    parts.append('\n请以 JSON 格式返回评价。')
    return "\n".join(parts)
```

### 5.5 Tutor Make-up System Prompt

```
你是 FoxSay 学习助手的"狐狸辅导员"——一只擅长查漏补缺、耐心讲题的狐狸。

你会收到：
1. 学生答错的知识点列表（KC IDs + 定义）
2. 课程材料的证据片段
3. 学生的具体错误点

你的任务：
针对学生的知识缺口，给出简洁、聚焦的补充讲解。

规则：
1. 只讲解学生真正缺失或错误的部分，不要重复学生已经掌握的内容。
2. 基于课程材料证据讲解，不要编造材料中没有的信息。
3. 用学生能理解的表达方式，适当举例。
4. 讲解后可以给一个小提示帮助学生记忆。
5. 保持狐狸的个性：聪明、有点小狡黠，但真诚有帮助。

请以 JSON 格式返回：
{
  "make_up_text": "补充讲解文本",
  "hint": "一个简短记忆提示"
}
```

### 5.6 Trivial Case Bypass (Empty Answer)

Before calling the Grader model, the service checks:

```python
if not user_answer or not user_answer.strip():
    # Skip model call — return obvious feedback
    return {
        "overall": "incorrect",
        "correct_points": [],
        "missing_points": [kp for kp in rubric.get("key_points", [])],
        "error_points": [],
        "uncertain_points": [],
        "kc_assessment": {kc_id: "incorrect" for kc_id in kc_ids},
        "learner_observations": [
            {
                "kc_id": kc_id,
                "type": "incorrect_attempt",
                "confidence": 1.0,
                "detail": "Student submitted empty answer"
            }
            for kc_id in kc_ids
        ]
    }
```

## 6. Plan Generation Algorithm

### 6.1 Deterministic Scheduler (No Model Call)

The scheduler produces the `plan_json.days[]` array entirely via deterministic computation. A subsequent optional model call produces the human-friendly `plan_summary` field.

```
Input:
  - exam_date: ISO-8601 date string
  - kcs: list of KnowledgeComponent objects (from V2Tools)
  - relations: list of KCRelation objects
  - outline: CourseOutline (for section ordering)
  - existing_observations: list of LearnerObservation (may be empty)

Algorithm:

1. COMPUTE DAYS:
   remaining = max(1, min(30, (exam_date - today).days))
   // Caps at 30 to avoid impossibly large plans; floors at 1.

2. BUILD KC GRAPH:
   - Each KC is a node.
   - Each prerequisite relation is a directed edge (source → target).
   - Each "related" relation is an undirected edge (both ways).
   - Compute topological order of KCs (Kahn's algorithm).
   - If no relations exist: use section_order → KC order within section.

3. ASSIGN PRIORITIES:
   For each KC:
     base_priority = 1.0
     // KC with more dependents (KCs that need it) gets higher priority
     dependents = count of KCs that have this KC as prerequisite
     base_priority += dependents * 0.5
     // KC with more material coverage gets higher priority
     material_coverage = count of distinct material_ids in KC.evidence
     base_priority += material_coverage * 0.2
     // Existing observations (correct/incorrect) are NOT used in MVP

4. DISTRIBUTE KCs PER DAY:
   total_priority = sum of all KC priorities
   kcs_per_day = round(len(kcs) / remaining)  // ceiling distribution
   For each day d in 1..remaining:
     // Take next kcs_per_day KCs from the topological order,
     // weighted by priority within each topological level
     // Ensure prerequisites appear on same or earlier day
     // Group related KCs on the same day when possible

5. BUILD ITEMS:
   For each day:
     Group KCs into items (1-3 KCs per item, related KCs grouped together)
     For each item:
       item_id = f"day{d}_item{n}"
       topic = generate_topic_name(kcs)  // deterministic from KC names
       evidence_refs = collect EvidenceRefs from all KCs in item
```

### 6.2 No Personalization Without History

The algorithm explicitly does NOT use `LearnerObservation` for priority calculation in MVP. This prevents:

- Fabricating "薄弱点" without real data
- Suggesting student is "weak at 特征值" just because the chapter is hard
- Claiming "你需要重点复习..." without prior ReviewAttempt data

The `plan_summary` field is the only place where a model might add human-friendly text, but the model prompt must constrain it:

```
不要声称学生薄弱点。你只能描述课程内容的组织安排，
不能声称"你最需要加强的是..."或"你可能在这些方面比较薄弱"。
```

### 6.3 Plan Invalidation (Staleness)

A plan becomes `stale` when:
- `current_source_revision != plan.source_revision` (material added/modified/removed)
- `current_knowledge_revision != plan.knowledge_revision` (KC/Relation projection recompiled)

The plan's `status` is set to `"stale"` and a new plan generation is triggered on next request.

## 7. /btw Integration

### 7.1 Architecture

`/btw` is a child turn within an active review step. It reuses `QuickAnswerService.answer()` or `DeepDiveService.answer()` **wholesale** — the ReviewService does not reimplement retrieval or answer generation.

### 7.2 Return Anchor

`return_anchor` is a structured value that allows the UI (and the user) to return to the exact review context after the /btw answer:

```json
{
  "session_id": "rs_abc123",
  "plan_id": "rp_def456",
  "day": 2,
  "item_id": "day2_item1",
  "step_id": "attempt",
  "step_label": "第2天 · 矩阵运算 · 答题中"
}
```

This is:

1. **Persisted** in `AgentRun.review_context` when the /btw AgentRun is created.
2. **Returned** to the frontend in the /btw response.
3. **Rendered** by the frontend as a "返回复习" link/button.
4. **NOT consumed** by the main review state machine — the session remains at the same step.

### 7.3 /btw Endpoint

```
POST /courses/{course_id}/review/session/{session_id}/btw

Request:
{
  "question": "为什么特征向量不能是零向量？",
  "workflow_hint": "auto"     // "auto" | "quick_answer" | "deep_dive"
}

Response:
{
  "envelope": { ... },          // Same AnswerEnvelope as normal chat
  "return_anchor": {
    "session_id": "rs_abc123",
    "day": 2,
    "item_id": "day2_item1",
    "step_id": "attempt",
    "step_label": "第2天 · 矩阵运算 · 答题中"
  }
}
```

### 7.4 Server-Side Flow

```python
async def handle_btw(
    self,
    course_id: str,
    session_id: str,
    question: str,
    workflow_hint: str = "auto",
) -> BtwResult:
    # 1. Validate session is active and at a btw-enabled step.
    session = self._store.get_review_session_v2(session_id)
    if session is None or session["status"] != "active":
        raise ValueError("No active review session")
    if session["current_step"] not in ("attempt", "feedback", "tutor"):
        raise ValueError("/btw only available during attempt, feedback, or tutor steps")

    # 2. Build return anchor.
    anchor = {
        "session_id": session_id,
        "plan_id": session["plan_id"],
        "day": session["current_day"],
        "item_id": session.get("current_item_id", ""),
        "step_id": session["current_step"],
        "step_label": _build_step_label(session),
    }

    # 3. Route to QuickAnswer or DeepDive.
    #    Use existing services — no review-specific answer logic.
    if workflow_hint == "quick_answer" or (
        workflow_hint == "auto" and not _is_deep_dive_query(question)
    ):
        result = await self._quick_answer.answer(
            course_id=course_id,
            session_id=session_id,      # btw answers go in the main chat session
            turn_id=new_turn_id(),
            query=question,
            review_context=anchor,      # persisted in AgentRun
        )
    else:
        result = await self._deep_dive.answer(
            course_id=course_id,
            session_id=session_id,
            turn_id=new_turn_id(),
            query=question,
            review_context=anchor,
        )

    # 4. Return envelope + anchor. Main review state is unchanged.
    return BtwResult(envelope=result.envelope, return_anchor=anchor)
```

### 7.5 /btw Constraints

- `/btw` is only available during `attempt`, `feedback`, and `tutor` steps (not during `briefing`, `teach`, `recap`, or `done`).
- The /btw question is NOT the review attempt's answer — it's a separate knowledge question.
- `/btw` answer success/failure has no effect on the review state machine.
- User can chain multiple /btw questions in the same step.
- `/btw` reuses the same budget scope as normal chat (`budget_scope="interactive"`).

## 8. Stale + Refresh Handling

### 8.1 Stale Detection

Stale comparison happens at each state machine transition:

```python
def _check_staleness(
    store: SqliteStore,
    plan: dict,
    session: dict,
    course_id: str,
) -> bool:
    """Returns True if the plan or session is stale due to revision change."""
    status = build_knowledge_status(store, course_id)
    current_source = status.source_revision or _NO_SOURCE_REVISION
    current_knowledge = status.knowledge_revision or _NO_KNOWLEDGE_REVISION

    if plan["source_revision"] != current_source:
        return True
    if plan["knowledge_revision"] != current_knowledge:
        return True
    return False
```

### 8.2 Actions on Stale Detection

| When Detected | Action |
|---------------|--------|
| On plan read (`GET /review/plan`) | Return plan with `status="stale"` + warning; frontend shows "材料已更新，建议重新生成复习计划" |
| On session start (`POST /review/session/start`) | Refuse to start; return error `"plan_stale"` |
| On advance/answer (mid-session) | Refuse to advance; mark session `stale`; return error `"session_stale"` with `stale_reason` |
| Page refresh (GET session state) | If stale, return stale flag + offer to regenerate plan |

### 8.3 Page Refresh Restore

When the frontend loads a course workspace, it calls:

```
GET /courses/{course_id}/review/session/current
```

Response (if active session exists):

```json
{
  "session": {
    "id": "rs_abc123",
    "current_day": 2,
    "current_step": "attempt",
    "current_item_id": "day2_item1",
    "status": "active"
  },
  "plan": {
    "id": "rp_def456",
    "status": "active",
    "days_count": 5,
    "current_day_items": [...]
  },
  "current_attempt": {
    "id": "ra_ghi789",
    "question_json": {...},
    "status": "awaiting"   // student hasn't submitted yet
  },
  "is_stale": false
}
```

The frontend restores to the exact step. If `status == "awaiting"`, the question card is shown. If `status == "graded"`, the feedback card is shown.

## 9. API Contract

### 9.1 POST /courses/{course_id}/review/plan

Generate a new review plan for the course.

**Request**:
```json
{
  "exam_date": "2026-08-15"
}
```

If `exam_date` is omitted, reads `exam_date` from the course record.

**Response** (200):
```json
{
  "plan": {
    "id": "rp_abc123",
    "course_id": "cs_linear_algebra",
    "exam_date": "2026-08-15",
    "source_revision": "src_20260711_001",
    "knowledge_revision": "kn_20260711_001",
    "days_count": 5,
    "total_kcs": 14,
    "status": "active",
    "plan_json": { ... },
    "plan_summary": "本复习计划覆盖14个核心知识点，分5天完成...",
    "created_at": "2026-07-11T10:00:00Z"
  }
}
```

**Errors**:
- `400`: Invalid `exam_date` (in the past, unparseable)
- `422`: Course has no ready projection (no KCs to build plan from)
- `409`: Active session already exists (must complete or cancel first)

---

### 9.2 GET /courses/{course_id}/review/plan

Get the current plan.

**Response** (200): Same as POST response.

**Response** (200, stale):
```json
{
  "plan": { ... },
  "is_stale": true,
  "stale_reason": "Source revision changed from src_old to src_new. 3 materials added/modified.",
  "active_session_exists": true
}
```

**Response** (404): No plan exists.

---

### 9.3 POST /courses/{course_id}/review/session/start

Start a new review session from the current plan.

**Request**: (empty body)

**Response** (200):
```json
{
  "session_id": "rs_abc123",
  "plan_id": "rp_def456",
  "current_day": 1,
  "current_step": "briefing",
  "day_title": "向量空间基础",
  "day_items_count": 3,
  "day_items": [
    {
      "item_id": "day1_item1",
      "kc_ids": ["kc_abc123"],
      "topic": "向量空间与子空间的定义",
      "priority": 1,
      "estimated_minutes": 15
    }
  ],
  "total_days": 5
}
```

**Errors**:
- `404`: No active plan exists
- `409`: Active session already exists (`session_id` returned in error for forced restart)
- `400`: Plan is stale

---

### 9.4 POST /courses/{course_id}/review/session/{session_id}/advance

Advance the review session to the next step.

**Request**:
```json
{
  "to_step": "teach"       // optional; server validates legal transition
}
```

If `to_step` is omitted, the server determines the next step from the state machine.

**Response** (200) — varies by target step:

**→ teach**:
```json
{
  "current_step": "teach",
  "current_item": {
    "item_id": "day2_item1",
    "topic": "矩阵运算——乘法与转置",
    "kc_ids": ["kc_jkl012"],
    "teaching_brief": "矩阵乘法不满足交换律...",
    "evidence_refs": [...]
  }
}
```

**→ attempt**:
```json
{
  "current_step": "attempt",
  "attempt_id": "ra_ghi789",
  "question": {
    "question_text": "计算下列矩阵的乘积...",
    "question_type": "计算",
    "rubric": { ... },
    "kc_ids": ["kc_jkl012"],
    "difficulty": "medium"
  }
}
```

**→ feedback** (auto-advance after grading):
```json
{
  "current_step": "feedback",
  "attempt_id": "ra_ghi789",
  "grade": {
    "overall": "partial",
    "correct_points": ["正确计算了矩阵乘积"],
    "missing_points": ["未验证结果是否满足结合律"],
    "error_points": [],
    "uncertain_points": []
  },
  "needs_tutor": true,
  "observations_created": 1,
  "next_action": "tutor_makeup"    // "tutor_makeup" | "next_item" | "day_recap" | "done"
}
```

**→ recap**:
```json
{
  "current_step": "recap",
  "current_day": 2,
  "day_summary": "今天复习了矩阵运算、秩和线性方程组，共3个知识点。完成了2道题目。",
  "kc_statuses": {
    "kc_jkl012": "partial",
    "kc_mno345": "correct",
    "kc_pqr678": "incorrect"
  },
  "is_last_day": false
}
```

**Errors**:
- `400`: Invalid transition
- `400`: Session is stale
- `404`: Session not found
- `409`: Session not active

---

### 9.5 POST /courses/{course_id}/review/session/{session_id}/answer

Submit the student's answer to the current attempt.

**Request**:
```json
{
  "answer": "设 A = [1 2; 3 4], B = [5 6; 7 8], 则 AB = [19 22; 43 50]..."
}
```

**Response** (200):
```json
{
  "attempt_id": "ra_ghi789",
  "grade": {
    "overall": "partial",
    "correct_points": [...],
    "missing_points": [...],
    "error_points": [...],
    "uncertain_points": [...],
    "kc_assessment": {
      "kc_jkl012": "partial"
    },
    "learner_observations": [
      {
        "kc_id": "kc_jkl012",
        "type": "missing_condition",
        "confidence": 0.9,
        "detail": "Did not verify associativity"
      }
    ]
  },
  "needs_tutor": true,
  "next_step": "feedback"
}
```

**Errors**:
- `400`: No awaiting attempt exists for this session
- `409`: Session is stale

---

### 9.6 POST /courses/{course_id}/review/session/{session_id}/complete

Complete the review session.

**Response** (200):
```json
{
  "session_id": "rs_abc123",
  "status": "completed",
  "summary": {
    "days_completed": 3,
    "total_attempts": 7,
    "correct_attempts": 4,
    "partial_attempts": 2,
    "incorrect_attempts": 1,
    "observations_count": 5,
    "kcs_covered": 8,
    "started_at": "2026-07-10T09:00:00Z",
    "completed_at": "2026-07-12T18:00:00Z"
  }
}
```

---

### 9.7 POST /courses/{course_id}/review/session/{session_id}/btw

Submit a /btw question within the review session.

**Request**:
```json
{
  "question": "为什么特征向量不能是零向量？",
  "workflow_hint": "auto"
}
```

**Response** (200):
```json
{
  "envelope": {
    "answer": "特征向量定义为满足 Av = λv 的非零向量...",
    "confidence_status": "grounded",
    "answer_source": "material",
    "citations": [...],
    "warnings": []
  },
  "return_anchor": {
    "session_id": "rs_abc123",
    "plan_id": "rp_def456",
    "day": 2,
    "item_id": "day2_item1",
    "step_id": "attempt",
    "step_label": "第2天 · 矩阵运算 · 答题中"
  }
}
```

**Errors**:
- `400`: /btw not available at current step (only available during `attempt`, `feedback`, `tutor`)
- `404`: No active session
- `409`: Session is stale

---

### 9.8 GET /courses/{course_id}/review/session/current

Get the current active session state (for page refresh restore).

**Response** (200):
```json
{
  "has_active_session": true,
  "session": { ... },
  "plan": { ... },
  "current_attempt": { ... },    // null if step is not "attempt"
  "last_grade": { ... },         // null if step is not "feedback"
  "is_stale": false
}
```

**Response** (200, no session):
```json
{
  "has_active_session": false
}
```

---

### 9.9 DELETE /courses/{course_id}/review/session/{session_id}

Cancel the review session.

**Response** (200):
```json
{
  "session_id": "rs_abc123",
  "previous_status": "active",
  "current_status": "cancelled"
}
```

---

### 9.10 GET /courses/{course_id}/review/observations

Get all LearnerObservations for a course.

**Response** (200):
```json
{
  "observations": [
    {
      "id": "lo_abc123",
      "kc_id": "kc_jkl012",
      "kc_name": "矩阵乘法",
      "observation_type": "missing_condition",
      "confidence": 0.9,
      "detail": "Did not verify associativity",
      "session_id": "rs_abc123",
      "created_at": "2026-07-11T10:30:00Z"
    }
  ],
  "total": 5,
  "by_kc": {
    "kc_jkl012": 2,
    "kc_mno345": 1
  }
}
```

## 10. ReviewService Class Design

### 10.1 Class Structure

```python
class ReviewService:
    """Revision-bound conversational review mode with state machine.

    Depends on:
        - SqliteStore (review tables + V2 knowledge reads)
        - V2AgentTools (read Outline, KC, Relation)
        - AuditedChatWriter (for Examiner, Grader, Tutor calls)
        - QuickAnswerService (for /btw child turns)
        - DeepDiveService (for /btw child turns, when deep-dive triggered)
    """

    def __init__(
        self,
        store: SqliteStore,
        tools: V2AgentTools,
        writer: AuditedChatWriter,
        quick_answer: QuickAnswerService,
        deep_dive: DeepDiveService,
        *,
        max_examiner_tokens: int = 1024,
        max_grader_tokens: int = 800,
        max_tutor_tokens: int = 800,
        temperature: float = 0.3,
        default_token_budget: int = 15000,  # 3 model calls max
    ) -> None: ...

    # Plan operations
    async def generate_plan(self, course_id: str, exam_date: str | None = None) -> ReviewPlanV2: ...
    async def get_current_plan(self, course_id: str) -> ReviewPlanV2 | None: ...

    # Session lifecycle
    async def start_session(self, course_id: str) -> ReviewSessionState: ...
    async def advance_session(self, session_id: str, to_step: str | None = None) -> ReviewSessionState: ...
    async def submit_answer(self, session_id: str, answer: str) -> GradingResult: ...
    async def complete_session(self, session_id: str) -> ReviewSessionSummary: ...
    async def cancel_session(self, session_id: str) -> dict: ...
    async def get_current_session(self, course_id: str) -> CurrentSessionState | None: ...

    # /btw
    async def handle_btw(
        self, session_id: str, question: str, workflow_hint: str = "auto"
    ) -> BtwResult: ...

    # Observations
    async def get_observations(self, course_id: str) -> ObservationList: ...

    # Internal
    def _deterministic_plan_scheduler(
        self, exam_date: str, kcs: list, relations: list, outline: dict
    ) -> dict: ...
    def _build_examiner_messages(self, item, evidence_text, retry_context) -> list: ...
    def _build_grader_messages(self, question, user_answer, evidence_text) -> list: ...
    def _build_tutor_messages(self, gaps, kc_defs, evidence_text) -> list: ...
    def _has_gaps(self, grade_json: dict) -> bool: ...
    def _check_staleness(self, plan: dict, course_id: str) -> bool: ...
```

### 10.2 Budget Scoping

| Model Call | `budget_scope` | Max Tokens (Output) |
|------------|---------------|---------------------|
| Examiner | `review` | 1024 |
| Grader | `review` | 800 |
| Tutor make-up | `review` | 800 |
| /btw (quick answer) | `interactive` | (per QuickAnswerService) |
| /btw (deep dive) | `interactive` | (per DeepDiveService) |

The review session's `token_budget` on the `AgentRun` covers all Examiner, Grader, and Tutor calls. Each /btw call creates its own `AgentRun` with its own budget.

### 10.3 What to Reuse

| Component | From | Notes |
|-----------|------|-------|
| `TurnScope` | `app.schemas.turn_scope` | Use with `workflow_kind="review_session"` |
| `AgentRun` / `AgentStep` | `app.schemas.agent_runs` | Same as QuickAnswer / DeepDive |
| `AuditedChatWriter.complete()` | `app.services.audited_chat_writer` | Same pattern, different `purpose` strings |
| `V2AgentTools` | `app.services.v2_agent_tools` | Read-only access to Outline, KC, Relation |
| `build_knowledge_status` | `app.services.knowledge_status` | Stale detection |
| `QuickAnswerService.answer()` | `quick_answer_service` | /btw child turn |
| `DeepDiveService.answer()` | `deep_dive_service` | /btw child turn (deep-dive path) |

### 10.4 What to Create New

| Component | File | Notes |
|-----------|------|-------|
| `ReviewPlanV2` schema | `backend/app/schemas/review.py` | Explicit revision fields, plan_json structure |
| `ReviewSessionV2` schema | `backend/app/schemas/review.py` | State machine tracking |
| `ReviewAttempt` schema | `backend/app/schemas/review.py` | Question + answer + grade |
| `LearnerObservation` schema | `backend/app/schemas/review.py` | Minimal, traceable |
| `GradingResult` schema | `backend/app/schemas/review.py` | Grader output |
| `BtwResult` schema | `backend/app/schemas/review.py` | /btw response |
| `ReviewService` | `backend/app/services/review_service.py` | Main service |
| SQLite migration | `backend/app/db/sqlite_store.py` | Tables + indexes + store methods |
| Review API router | `backend/app/api/review_v2.py` | Endpoints (separate from legacy `review.py`) |
| Tests | `backend/tests/test_review_v2.py` | 10 test scenarios |

### 10.5 Migration Path

The existing `review_plans` and `review_sessions` tables (blob-style, legacy) coexist during V2-F6 development under separate table names (`review_plans_v2`, `review_sessions_v2`). The legacy API (`app/api/review.py`) continues to work with legacy tables until V2-F8 (legacy excision).

## 11. Test Scenarios

### Scenario 1: Happy path — full review day cycle

**Setup**: Course "线性代数" with 4 materials, 14 KCs, 8 prerequisite relations. Exam in 7 days. Plan generated for 7 days.

**Flow**:
1. Generate plan → plan has 7 days, 2 items/day
2. Start session → step = `briefing`, day 1
3. Advance to `teach` → teaching_brief for day1_item1 returned
4. Advance to `attempt` → Examiner generates question
5. Submit correct answer → Grader returns `overall="correct"`, needs_tutor=false
6. Advance to `feedback` → confirms correct, next_action="next_item"
7. Advance through day1_item2 (correct) → next_action="day_recap"
8. Advance to `recap` → summary of day 1 shown, is_last_day=false
9. Advance → day 2, step = `briefing`

**Expected**:
- 2 Examiner calls (one per item)
- 2 Grader calls (one per attempt)
- 0 Tutor calls (no gaps)
- 2 `review_attempt` records, both status="graded"
- 0 `learner_observations` (correct_attempt observations are optional in MVP)
- AgentRun steps: examiner(2), grader(2), verifier(1)
- Plan `status` stays "active"

### Scenario 2: Answer with gaps → tutor make-up → retry

**Setup**: Day 1, item 1. Examiner generates question about "线性无关判定".

**Flow**:
1. Student submits partial answer (missing key condition)
2. Grader returns `overall="partial"`, missing_points includes "行列式为零意味着线性相关"
3. `needs_tutor=true`
4. Student requests make-up → Tutor generates explanation
5. Student submits retry answer → correct this time
6. Grader returns `overall="correct"`
7. Advance to feedback

**Expected**:
- 1 Examiner, 2 Grader, 1 Tutor call (4 model calls for this item)
- 2 `review_attempt` records: first `is_retry=0`, second `is_retry=1`
- 1 `learner_observation` for the initial missing_condition
- `review_attempt.status` transitions: awaiting → graded → retrying → graded
- No state machine deadlock (retry should auto-advance to feedback)

### Scenario 3: Empty answer — trivial grade, no model call

**Setup**: Student clicks submit with empty input.

**Expected**:
- No Grader model call
- `overall="incorrect"`, all key_points in `missing_points`
- `learner_observations` created with type="incorrect_attempt", confidence=1.0
- Tutor make-up offered
- Session advances normally

### Scenario 4: /btw during attempt — child turn, no state advance

**Setup**: Session at `attempt` step for day2_item1.

**Flow**:
1. POST /btw with question "为什么特征向量不能是零向量？"
2. QuickAnswerService.answer() called, returns grounded answer with citations
3. Response includes `return_anchor` with day=2, item_id="day2_item1", step_id="attempt"
4. Main session still at step="attempt", current_item_id unchanged

**Expected**:
- /btw creates AgentRun with `workflow_kind="btw"` and `review_context` containing the anchor
- QuickAnswerService runs normally (retrieval, CRAG, writer, assemble)
- `review_sessions_v2.current_step` unchanged
- Frontend shows /btw answer + "返回复习" button linking to anchor
- Clicking "返回复习" restores the attempt question view
- No `review_attempts` record created for the /btw (it's not an attempt)

### Scenario 5: /btw deep-dive question

**Setup**: Session at `feedback` step. User asks /btw "线性无关、满秩和可逆之间是什么关系？"

**Flow**: Trigger logic detects deep-dive keywords → routes to DeepDiveService.

**Expected**:
- DeepDiveService.answer() runs Scout → Mapper → Tutor → Verifier
- /btw AgentRun has `workflow_kind="btw"`
- Return anchor points to `feedback` step
- Review session unchanged

### Scenario 6: Stale plan — refused on session start

**Setup**:
1. Plan generated with `source_revision="A"`
2. A new material is uploaded, `source_revision` changes to "B"
3. User tries to start a session

**Expected**:
- `POST .../session/start` returns 400 with `error_code="plan_stale"`
- Frontend shows "复习计划基于的课程材料已更新 (版本 A→B)，建议重新生成计划"
- Plan `status` updated to "stale"

### Scenario 7: Stale mid-session — refused on advance

**Setup**:
1. Session active at step="attempt", plan revision="A"
2. Background material processing completes, `source_revision` → "B"
3. User submits answer

**Expected**:
- Server detects staleness (`plan.source_revision != current`)
- Session marked `stale`
- Returns error with `error_code="session_stale"` and `stale_reason`
- Frontend shows warning and offers "重新生成计划" button
- Any in-progress attempt data is preserved (not lost)

### Scenario 8: Page refresh restore — mid-attempt

**Setup**:
1. Session active, current_step="attempt", attempt_id="ra_ghi789", status="awaiting"
2. User refreshes page
3. Frontend calls `GET /review/session/current`

**Expected**:
- Response includes full `session`, `plan`, and `current_attempt` with `question_json`
- Frontend renders the question card with the same question
- No duplicate Examiner call
- If the user had typed partial answer (not submitted), it's lost (MVP limitation)

### Scenario 9: Plan generation — no learning history

**Setup**: Course with 14 KCs, 8 prerequisite relations, 0 LearnerObservations.

**Expected**:
- Plan's kc priority based on topological order + material coverage, NOT on fabricated weak points
- `plan_json.metadata.has_learning_history = false`
- `plan_summary` does NOT contain phrases like "最需要加强", "薄弱环节", "重点突破"
- KC distribution is proportional to prerequisite chain depth
- No KC appears before its prerequisite in the topological order

### Scenario 10: Plan generation — with learning history (future-proof)

**Setup**: Same as Scenario 9 but with existing LearnerObservations (3 incorrect_attempt, 2 missing_condition).

**Expected**:
- In MVP, observations are NOT used for priority (by design)
- `plan_json.metadata.has_learning_history = true`
- Future implementation: KCs with incorrect attempts get higher priority
- Current implementation: observations are stored but ignored by scheduler

## 12. Implementation Notes

### 12.1 Deterministic Scheduler Testing

The plan generation algorithm must be tested for determinism:

```python
def test_plan_deterministic():
    """Same inputs produce same plan_json."""
    plan1 = service._deterministic_plan_scheduler(exam_date, kcs, relations, outline)
    plan2 = service._deterministic_plan_scheduler(exam_date, kcs, relations, outline)
    assert plan1 == plan2
```

### 12.2 Concurrency

- Only one active session per course. `POST .../session/start` checks for existing active session.
- If a session is `active` for >24 hours without progress, it's auto-marked `paused` (optional feature, not MVP).
- MVP: single-worker SQLite. No lease mechanism needed for review sessions (they're lightweight, request-scoped).

### 12.3 SSE for Review Events

The existing SSE contract (`accepted`, `phase`, `token`, `done`, `error`) is reused. Review-specific phase names:

| Phase | Event `phase` value | Notes |
|-------|---------------------|-------|
| Coaching (teach) | `review_coach` | Teaching brief displayed |
| Examining | `review_examiner` | Question generation in progress |
| Grading | `review_grader` | Grading in progress |
| Tutoring | `review_tutor` | Make-up explanation in progress |
| /btw | (standard chat events) | Reuses quick_answer/deep_dive phases |

### 12.4 Edge Cases

1. **Last day of plan**: `recap` → `done` (not `next_day`). Session auto-completes.
2. **Exam date in the past**: Plan generation returns 1 day with "紧急复习" mode. All KCs distributed on a single day.
3. **Zero KCs**: Plan generation refuses with error `"no_knowledge_components"`. Course needs projection before review.
4. **User cancels mid-attempt**: Session is marked `cancelled`. `review_attempt` with `status="awaiting"` stays as-is (may be garbage-collected later).
5. **Retry on last item of day**: Feedback → next_day_recap still triggers after retry completes.
6. **Multiple /btw in same step**: Each creates a separate AgentRun. No limit on count (budget enforces).
7. **/btw during tutor make-up**: Allowed — student can ask clarifying questions about the make-up explanation.
8. **Tutor model call fails**: Degrade gracefully: show "无法生成补充讲解" with Grader's raw missing_points as feedback text.
9. **Examiner returns invalid JSON**: Retry once with a repair prompt (one extra audited call). If still fails, return error.
10. **Grader returns invalid JSON**: Fall back to deterministic assessment: all key_points marked as uncertain, offer manual review.

## 13. Frontend Integration Notes

### 13.1 CourseWorkspace Mode

Review mode is a **mode** of CourseWorkspace, not a separate page. The `ConversationPane` renders either normal chat or review cards depending on the active mode.

```
ConversationPane
  ├─ ChatView (normal chat, quick answer, deep dive)
  └─ ReviewView (review mode)
      ├─ BriefingCard
      ├─ TeachCard
      ├─ AttemptCard (question + answer input)
      ├─ FeedbackCard (grading result + optional tutor)
      ├─ RecapCard
      └─ BtwCard (child turn, with "返回复习" link)
```

### 13.2 ReviewPlan in StudioPane

The `StudioPane` shows the active review plan and progress:

```
StudioPane
  └─ ReviewPlanPanel (when review mode active)
      ├─ PlanOverview (days, progress bar)
      ├─ TodayView (current day's items, status)
      └─ ObservationsPanel (this session's observations)
```

### 13.3 State Synchronization

Frontend uses `GET /review/session/current` on mount to restore state. During active review, it uses the response from advance/answer/btw endpoints to update local state. SSE is used for streaming the `Examiner` and `Tutor` generation phases (same as chat).

---

## Appendix: Comparison with Legacy Review

| Aspect | Legacy (`review_plans`, `review_sessions`, `app/api/review.py`) | V2-F6 |
|--------|------|-------|
| Plan storage | Blob as `data_json` JSON | Normalized V2 table with explicit `source_revision`, `knowledge_revision` |
| Plan generation | LLM generates entire plan | Deterministic scheduler + optional model summary |
| Weak points | Fabricated by LLM from material difficulty | Not fabricated without LearnerObservation data |
| Session state | Minimal (`current_day`, `current_step`, `completed_steps`) | Full state machine with `current_item_id`, transition validation |
| Attempts | Not persisted | `review_attempts` table with question, answer, grade history |
| Grading | LLM generates free-text feedback | Structured `grade_json` with correct/missing/error/uncertain points |
| /btw | Hardcoded `grounded`, `relevance=1.0` | Reuses QuickAnswerService/DeepDiveService with return anchor |
| LearnerObservation | Not implemented | `learner_observations` table, traceable to attempt |
| Stale handling | Not implemented | Revision comparison on every transition |
| Page refresh | State lost | Restored from `GET /review/session/current` |
| Budget | Not tracked | Per-review-run budget with `budget_scope="review"` |
| Course-agnostic | Partially (legacy skeleton-based) | Fully: no subject-specific fields, prompts, or logic |
