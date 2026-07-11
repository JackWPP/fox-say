# V2-F5: Bounded Deep-Dive Multi-Agent Architecture

> **Status**: Architecture decision (design-only, no code modifications)
>
> **Date**: 2026-07-11 (Asia/Shanghai)
>
> **Depends on**: V2-F2 (QuickAnswerService), V2-F4 (frontend refactor)
>
> **Implements**: `docs/course-agent-v2-plan.md` §6.2 `deep_dive` workflow

## 1. Decision Summary

Deep-dive questions ("what's the relationship between linear independence, full rank, and invertibility?") span multiple chapters, concepts, and knowledge-component relationships. A single-shot retrieval + writer call is insufficient because:

1. Cross-chapter evidence may belong to different sections with low text similarity to the query.
2. The writer model cannot reason about KC/relation topology without loading the entire course — which would violate boundedness.
3. Without a structured mapper phase, the writer either hallucinates connections or produces parallel summaries rather than synthesized analysis.

The proposed `DeepDiveService` adds exactly **one** pre-writer text call (the Mapper) and one post-writer validation step (the Verifier), for a total of **2 text model calls** (Mapper + Tutor). Scout retrieval is not a text call. Verifier is server-side only.

## 2. Trigger Logic

A student question routes to `DeepDiveService` (instead of `QuickAnswerService`) when **any** of the following is true:

### 2.1 Keyword-based trigger (deterministic, no model call)

The query contains cross-chapter or comparative keywords. Apply Unicode NFKC normalization and casefolding before matching. Match against these patterns:

| Pattern | Chinese keywords | English keywords (normalized) |
|---------|-----------------|-------------------------------|
| Cross-chapter relationship | `之间`, `关系`, `联系`, `关联`, `跨章节` | `relationship`, `connection`, `across chapter` |
| Comparison | `区别`, `比较`, `对比`, `异同`, `vs`, `相比` | `difference`, `compare`, `versus`, `vs` |
| System / composite | `体系`, `系统`, `框架`, `整体`, `总结` | `system`, `framework`, `overview`, `summary` |
| How related | `有什么关系`, `如何联系`, `怎样关联` | `how are.*related`, `relation between` |

A single match triggers deep-dive. The keyword list is stored as a module-level constant, not in a database or config file, because it changes with product requirements, not runtime configuration.

### 2.2 Retrieval-based trigger (after initial retrieval)

If keyword matching returns false, perform a standard retrieval (same `retrieve_current_fragments` call). If the `RetrievalOutcome` confidence is `ambiguous` AND the hits span **≥2 distinct `section_id` values** (determined by reading section membership from `V2AgentTools.get_current_outline`), trigger deep-dive.

This is a **server-side** decision: the API caller can set `workflow_hint` to `"auto"` (default), `"quick_answer"`, or `"deep_dive"`. An explicit `workflow_hint` always overrides the server heuristic.

### 2.3 Course materials without KC/Relation projection

If the course's `projection_status` is not `"ready"` (no Terms, KCs, or Relations exist yet), the Mapper phase is skipped entirely. The workflow degrades to `quick_answer` with a `deep_dive` AgentRun label and a `skipped_mapper` step. This is a legitimate outcome for text-heavy courses.

## 3. Sequence Diagram

```
┌──────────┐     ┌────────────────┐     ┌──────────────┐     ┌───────────────┐     ┌───────────────┐     ┌──────────────┐
│ Caller   │     │ DeepDiveService│     │ SqliteStore  │     │ Retrieval     │     │ V2AgentTools  │     │ AuditedChat  │
│          │     │                │     │              │     │               │     │               │     │ Writer       │
└────┬─────┘     └───────┬────────┘     └──────┬───────┘     └───────┬───────┘     └───────┬───────┘     └──────┬─────┘
     │                   │                     │                     │                     │                    │
     │ answer(query)     │                     │                     │                     │                    │
     │──────────────────>│                     │                     │                     │                    │
     │                   │                     │                     │                     │                    │
     │                   │ 1. Build TurnScope  │                     │                     │                    │
     │                   │─────────────────────│                     │                     │                    │
     │                   │<────────────────────│                     │                     │                    │
     │                   │                     │                     │                     │                    │
     │                   │ 2. Create AgentRun  │                     │                     │                    │
     │                   │  (workflow=deep_dive)│                    │                     │                    │
     │                   │─────────────────────│                     │                     │                    │
     │                   │<────────────────────│                     │                     │                    │
     │                   │                     │                     │                     │                    │
     │                   │ 3. PHASE: scout     │                     │                     │                    │
     │                   │  (agent_role="scout")│                    │                     │                    │
     │                   │  retrieve_current_  │                     │                     │                    │
     │                   │  fragments(...)     │                     │                     │                    │
     │                   │─────────────────────────────────────────>│                     │                    │
     │                   │<─── RetrievalOutcome ─────────────────────│                     │                    │
     │                   │  Build EvidencePack │                     │                     │                    │
     │                   │                     │                     │                     │                    │
     │                   │  [If unavailable → error envelope, return]│                     │                    │
     │                   │                     │                     │                     │                    │
     │                   │ 4. PHASE: mapper    │                     │                     │                    │
     │                   │  (agent_role="mapper")                   │                     │                    │
     │                   │  Read bounded Terms/│                     │                     │                    │
     │                   │  KCs/Relations/Outline                   │                     │                    │
     │                   │──────────────────────────────────────────────────────────>│                    │
     │                   │<─── bounded DTOs ──────────────────────────────────────────│                    │
     │                   │                     │                     │                     │                    │
     │                   │  [If projection not ready → skip_mapper] │                     │                    │
     │                   │                     │                     │                     │                    │
     │                   │  Build mapper msgs  │                     │                     │                    │
     │                   │  AuditedChatWriter.complete(run, purpose="deep_dive_mapper")       │                    │
     │                   │────────────────────────────────────────────────────────────────────>│
     │                   │<─── AuditedTextResult (mapper JSON) ────────────────────────────────│
     │                   │                     │                     │                     │                    │
     │                   │  [If mapper fails → degrade to quick_answer]                      │                    │
     │                   │                     │                     │                     │                    │
     │                   │ 5. PHASE: tutor     │                     │                     │                    │
     │                   │  (agent_role="tutor")│                    │                     │                    │
     │                   │  Build tutor msgs   │                     │                     │                    │
     │                   │  (evidence + mapper output)                                     │                    │
     │                   │  AuditedChatWriter.complete(run, purpose="deep_dive_tutor")      │                    │
     │                   │────────────────────────────────────────────────────────────────────>│
     │                   │<─── AuditedTextResult (tutor JSON) ───────────────────────────────────│
     │                   │                     │                     │                     │                    │
     │                   │  [If tutor fails → unavailable envelope] │                     │                    │
     │                   │                     │                     │                     │                    │
     │                   │ 6. PHASE: verifier  │                     │                     │                    │
     │                   │  (agent_role="verifier")                  │                     │                    │
     │                   │  - Parse tutor JSON │                     │                     │                    │
     │                   │  - Validate cited fragment_ids vs allowed set                    │                    │
     │                   │  - Check confidence/answer_source consistency                    │                    │
     │                   │  - Check stale revision                                         │                    │
     │                   │  - assemble_answer_envelope(...)                                 │                    │
     │                   │                     │                     │                     │                    │
     │                   │ 7. Update run status│                     │                     │                    │
     │                   │─────────────────────│                     │                     │                    │
     │                   │                     │                     │                     │                    │
     │  DeepDiveResult    │                     │                     │                     │                    │
     │<──────────────────│                     │                     │                     │                    │
     │                   │                     │                     │                     │                    │
```

## 4. Phase Contracts

### 4.1 Phase 1: Scout (retrieval, no model call)

| Property | Value |
|----------|-------|
| `agent_role` | `"scout"` |
| `step_type` | `"retrieve"` |
| `output_type` | `"evidence_pack"` |
| Model call | No |
| Persisted | AgentStep (status, input_fingerprint) |

**Input**: `course_id`, `query`, `scope` (selected material IDs if scope_mode=selected)

**Output**: `EvidencePack` with `selected_hits` up to `max_scout_hits` (default 8, higher than quick_answer's 5 because cross-chapter questions benefit from broader retrieval).

**Implementation**: Identical to `QuickAnswerService`'s retrieval step. Reuses `retrieve_current_fragments` and `_build_evidence_pack`.

**Edge case**: If retrieval is `unavailable`, return `unavailable` envelope immediately — same as quick_answer.

### 4.2 Phase 2: Mapper (1 text model call)

| Property | Value |
|----------|-------|
| `agent_role` | `"mapper"` |
| `step_type` | `"generate"` |
| `output_type` | `"course_map"` |
| Model call | Yes (1 audited text call) |
| `purpose` | `"deep_dive_mapper"` |
| Persisted | AgentStep (model_call_id, input_fingerprint) |

**Input**:
1. `query` — the student's question
2. `course_outline` — `CourseOutline.sections[]` (each: `section_id`, `title`, `heading_path`, `ordinal`). **No evidence refs** passed to mapper to keep token usage bounded.
3. `terms` — up to `max_bounded_items` (default 10) Term objects, selected as follows:
   - Filter terms whose `canonical_name` or `definition` has any token overlap with the query (casefolded Unicode NFKC)
   - If ≤10 match, take all; if >10, take the first 10 sorted alphabetically by `canonical_name`
4. `kcs` — up to `max_bounded_items` (default 10) KnowledgeComponent objects, selected as follows:
   - Filter KCs whose `name` or `definition` has any token overlap with the query
   - If ≤10 match, take all; if >10, take the first 10 sorted by `section_id` then `name`
5. `relations` — up to `max_bounded_items` (default 10) KCRelation objects, selected as:
   - Only relations where both `source_kc_id` and `target_kc_id` are among the selected KCs
   - If >10, prioritize `prerequisite` over `related` relations

All items are read via `V2AgentTools` with the current `course_id`. The mapper **MUST NOT** receive the full course list.

**Output** (JSON, parsed server-side):
```json
{
  "relevant_sections": [
    {"section_id": "sec_xxx", "title": "向量空间", "relevance_reason": "定义线性无关的章节"},
    {"section_id": "sec_yyy", "title": "矩阵与方程组", "relevance_reason": "定义满秩和可逆的章节"}
  ],
  "relevant_kcs": [
    {"kc_id": "kc_xxx", "name": "线性无关", "role": "source_concept"},
    {"kc_id": "kc_yyy", "name": "满秩", "role": "target_concept"}
  ],
  "key_relationships": [
    {
      "description": "线性无关的向量组构成满秩矩阵",
      "involved_kc_ids": ["kc_xxx", "kc_yyy"],
      "evidence_supported": true
    }
  ],
  "narrative_bridge": "线性无关、满秩和可逆是矩阵性质的三个递进层次：..."
}
```

**Fields**:
- `relevant_sections`: Sections from the course outline that contain relevant material. `relevance_reason` explains why (1 sentence max).
- `relevant_kcs`: KCs from the bounded list that are relevant. `role` is `"source_concept"`, `"target_concept"`, `"bridge_concept"`, or `"context"`.
- `key_relationships`: Synthesized relationships between the KCs. `evidence_supported` means the mapper found supporting structure in the Relations list or outline. Must be `false` if the mapper is inferring from general knowledge.
- `narrative_bridge`: A 2-3 sentence natural language bridge connecting the concepts.

**Skipping the Mapper**: If `projection_status != "ready"` (no Terms/KCs/Relations exist), the mapper step is recorded as `skipped` with a reason. The workflow proceeds directly to Tutor with only evidence context.

### 4.3 Phase 3: Tutor (1 text model call)

| Property | Value |
|----------|-------|
| `agent_role` | `"tutor"` |
| `step_type` | `"generate"` |
| `output_type` | `"answer_draft"` |
| Model call | Yes (1 audited text call) |
| `purpose` | `"deep_dive_tutor"` |
| Persisted | AgentStep (model_call_id, input_fingerprint) |

**Input**:
1. `query` — the student's question
2. `evidence` — `EvidencePack` (same format as quick_answer, up to `max_scout_hits` hits)
3. `mapper_output` — parsed Mapper JSON (or `None` if mapper was skipped)
4. `allowed_fragment_ids` — from the Scout's EvidencePack

**Output** (JSON, same format as QuickAnswerService's writer):
```json
{
  "answer": "完整的结构化回答...",
  "citation_fragment_ids": ["frag_id_1", "frag_id_2"]
}
```

The Tutor receives both evidence AND mapper output. This is the key architectural difference from quick_answer: the Tutor reasons about cross-chapter relationships using the Mapper's structured outline, but grounds every factual claim in the Scout's evidence fragments.

**If mapper was skipped**: The tutor receives only evidence context, identical to quick_answer. The prompt instructs it to compare/contrast based solely on retrieved evidence.

### 4.4 Phase 4: Verifier (server-side, no model call)

| Property | Value |
|----------|-------|
| `agent_role` | `"verifier"` |
| `step_type` | `"verify"` |
| `output_type` | `"answer_envelope"` |
| Model call | No |
| Persisted | AgentStep (status, input_fingerprint) |

**Performs the following checks, in order**:

1. **Parse tutor response**: Same `_parse_writer_response` from `quick_answer_service.py`. If JSON is malformed, use raw text as answer with warning.

2. **Citation allow-list validation**: Every `citation_fragment_id` from the Tutor response is checked against `evidence.allowed_fragment_ids`. Unknown IDs are rejected with `unknown_citation_selection` warning. This reuses `assemble_answer_envelope` from `app.services.answer_envelope`.

3. **Citation uniqueness**: The Verifier also checks that for cross-chapter relationships described in the answer, at least two distinct `material_id` or `section_id` values are cited. Failing this check produces a warning (`insufficient_cross_section_citation`) but does not reject the answer — the answer is still valid, just flagged for quality review.

   **Implementation detail**: After `assemble_answer_envelope` returns, count unique `(citation.evidence.material_id, citation.evidence.fragment_id)` tuples across all resolved citations. If count < 2 and mapper was not skipped, add `insufficient_cross_section_citation` warning. The section_id check requires joining through `SourceFragment.heading_path` which is available from the `RetrievalHit` → `EvidenceRef` → `locator`. For MVP, checking `material_id` diversity is sufficient.

4. **Confidence/answer_source consistency**:
   - If retrieval `confidence == "out_of_scope"`, force `answer_source = "supplementary"` (no citations).
   - If mapper was skipped: always use the raw confidence from retrieval.
   - If mapper ran successfully: the answer may still be `material` even for `ambiguous` retrieval, because the mapper adds structure. The envelope's `confidence_status` reflects the original retrieval confidence; the `answer_source` may be `material` as long as valid citations exist.

5. **Stale revision check**: Same as QuickAnswerService — compare `current_status.source_revision` with `scope.source_revision`. If different, mark run as `stale`.

6. **Envelope assembly**: Call `assemble_answer_envelope(outcome, answer=answer_text, citation_fragment_ids=citation_ids)`.

## 5. Prompt Templates

### 5.1 Mapper System Prompt

```
你是 FoxSay 学习助手的"课程地图师"——一只擅长理清知识脉络的狐狸。

你会收到：
1. 一个学生的跨章节问题
2. 课程的大纲结构（章节标题和顺序）
3. 一小部分与问题可能相关的术语和知识点（最多各10条）
4. 一小部分知识点之间的关系（最多10条）

你的任务：
1. 识别问题涉及哪些章节（从大纲中选择）
2. 从提供的术语/知识点列表中选出真正相关的，并说明它们扮演的角色
3. 基于提供的知识点关系，描述它们之间的联系
4. 用2-3句话构建一个"叙事桥梁"，说明这些概念如何关联

规则：
- 只能引用提供的大纲章节、术语、知识点和关系，不得编造不存在的章节、概念或关系
- 如果提供的知识点关系中缺少某些联系，在 key_relationships 中标记 evidence_supported=false
- 如果知识点列表中缺少关键概念，在 relevant_kcs 中依然可以提及，但无法给出 kc_id
- 保持简洁：每个 relevance_reason 不超过一句话
- 保持狐狸的个性：聪明、有条理，但不要变成无个性的数据分析师

请以 JSON 格式返回：
{
  "relevant_sections": [
    {"section_id": "...", "title": "...", "relevance_reason": "..."}
  ],
  "relevant_kcs": [
    {"kc_id": "...", "name": "...", "role": "source_concept|target_concept|bridge_concept|context"}
  ],
  "key_relationships": [
    {
      "description": "...",
      "involved_kc_ids": ["...", "..."],
      "evidence_supported": true
    }
  ],
  "narrative_bridge": "..."
}
```

### 5.2 Mapper User Message Template

```python
def _build_mapper_user_message(
    query: str,
    outline_sections: list[dict],
    bounded_terms: list[dict],
    bounded_kcs: list[dict],
    bounded_relations: list[dict],
) -> str:
    parts = [f"学生问题：{query}"]

    if outline_sections:
        parts.append(f"\n课程大纲（共{len(outline_sections)}节）：")
        for sec in outline_sections[:20]:  # hard cap at 20 sections
            parts.append(f"  · [{sec['section_id']}] {sec['title']} (第{sec['ordinal']+1}节)")

    if bounded_terms:
        parts.append(f"\n相关术语（共{len(bounded_terms)}条）：")
        for term in bounded_terms:
            parts.append(f"  · [{term['term_id']}] {term['canonical_name']}（{term['term_kind']}）：{term['definition'][:120]}")

    if bounded_kcs:
        parts.append(f"\n相关知识点（共{len(bounded_kcs)}条）：")
        for kc in bounded_kcs:
            parts.append(f"  · [{kc['kc_id']}] {kc['name']}（{kc['kind']}）：{kc['definition'][:120]}")

    if bounded_relations:
        parts.append(f"\n知识点关系（共{len(bounded_relations)}条）：")
        for rel in bounded_relations:
            parts.append(f"  · {rel['source_kc_id']} --[{rel['relation_type']}]--> {rel['target_kc_id']}")

    parts.append('\n请以 JSON 格式返回课程地图分析。')
    return "\n".join(parts)
```

### 5.3 Tutor System Prompt

```
你是 FoxSay 学习助手——一只聪明、有点狡黠但靠谱的课程学习伙伴。

你会收到：
1. 一个学生的跨章节问题
2. 课程材料中的证据片段（Scout 检索结果）
3. 课程地图师的分析结果（识别了相关章节、知识点和关系）

请综合证据和地图分析，给学生一个结构化的回答。

规则：
1. 优先基于提供的课程材料证据回答。
2. 对比多个概念时，先分别解释每个概念，再说明它们的关系。
3. 每个来自课程材料的事实性声明，必须提供来源引用（使用提供的片段 ID）。
4. 只能引用提供的片段 ID（allowed_fragment_ids），不得编造片段 ID、文件名或定位信息。
5. 地图师的叙事桥梁提供了概念关系的方向，但事实依据必须来自证据片段。
6. 如果没有证据片段，说明课程材料未覆盖此内容，以下为通用理解，建议对照教材确认。
7. 保持狐狸的个性：聪明、有点小狡黠，但真诚有帮助，不要变成无个性的通用助手。

请以 JSON 格式返回回答：
{"answer": "你的回答文本", "citation_fragment_ids": ["片段ID1", "片段ID2"]}

- answer：你的回答文本。建议结构：先分别解释概念，再分析关系，最后总结。
- citation_fragment_ids：你引用的片段 ID 列表，只能从提供的可引用片段 ID 中选择。
  如果没有证据或不需要引用，返回空列表。
```

### 5.4 Tutor User Message Template

```python
def _build_tutor_user_message(
    query: str,
    evidence: EvidencePack,
    mapper_output: dict | None,  # parsed Mapper JSON
) -> str:
    parts = [f"学生问题：{query}"]

    # Evidence section (same as quick_answer)
    if evidence.context_text:
        parts.append(f"\n课程材料证据：\n{evidence.context_text}")
    else:
        parts.append("\n课程材料证据：\n（本课程材料未覆盖此内容）")

    # Mapper output section (deep-dive specific)
    if mapper_output:
        parts.append("\n课程地图分析：")
        narrative = mapper_output.get("narrative_bridge", "")
        if narrative:
            parts.append(f"  概念关系概述：{narrative}")

        sections = mapper_output.get("relevant_sections", [])
        if sections:
            sec_names = [s.get("title", "?") for s in sections]
            parts.append(f"  相关章节：{', '.join(sec_names)}")

        kcs = mapper_output.get("relevant_kcs", [])
        if kcs:
            kc_names = [k.get("name", "?") for k in kcs]
            parts.append(f"  相关知识点：{', '.join(kc_names)}")

        rels = mapper_output.get("key_relationships", [])
        if rels:
            parts.append("  知识点关系：")
            for rel in rels:
                desc = rel.get("description", "")
                supported = "（有证据支撑）" if rel.get("evidence_supported") else "（推论）"
                parts.append(f"    · {desc} {supported}")

    # Allowed fragment IDs
    if evidence.allowed_fragment_ids:
        ids_str = ", ".join(evidence.allowed_fragment_ids)
        parts.append(f"\n可引用的片段 ID：{ids_str}")
    else:
        parts.append("\n可引用的片段 ID：（无）")

    parts.append('\n请以 JSON 格式返回：{"answer": "...", "citation_fragment_ids": [...]}')
    return "\n".join(parts)
```

## 6. Failure Modes and Degradation

### 6.1 Decision table

| Failure | Detection | Action | Envelope state |
|---------|-----------|--------|---------------|
| Retrieval unavailable | `outcome.retrieval_availability == "unavailable"` | Return unavailable envelope immediately | `unavailable`, `answer_source=supplementary` |
| Projection not ready (no Terms/KCs/Relations) | `projection_status != "ready"` | Skip mapper, proceed with Tutor using only evidence | Normal CRAG states, `skipped_mapper` step |
| Mapper model call fails | `AuditedModelCallError` | Degrade to quick_answer mode: call Tutor with only evidence, no mapper output | Normal CRAG states, `mapper_degration` warning |
| Mapper returns invalid JSON | `json.JSONDecodeError` on mapper output | Proceed to Tutor with `mapper_output=None`, add warning | Normal CRAG states, `mapper_parse_warning` |
| Tutor model call fails | `AuditedModelCallError` | Return unavailable envelope (mapper result is discarded) | `unavailable` |
| Both Mapper and Tutor fail | Both fail | Return unavailable envelope | `unavailable` |
| Stale source revision | `current_source_revision != scope.source_revision` | Assemble envelope, mark run as `stale` | `stale` status, warning added |
| All cited fragment IDs rejected | Verifier drops all citations | Fallback to all allowed evidence (same as quick_answer) | `fallback_to_allowed_evidence` warning |
| Budget exhausted before mapper call | `reserve_agent_run_model_call` returns `rejected` | Return unavailable envelope | `unavailable`, `error_code=budget_exhausted` |

### 6.2 Degradation to QuickAnswer

When the mapper fails (model error, invalid JSON, budget exhaustion), the service records the failure but does NOT mark the entire run as failed. Instead:

1. Record the mapper step as `failed` with the error.
2. Add a warning: `"Mapper phase failed, degraded to single-shot quick answer. Answer may lack cross-chapter synthesis."`
3. Proceed to Tutor phase with `mapper_output=None`.
4. The Tutor call uses the deep-dive Tutor prompt but without the mapper output section — effectively identical to the quick_answer prompt (though slightly different system prompt wording).

This ensures the student always gets some answer rather than an error. The `confidence_status` in the envelope reflects the retrieval confidence, not the mapper failure.

### 6.3 Skipping Mapper Deliberately

When projection is not ready, the mapper step is recorded as `skipped` (not `failed`):
- `status: "skipped"`
- `output_type: null`
- `error: "Course projection not ready; no Terms/KCs/Relations available for deep-dive mapping"`

This is a legitimate path, not a degradation. Text-heavy courses without formalized KC structures can still do deep-dive by comparing evidence fragments directly.

## 7. Token Budget Enforcement

### 7.1 Hard caps (module-level constants)

```python
MAPPER_MAX_INPUT_TOKENS = 8000
MAPPER_MAX_OUTPUT_TOKENS = 1500
TUTOR_MAX_INPUT_TOKENS = 8000
TUTOR_MAX_OUTPUT_TOKENS = 1500
MAX_BOUNDED_ITEMS = 10       # max Terms, KCs, Relations each
MAX_OUTLINE_SECTIONS = 20    # max sections sent to mapper
MAX_SCOUT_HITS = 8           # max evidence hits for deep-dive
```

### 7.2 Input token estimation

Before each model call, estimate the input token count using the same `_conservative_input_token_upper_bound` from `audited_text_model.py`, which is already used by `AuditedChatWriter.complete()` for the `input_token_upper_bound` field in the reservation request.

This function uses a conservative 4 chars/token estimate on the canonical request (UTF-8 bytes ÷ 4). It is already called before the provider call to validate budget.

### 7.3 Truncation strategy

Apply truncation in the **service layer** (before building messages for the writer), in this priority order:

#### Mapper input truncation (order of dropping):
1. **Outline sections**: If >20, keep first 20 sections (by ordinal). The outline is already sorted.
2. **Terms/KCs/Relations**: Each capped at `MAX_BOUNDED_ITEMS` (10) during selection. No additional truncation needed.
3. **Term/KC definition length**: Each definition is already truncated to 120 characters in the user message template.
4. **If the serialized message still exceeds 8000 token estimate**: Drop relations first, then drop KCs, then drop terms, then drop outline sections to 10. Never drop below 5 outline sections.

#### Tutor input truncation (order of dropping):
1. **Evidence fragments**: If >8, keep top 8 by score. This is already enforced by `MAX_SCOUT_HITS`.
2. **Mapper output**: If the mapper's `narrative_bridge` exceeds 500 characters, truncate to 500 chars with `"..."`. Truncate `key_relationships` to 5 items max.
3. **Evidence text**: Each fragment's `canonical_text` is already bounded by the source fragment size. If individual fragments exceed 1000 chars, truncate with `"...[truncated]"`.
4. **If the serialized message still exceeds 8000 token estimate**: Reduce scout hits from 8 → 5 → 3. At 3 hits, stop truncating and proceed (risk of some evidence exceeding context window is accepted).

### 7.4 Budget scoping

Both mapper and tutor calls use `budget_scope="interactive"` (same as quick_answer). The deep-dive run's `token_budget` is set at run creation. If the course's interactive budget is exhausted, the reservation is rejected before any provider call.

The per-run `token_budget` field on `AgentRun` is advisory for auditing; the actual gate is the course-level budget check in `reserve_agent_run_model_call`.

## 8. DeepDiveResult

```python
@dataclass(frozen=True)
class DeepDiveResult:
    """The complete outcome of one deep-dive turn."""
    run_id: str
    envelope: AnswerEnvelope
    evidence: EvidencePack
    mapper_ran: bool
    mapper_call_id: str | None = None
    tutor_call_id: str | None = None
    run_status: str = "completed"
    error_code: str | None = None
    error_detail: str | None = None
    warnings: list[str] = field(default_factory=list)
```

`mapper_ran` is `True` if the mapper phase executed successfully, `False` if skipped or degraded. Frontend can use this to decide whether to show the "Course Mapper" phase card.

## 9. DeepDiveService Class Design

```python
class DeepDiveService:
    """Bounded deep-dive workflow: Scout → Mapper → Tutor → Verifier."""

    def __init__(
        self,
        store: SqliteStore,
        writer: AuditedChatWriter,
        tools: V2AgentTools,
        *,
        max_scout_hits: int = 8,
        max_bounded_items: int = 10,
        mapper_max_input_tokens: int = 8000,
        mapper_max_output_tokens: int = 1500,
        tutor_max_input_tokens: int = 8000,
        tutor_max_output_tokens: int = 1500,
        temperature: float | None = 0.3,
        default_token_budget: int = 20000,  # higher than quick_answer's 10000
    ) -> None: ...

    async def answer(
        self,
        *,
        course_id: str,
        session_id: str,
        turn_id: str,
        query: str,
        selected_material_ids: list[str] | None = None,
        selected_note_ids: list[str] | None = None,
        review_context: dict[str, Any] | None = None,
        token_budget: int | None = None,
        # Injection points for tests
        qdrant_store: Any | None = None,
        embed_query: Any | None = None,
        enable_vector: bool = False,
    ) -> DeepDiveResult: ...
```

### 9.1 Constructor differences from QuickAnswerService

- Takes an additional `tools: V2AgentTools` parameter (for reading Outline/Terms/KCs/Relations)
- `max_scout_hits` defaults to 8 (vs 5 for quick_answer)
- `default_token_budget` defaults to 20000 (vs 10000, because 2 model calls)
- Has mapper-specific token caps

### 9.2 Method structure `answer()`

The method follows the same structure as `QuickAnswerService.answer()`:

1. Build `TurnScope` (workflow_kind="deep_dive")
2. Create `AgentRun`
3. **Scout phase**: retrieve → build EvidencePack → if unavailable, return error envelope
4. **Read bounded tools**: Skip if projection not ready
5. **Mapper phase**: build messages → call writer → parse JSON
   - On failure: record failed step, set `mapper_ran=False`, proceed to Tutor
6. **Tutor phase**: build messages (with or without mapper output) → call writer → parse JSON
   - On failure: return unavailable envelope
7. **Verifier phase**: parse, validate, assemble envelope
8. Check stale revision
9. Return `DeepDiveResult`

## 10. Test Scenarios

### Scenario 1: Successful deep-dive — grounded retrieval + mapper + tutor

**Setup**: Course "线性代数" with 4 materials, full projection ready (Outline, Terms, KCs, Relations). Retrieval returns 6 hits spanning 2 materials (A: 向量空间, B: 矩阵与方程组), confidence="grounded" (score 0.85).

**Query**: "线性无关、满秩和可逆之间是什么关系？"

**Mock data**:
- Fake provider returns valid Mapper JSON:
  ```json
  {
    "relevant_sections": [...2 sections...],
    "relevant_kcs": [...3 KCs...],
    "key_relationships": [...2 relations...],
    "narrative_bridge": "..."
  }
  ```
- Fake provider returns valid Tutor JSON:
  ```json
  {
    "answer": "线性无关、满秩和可逆是矩阵理论中三个递进的性质...",
    "citation_fragment_ids": ["frag_a_1", "frag_b_2"]
  }
  ```

**Expected**:
- `DeepDiveResult.run_status == "completed"`
- `DeepDiveResult.mapper_ran == True`
- `envelope.confidence_status == "grounded"`
- `envelope.answer_source == "material"`
- `envelope.citations` has 2 entries
- AgentRun has 4 steps: scout, mapper, tutor, verifier (all completed)
- 2 model_call_audit records (mapper + tutor)

### Scenario 2: Successful deep-dive — ambiguous retrieval with successful mapper

**Setup**: Retrieval returns 4 hits with confidence="ambiguous" (score 0.62). Hits span 3 distinct section IDs.

**Expected**:
- `envelope.confidence_status == "ambiguous"` (preserves original retrieval confidence)
- `envelope.answer_source == "material"` (mapper added structure, citations still exist)
- `envelope.warnings` may include `ambiguous_confidence_notice`

### Scenario 3: Mapper fails — degradation to quick-answer

**Setup**: Fake provider raises `FakeProviderError("Rate limit", status_code=429)` on mapper call.

**Expected**:
- `DeepDiveResult.mapper_ran == False`
- `DeepDiveResult.run_status == "completed"` (NOT failed)
- `DeepDiveResult.warnings` includes "Mapper phase failed, degraded to single-shot quick answer"
- Tutor call still succeeds (uses only evidence, no mapper output)
- `envelope.answer_source == "material"` (if citations exist)
- AgentRun steps: scout (completed), mapper (failed), tutor (completed), verifier (completed)
- Exactly 1 model_call_audit record (tutor only; mapper audit record exists but is failed)

### Scenario 4: Both mapper and tutor fail — unavailable envelope

**Setup**: Fake provider raises errors on both mapper and tutor calls.

**Expected**:
- `DeepDiveResult.run_status == "failed"`
- `envelope.retrieval_availability == "unavailable"` (Tutor failure treated as system unavailability)
- `envelope.answer_source == "supplementary"`
- `envelope.citations == []`
- `envelope.answer` contains error message visible to user
- AgentRun steps: scout (completed), mapper (failed), tutor (failed), verifier (completed with unavailable)

### Scenario 5: Projection not ready — mapper skipped

**Setup**: Course "学术写作基础" has ready source fragments but `projection_status != "ready"` (no Terms/KCs/Relations compiled). Retrieval returns 3 hits, confidence="grounded".

**Query**: "论点组织和论据呈现有什么区别？"

**Expected**:
- `DeepDiveResult.mapper_ran == False` (but not an error)
- AgentRun step: mapper `status == "skipped"` with descriptive `error` field
- Tutor runs with only evidence (no mapper output)
- `envelope.answer_source == "material"` (citations from evidence)
- No warnings about mapper failure (it was deliberately skipped)

### Scenario 6: Citation forgery rejection

**Setup**: Mapper succeeds. Tutor returns:
```json
{
  "answer": "valid answer text",
  "citation_fragment_ids": ["frag_a_1", "fake_frag_id", "frag_b_2"]
}
```
where `"fake_frag_id"` is NOT in the allowed set.

**Expected**:
- Verifier rejects `"fake_frag_id"` (unknown_citation_selection warning)
- `envelope.citations` has 2 entries (`frag_a_1`, `frag_b_2`)
- `envelope.warnings` includes one `unknown_citation_selection` warning
- Answer still succeeds (citation rejection does not fail the run)

### Scenario 7: Budget exhausted

**Setup**: Course's interactive token budget is at its limit. The `reserve_agent_run_model_call` for the mapper returns `status="rejected"`.

**Expected**:
- Mapper step fails with `model_call_rejected`
- Degradation proceeds: Tutor attempt also fails with same error (no budget left)
- `DeepDiveResult.run_status == "failed"`
- `envelope.retrieval_availability == "unavailable"`
- `DeepDiveResult.error_code == "budget_exhausted"`

### Scenario 8: Out-of-scope deep-dive with supplementary answer

**Setup**: Retrieval confidence="out_of_scope" (score 0.30). Course has no relevant material.

**Query**: "光电效应和波粒二象性有什么关系？"

**Expected**:
- Retrieval outcome: `confidence="out_of_scope"`, `hits=[]`
- Since retrieval has no hits, the service should recognize this after the scout phase
- Skip mapper and tutor: the answer must be supplementary regardless
- `envelope.answer_source == "supplementary"`
- `envelope.confidence_status == "out_of_scope"`
- `envelope.citations == []`
- Answer text includes the required supplementary disclaimer
- AgentRun steps: scout (completed), mapper (skipped, reason="out_of_scope_no_evidence"), tutor (skipped), verifier (completed)
- No model calls made (neither mapper nor tutor)

## 11. Implementation Notes

### 11.1 What to reuse

| Component | Reused from | Notes |
|-----------|-------------|-------|
| `_build_turn_scope` | `QuickAnswerService` | Change `workflow_kind` to `"deep_dive"` |
| `_create_run`, `_create_step`, `_complete_step`, `_fail_step` | `QuickAnswerService` | Identical |
| `retrieve_current_fragments` | `app.services.retrieval` | May use higher `limit` |
| `_build_evidence_pack` | `quick_answer_service` | Same function |
| `AuditedChatWriter.complete()` | `audited_chat_writer` | Different `purpose` string |
| `assemble_answer_envelope` | `app.services.answer_envelope` | Identical |
| `_parse_writer_response` | `quick_answer_service` | Identical (used for tutor) |
| `V2AgentTools` | `app.services.v2_agent_tools` | Read-only bounded access |
| `build_knowledge_status` | `app.services.knowledge_status` | For stale check |

### 11.2 What to create new

| Component | File | Notes |
|-----------|------|-------|
| `DeepDiveService` | `backend/app/services/deep_dive_service.py` | Main service class |
| `DeepDiveResult` | `backend/app/services/deep_dive_service.py` | Result dataclass |
| `_build_mapper_messages` | `backend/app/services/deep_dive_service.py` | Mapper prompts |
| `_build_tutor_messages` | `backend/app/services/deep_dive_service.py` | Tutor prompts (deep-dive variant) |
| `_parse_mapper_response` | `backend/app/services/deep_dive_service.py` | Mapper JSON parsing |
| `_select_bounded_items` | `backend/app/services/deep_dive_service.py` | Term/KC/Relation selection |
| `_is_deep_dive_query` | `backend/app/services/deep_dive_service.py` | Trigger logic |
| Deep-dive trigger tests | `backend/tests/test_deep_dive_service.py` | All 8 scenarios |
| Deep-dive trigger unit tests | `backend/tests/test_deep_dive_trigger.py` | Trigger logic edge cases |

### 11.3 File organization

All deep-dive logic lives in one file (`deep_dive_service.py`) to avoid premature abstraction. If the file exceeds ~600 lines after implementation, extract the trigger logic and prompt templates into separate modules.

### 11.4 Edge cases explicitly handled

1. **Empty mapper output**: If mapper returns valid JSON but all lists are empty, feed `mapper_output` with empty lists to Tutor. Tutor prompt's mapper section will simply state no relevant sections/KCs found.

2. **Mapper returns non-JSON but parseable text**: Attempt to find JSON substring within the content; if that fails, treat as parse failure → degradation.

3. **Single-section course**: If all retrieval hits come from one section, the deep-dive may still be valuable (within-section concept comparison). The mapper should still run. The cross-section citation check in Verifier does not hard-fail.

4. **No Relations data**: If Relations list is empty (but Terms/KCs exist), the mapper receives `bounded_relations=[]`. This is valid. The mapper prompt still asks it to synthesize from Outline + Terms/KCs.

5. **Citation contains stale fragment**: The Verifier's `assemble_answer_envelope` already handles this by checking each fragment ID against the `outcome.hits` allow-list. Stale fragments from a previous revision simply won't be in the Scout's allowed set.

## 12. Open Questions (for implementation)

1. **Mapper temperature**: Should the mapper use a lower temperature (0.1) than the tutor (0.3) since it's doing structured analysis rather than creative writing? Recommendation: start with 0.1 for mapper.

2. **Mapper retry on parse failure**: If the mapper's JSON is malformed, should we retry the call once with a stronger format prompt? The plan says `max_retries=0` for SDK calls, but a structured repair is a new audited call. Recommendation: do not retry; degrade to quick-answer for reliability and cost predictability. If evidence later shows >10% parse failure rate, add a single recovery call.

3. **Term/KC overlap filtering**: The current selection uses simple token overlap. Should we use the query embedding to do semantic selection of the top 10? Recommendation: no. Embedding calls add cost and latency. Token overlap is deterministic, zero-cost, and sufficient for pruning a list from ~50 items to 10.

4. **Verifier cross-section citation check**: This requires knowing each citation's section. Currently `AnswerCitation` has `evidence: EvidenceRef` but not `section_id`. Recommendation: add `section_id` to `AnswerCitation` (populated from `SourceFragment.heading_path` lookup during assembly) OR do the check in `deep_dive_service` before calling `assemble_answer_envelope`. The latter is simpler and avoids schema changes.
