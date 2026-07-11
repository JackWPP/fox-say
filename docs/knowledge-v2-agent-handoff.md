# V2 Knowledge System → Chat / Agent Handoff

## Handoff boundary

知识体系 V2 的事实层已经完成；下一阶段才迁移 `/courses/{course_id}/chat` 与 Agent 执行循环。
在迁移完成前，legacy Wiki/DMAP/KC/chat 仍可运行，但**不得**被声明为 V2 的事实源或引用来源。

下一阶段已确定全面重构**通用 Course Agent V2 与电脑端 Course Workspace**，完成知识体系展示、
V2 Chat、bounded deep-dive 多 Agent、对话式备考、Artifact 与 `/btw` 闭环。线性代数是主要工程验收和演示工具，不是产品或运行时边界；另有文字型合成课程 smoke 防止学科硬编码。详细产品流程、任务边界和验收见
[`course-agent-v2-plan.md`](course-agent-v2-plan.md)；实际状态和领取范围仍只以任务台账的 `V2-F0`～`V2-F8` 为准。

## Current evidence chain

```text
SourceFragment (fact)
  → CourseOutline (D0)
  → SemanticAtom (audited text model)
  → Term (rule)
  → KnowledgeComponent (rule)
  → KCRelation (audited text model, explicit opt-in)
```

除 `SourceFragment` 外均为 course/source/knowledge-revision scoped、可删除重建的投影；所有写入都通过持久 `knowledge_jobs` 的 target、attempt、lease、current source 和父投影栅栏。

## Agent may read

Use `app.services.v2_agent_tools.V2AgentTools` only within a supplied `course_id`:

- `search_evidence`：current fragment 检索，返回 CRAG `RetrievalOutcome`；此工具禁用隐式 embedding/模型调用。
- `open_evidence`：按 opaque `EvidenceRef.fragment_id` 打开 current-ready 原文。
- `get_current_outline`：D0 current outline。
- `get_knowledge_status`：持久任务、revision、预算状态。
- `get_current_terms` / `get_current_knowledge_components`：只返回当前 source + knowledge revision 的投影。
- `get_current_kc_relations`：只返回当前 source + knowledge revision 的有证据关系。

所有工具必须显式接收 `course_id`；不能从 filename、chapter 字符串、session 或模型上下文反推范围。

## Required chat migration contract

1. 先调用 V2 retrieval，再由服务器 `assemble_answer_envelope(...)` 组装 `AnswerEnvelope`。
2. 模型可撰写答案，但不能自由生成 citation；material citation 只从该次 `RetrievalOutcome` 的 canonical fragments 选择。
3. `grounded` 正常带 citation；`ambiguous` 说明证据有限；`out_of_scope` 必须是 `answer_source="supplementary"` 并声明材料未覆盖；`unavailable` 是可见错误而不是“无材料”。
4. 聊天持久化/SSE 只保存已组装的 V2 citation metadata；SSE 永远不是知识任务状态源。
5. 第一次迁移保持 legacy stream endpoint 的事件形状兼容；以 feature boundary 逐步替换工具，不做 legacy/V2 双事实合并。

## Model and cost boundaries

- Semantic Atom：DeepSeek audited text job；自动调度需 `KNOWLEDGE_SEMANTIC_AUTO_ENQUEUE=true`。
- KC relation：同样是单次 audited text job，默认 `KNOWLEDGE_KC_RELATION_AUTO_ENQUEUE=false`。
- VLM：`visual_analysis` 显式 asset job，默认 `KNOWLEDGE_VISUAL_ANALYSIS_ENABLED=false`；结果在被单独投影为证据前不是事实。
- 每次模型调用必须沿用 `model_call_audits`、course/job token reservation、`max_retries=0` 与可见错误；不得在 Agent 对话中绕过这些边界。

## Migration order

1. `V2-F1` 先建立独立 AgentRun、course/session 隔离和可复用的模型审计/预算 owner，不能伪造 knowledge job。
2. `V2-F2` 建立 V2 quick-answer service 和 AnswerEnvelope-only 输出测试，再由 `V2-F3` 接 chat stream、历史与恢复。
3. `V2-F4` 展示真实知识构建结果和四种回答状态；`V2-F5` 再增加 bounded deep-dive 多 Agent。
4. `V2-F6` 将复习、作答、批改和 `/btw` 改读 current KC + Relation；不要读取 legacy `wiki_kcs`。
5. `V2-F7` 完成 current V2 课程简报和一个核心 Artifact；`V2-F8` 最后删除所有 Course Agent production 路径的 legacy Wiki/DMAP 事实输入，并执行线性代数主验收与文字型通用性 smoke。

## Evidence already available

- G1 自动合成线代真实链路：1 DeepSeek 请求，421 tokens，3295 ms，D0/Semantic/Term/KC 成功；见 `docs/postmortem/knowledge-v2-g1-auto-linear-2026-07-11.md`。
- D3b 和 VLM 是 explicit opt-in；迁移 Agent 前应读取任务台账确认其最终状态。
