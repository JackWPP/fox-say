"""V2-F6 ReviewService: revision-bound conversational review mode."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from app.db.sqlite_store import SqliteStore
from app.schemas.agent_runs import AgentRun, AgentStep
from app.schemas.review_v2 import (
    BTW_ALLOWED_STEPS,
    BtwResult,
    CurrentSessionState,
    GradingResult,
    ObservationList,
    ReviewSessionState,
    ReviewSessionSummary,
    VALID_TRANSITIONS,
)
from app.services.audited_chat_writer import AuditedChatWriter
from app.services.audited_text_model import AuditedModelCallError
from app.services.knowledge_status import build_knowledge_status
from app.services.v2_agent_tools import V2AgentTools

_NO_SOURCE_REVISION = "__no_source__"
_NO_KNOWLEDGE_REVISION = "__no_knowledge__"

EXAMINER_MAX_OUTPUT_TOKENS = 1024
GRADER_MAX_OUTPUT_TOKENS = 800
TUTOR_MAX_OUTPUT_TOKENS = 800

# ---- Prompt Templates (from architecture doc §5) ----

EXAMINER_SYSTEM_PROMPT = """你是 FoxSay 学习助手的"狐狸考官"——一只会出题、但不会刁难学生的狐狸。

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
}"""

GRADER_SYSTEM_PROMPT = """你是 FoxSay 学习助手的"狐狸评卷官"——一只公正客观、善于发现细节的狐狸。

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
}"""

TUTOR_SYSTEM_PROMPT = """你是 FoxSay 学习助手的"狐狸辅导员"——一只擅长查漏补缺、耐心讲题的狐狸。

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
}"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_model_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("{"):
        return json.loads(text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("No JSON object found in model response")


def _has_gaps(grade_json: dict) -> bool:
    return bool(grade_json.get("missing_points") or grade_json.get("error_points"))


def _make_plan_id(course_id: str, source_rev: str, knowledge_rev: str, exam_date: str) -> str:
    raw = f"{course_id}:{source_rev}:{knowledge_rev}:{exam_date}"
    return f"rp_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _make_session_id() -> str:
    return f"rs_{uuid.uuid4().hex[:16]}"


def _make_attempt_id() -> str:
    return f"ra_{uuid.uuid4().hex[:16]}"


def _make_observation_id() -> str:
    return f"lo_{uuid.uuid4().hex[:16]}"


class ReviewService:
    """Revision-bound conversational review mode with state machine."""

    def __init__(
        self,
        store: SqliteStore,
        tools: V2AgentTools,
        writer: AuditedChatWriter,
        *,
        temperature: float = 0.3,
        default_token_budget: int = 15000,
    ) -> None:
        self._store = store
        self._tools = tools
        self._writer = writer
        self._temperature = temperature
        self._default_token_budget = default_token_budget

    # ---- Plan Operations ----

    async def generate_plan(
        self, course_id: str, exam_date: str | None = None,
    ) -> dict:
        status = build_knowledge_status(self._store, course_id)
        source_rev = status.source_revision or _NO_SOURCE_REVISION
        knowledge_rev = status.knowledge_revision or _NO_KNOWLEDGE_REVISION

        if status.projection_status != "ready":
            raise ValueError("projection_not_ready")

        outline = self._tools.get_current_outline(course_id)
        kcs = self._tools.get_current_knowledge_components(course_id)
        relations = self._tools.get_current_kc_relations(course_id)

        if outline is None or not kcs:
            raise ValueError("no_knowledge_components")

        active_session = self._store.get_active_review_session_v2(course_id)
        if active_session is not None:
            raise ValueError("active_session_exists")

        if exam_date is None:
            course = self._store.get_course(course_id)
            exam_date = course.get("exam_date") if course else None
        if not exam_date:
            exam_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        plan_json = self._deterministic_plan_scheduler(
            exam_date, kcs, relations, outline,
        )
        plan_id = _make_plan_id(course_id, source_rev, knowledge_rev, exam_date)

        self._store.stale_review_plan_v2(course_id)
        self._store.insert_review_plan_v2(
            plan_id, course_id, exam_date, source_rev, knowledge_rev,
            json.dumps(plan_json, ensure_ascii=False), None,
            days_count=len(plan_json["days"]),
            total_kcs=plan_json["metadata"]["total_kcs"],
        )

        return {
            "id": plan_id, "course_id": course_id,
            "exam_date": exam_date,
            "source_revision": source_rev,
            "knowledge_revision": knowledge_rev,
            "days_count": len(plan_json["days"]),
            "total_kcs": plan_json["metadata"]["total_kcs"],
            "status": "active",
            "plan_json": plan_json,
            "is_stale": False,
        }

    async def get_current_plan(self, course_id: str) -> dict | None:
        row = self._store.get_active_review_plan_v2(course_id)
        if row is None:
            return None
        status = build_knowledge_status(self._store, course_id)
        source_rev = status.source_revision or _NO_SOURCE_REVISION
        knowledge_rev = status.knowledge_revision or _NO_KNOWLEDGE_REVISION
        plan_json = json.loads(row["plan_json"])
        is_stale = (
            row["source_revision"] != source_rev
            or row["knowledge_revision"] != knowledge_rev
        )
        return {
            "id": row["id"], "course_id": row["course_id"],
            "exam_date": row["exam_date"],
            "source_revision": row["source_revision"],
            "knowledge_revision": row["knowledge_revision"],
            "days_count": row["days_count"],
            "total_kcs": row["total_kcs"],
            "status": "stale" if is_stale else row["status"],
            "plan_json": plan_json,
            "is_stale": is_stale,
            "created_at": row["created_at"],
        }

    # ---- Session Lifecycle ----

    async def start_session(self, course_id: str) -> ReviewSessionState:
        plan = await self.get_current_plan(course_id)
        if plan is None:
            raise ValueError("no_active_plan")
        if plan.get("is_stale"):
            raise ValueError("plan_stale")

        active = self._store.get_active_review_session_v2(course_id)
        if active is not None:
            raise ValueError("active_session_exists")

        session_id = _make_session_id()
        self._store.insert_review_session_v2(
            session_id, plan["id"], course_id,
            plan["source_revision"], plan["knowledge_revision"],
        )

        plan_json = plan["plan_json"]
        day1 = plan_json["days"][0] if plan_json["days"] else {"title": "", "items": []}
        return ReviewSessionState(
            session_id=session_id, plan_id=plan["id"],
            course_id=course_id, current_day=1,
            current_step="briefing",
            day_title=day1.get("title", ""),
            day_items=day1.get("items", []),
            day_items_count=len(day1.get("items", [])),
            total_days=plan["days_count"],
        )

    async def advance_session(
        self, session_id: str, to_step: str | None = None,
    ) -> ReviewSessionState:
        session = self._store.get_review_session_v2(session_id)
        if session is None:
            raise ValueError("session_not_found")
        if session["status"] != "active":
            raise ValueError("session_not_active")

        self._check_staleness(session)

        current_step = session["current_step"]
        valid_targets = VALID_TRANSITIONS.get(current_step, [])

        if to_step is not None:
            if to_step not in valid_targets:
                raise ValueError(f"invalid_transition: {current_step} -> {to_step}")
            target = to_step
        elif valid_targets:
            target = valid_targets[0]
        else:
            raise ValueError("no_valid_transition")

        return await self._execute_transition(session, target)

    async def _execute_transition(
        self, session: dict, target: str,
    ) -> ReviewSessionState:
        course_id = session["course_id"]
        session_id = session["id"]
        plan = await self.get_current_plan(course_id)
        if plan is None:
            raise ValueError("no_active_plan")
        plan_json = plan["plan_json"]
        current_day = session["current_day"]
        day_data = plan_json["days"][current_day - 1] if current_day <= len(plan_json["days"]) else None

        if target == "teach":
            if day_data is None:
                raise ValueError("day_not_found")
            items = day_data.get("items", [])
            item_idx = 0
            if session.get("current_item_id"):
                for i, it in enumerate(items):
                    if it["item_id"] == session["current_item_id"]:
                        item_idx = i + 1
                        break
            if item_idx >= len(items):
                item_idx = 0
            item = items[item_idx] if items else None
            self._store.update_review_session_v2(
                session_id, current_step="teach",
                current_item_id=item["item_id"] if item else None,
            )
            kc_defs = self._get_kc_defs(course_id, item["kc_ids"] if item else [])
            return ReviewSessionState(
                session_id=session_id, plan_id=session["plan_id"],
                course_id=course_id, current_day=current_day,
                current_step="teach",
                current_item_id=item["item_id"] if item else None,
                current_item={
                    "item_id": item["item_id"] if item else "",
                    "topic": item.get("topic", "") if item else "",
                    "kc_ids": item.get("kc_ids", []) if item else [],
                    "teaching_brief": self._build_teaching_brief(kc_defs),
                    "evidence_refs": item.get("evidence_refs", []) if item else [],
                },
            )

        elif target == "attempt":
            item_id = session.get("current_item_id")
            if not item_id and day_data:
                items = day_data.get("items", [])
                if items:
                    item_id = items[0]["item_id"]
                    self._store.update_review_session_v2(
                        session_id, current_item_id=item_id,
                    )
            item = self._find_item(plan_json, current_day, item_id)
            if item is None:
                raise ValueError("item_not_found")

            run_id = f"ar_{uuid.uuid4().hex[:16]}"
            status_obj = build_knowledge_status(self._store, course_id)
            source_rev = status_obj.source_revision or _NO_SOURCE_REVISION
            knowledge_rev = status_obj.knowledge_revision or _NO_KNOWLEDGE_REVISION
            now = _now_iso()

            run = AgentRun(
                run_id=run_id, turn_id=f"tn_{uuid.uuid4().hex[:16]}",
                course_id=course_id, session_id=session_id,
                workflow_kind="review_session",
                source_revision=source_rev,
                knowledge_revision=knowledge_rev,
                status="accepted", token_budget=self._default_token_budget,
                review_context={"review_session_id": session_id, "review_plan_id": session["plan_id"]},
                created_at=now, updated_at=now,
            )
            self._store.create_agent_run(run)

            kc_defs = self._get_kc_defs(course_id, item.get("kc_ids", []))
            evidence_text = self._collect_evidence_text(course_id, item.get("evidence_refs", []))
            examiner_messages = [
                {"role": "system", "content": EXAMINER_SYSTEM_PROMPT},
                {"role": "user", "content": self._build_examiner_message(kc_defs, evidence_text)},
            ]

            step_id = f"as_{uuid.uuid4().hex[:16]}"
            step = AgentStep(
                step_id=step_id, run_id=run_id,
                agent_role="examiner", step_type="generate",
                status="running", output_type="review_question",
                created_at=_now_iso(),
            )
            self._store.create_agent_step(step)
            self._store.update_agent_run_status(course_id, run_id, "executing")

            try:
                result = await self._writer.complete(
                    run, purpose="review_examiner", messages=examiner_messages,
                    max_output_tokens=EXAMINER_MAX_OUTPUT_TOKENS,
                    temperature=self._temperature, budget_scope="review",
                )
                question_json = _parse_model_json(result.content)
            except (AuditedModelCallError, ValueError, json.JSONDecodeError) as exc:
                self._store.update_agent_step(step_id, "failed", error=str(exc))
                self._store.update_agent_run_status(
                    course_id, run_id, "failed",
                    error_code="examiner_failed", error_detail=str(exc),
                )
                raise ValueError(f"examiner_failed: {exc}") from exc

            self._store.update_agent_step(
                step_id, "completed", model_call_id=result.call_id,
            )

            attempt_id = _make_attempt_id()
            self._store.insert_review_attempt(
                attempt_id, session_id, course_id, current_day, item_id or "",
                json.dumps(item.get("kc_ids", [])),
                json.dumps(question_json, ensure_ascii=False),
                agent_run_id=run_id,
            )

            self._store.update_review_session_v2(
                session_id, current_step="attempt",
                current_item_id=item_id,
            )
            return ReviewSessionState(
                session_id=session_id, plan_id=session["plan_id"],
                course_id=course_id, current_day=current_day,
                current_step="attempt",
                current_item_id=item_id,
                current_attempt={
                    "id": attempt_id,
                    "question": question_json,
                    "status": "awaiting",
                },
            )

        elif target == "grading":
            return await self._do_grading(session)

        elif target == "tutor":
            return await self._do_tutor(session)

        elif target == "feedback":
            last_attempt = self._get_last_attempt(session_id)
            grade = json.loads(last_attempt["grade_json"]) if last_attempt and last_attempt.get("grade_json") else {}
            return ReviewSessionState(
                session_id=session_id, plan_id=session["plan_id"],
                course_id=course_id, current_day=current_day,
                current_step="feedback",
                current_item_id=session.get("current_item_id"),
                grade=grade,
                needs_tutor=_has_gaps(grade),
                next_action=self._determine_next_action(session, plan_json),
            )

        elif target == "next_item":
            item_id = session.get("current_item_id")
            day_data = plan_json["days"][current_day - 1] if current_day <= len(plan_json["days"]) else None
            items = day_data.get("items", []) if day_data else []
            current_idx = 0
            for i, it in enumerate(items):
                if it.get("item_id") == item_id:
                    current_idx = i
                    break
            if current_idx + 1 < len(items):
                next_item = items[current_idx + 1]
                self._store.update_review_session_v2(
                    session_id, current_step="teach",
                    current_item_id=next_item["item_id"],
                )
                kc_defs = self._get_kc_defs(course_id, next_item.get("kc_ids", []))
                return ReviewSessionState(
                    session_id=session_id, plan_id=session["plan_id"],
                    course_id=course_id, current_day=current_day,
                    current_step="teach",
                    current_item_id=next_item["item_id"],
                    current_item={
                        "item_id": next_item["item_id"],
                        "topic": next_item.get("topic", ""),
                        "kc_ids": next_item.get("kc_ids", []),
                        "teaching_brief": self._build_teaching_brief(kc_defs),
                    },
                )
            else:
                self._store.update_review_session_v2(
                    session_id, current_step="next_day_recap",
                )
                return ReviewSessionState(
                    session_id=session_id, plan_id=session["plan_id"],
                    course_id=course_id, current_day=current_day,
                    current_step="next_day_recap",
                    day_summary=self._build_day_summary(session_id, current_day),
                    kc_statuses=self._build_kc_statuses(session_id),
                    is_last_day=(current_day >= plan["days_count"]),
                )

        elif target == "next_day_recap":
            self._store.update_review_session_v2(
                session_id, current_step="next_day_recap",
            )
            return ReviewSessionState(
                session_id=session_id, plan_id=session["plan_id"],
                course_id=course_id, current_day=current_day,
                current_step="next_day_recap",
                day_summary=self._build_day_summary(session_id, current_day),
                kc_statuses=self._build_kc_statuses(session_id),
                is_last_day=(current_day >= len(plan_json["days"])),
            )

        elif target == "briefing":
            new_day = current_day + 1
            self._store.update_review_session_v2(
                session_id, current_day=new_day,
                current_step="briefing", current_item_id=None,
            )
            day_data = plan_json["days"][new_day - 1] if new_day <= len(plan_json["days"]) else {"title": "", "items": []}
            return ReviewSessionState(
                session_id=session_id, plan_id=session["plan_id"],
                course_id=course_id, current_day=new_day,
                current_step="briefing",
                day_title=day_data.get("title", ""),
                day_items=day_data.get("items", []),
                day_items_count=len(day_data.get("items", [])),
                total_days=plan["days_count"],
            )

        elif target == "done":
            self._store.update_review_session_v2(session_id, status="completed")
            return ReviewSessionState(
                session_id=session_id, plan_id=session["plan_id"],
                course_id=course_id, current_day=current_day,
                current_step="done", status="completed",
            )

        raise ValueError(f"unhandled_transition: {target}")

    # ---- Answer Submission ----

    async def submit_answer(
        self, session_id: str, answer: str,
    ) -> GradingResult:
        session = self._store.get_review_session_v2(session_id)
        if session is None:
            raise ValueError("session_not_found")
        if session["current_step"] != "attempt":
            raise ValueError("not_in_attempt_step")

        self._check_staleness(session)

        last_attempt = self._get_last_attempt(session_id)
        if last_attempt is None:
            raise ValueError("no_awaiting_attempt")

        self._store.update_review_attempt(
            last_attempt["id"], user_answer=answer,
        )

        if not answer or not answer.strip():
            question_json = json.loads(last_attempt["question_json"])
            rubric = question_json.get("rubric", {})
            kc_ids = json.loads(last_attempt["kc_ids_json"])
            grade = {
                "overall": "incorrect",
                "correct_points": [],
                "missing_points": rubric.get("key_points", []),
                "error_points": [],
                "uncertain_points": [],
                "kc_assessment": {kid: "incorrect" for kid in kc_ids},
                "learner_observations": [
                    {"kc_id": kid, "type": "incorrect_attempt", "confidence": 1.0,
                     "detail": "Student submitted empty answer"}
                    for kid in kc_ids
                ],
            }
        else:
            question_json = json.loads(last_attempt["question_json"])
            course_id = session["course_id"]
            evidence_text = self._collect_evidence_text(
                course_id, question_json.get("evidence_refs", []),
            )
            grader_messages = [
                {"role": "system", "content": GRADER_SYSTEM_PROMPT},
                {"role": "user", "content": self._build_grader_message(
                    question_json, answer, evidence_text,
                )},
            ]
            run_id = last_attempt.get("agent_run_id") or f"ar_{uuid.uuid4().hex[:16]}"
            run = self._store.get_agent_run(course_id, run_id)
            if run is None:
                status_obj = build_knowledge_status(self._store, course_id)
                source_rev = status_obj.source_revision or _NO_SOURCE_REVISION
                knowledge_rev = status_obj.knowledge_revision or _NO_KNOWLEDGE_REVISION
                now = _now_iso()
                run = AgentRun(
                    run_id=run_id, turn_id=f"tn_{uuid.uuid4().hex[:16]}",
                    course_id=course_id, session_id=session_id,
                    workflow_kind="review_session",
                    source_revision=source_rev,
                    knowledge_revision=knowledge_rev,
                    status="accepted", token_budget=self._default_token_budget,
                    created_at=now, updated_at=now,
                )
                self._store.create_agent_run(run)

            step_id = f"as_{uuid.uuid4().hex[:16]}"
            step = AgentStep(
                step_id=step_id, run_id=run_id,
                agent_role="grader", step_type="grade",
                status="running", output_type="grading_result",
                created_at=_now_iso(),
            )
            self._store.create_agent_step(step)

            try:
                result = await self._writer.complete(
                    run, purpose="review_grader", messages=grader_messages,
                    max_output_tokens=GRADER_MAX_OUTPUT_TOKENS,
                    temperature=self._temperature, budget_scope="review",
                )
                grade = _parse_model_json(result.content)
            except (AuditedModelCallError, ValueError, json.JSONDecodeError) as exc:
                self._store.update_agent_step(step_id, "failed", error=str(exc))
                raise ValueError(f"grader_failed: {exc}") from exc

            self._store.update_agent_step(
                step_id, "completed", model_call_id=result.call_id,
            )

        self._store.update_review_attempt(
            last_attempt["id"],
            grade_json=json.dumps(grade, ensure_ascii=False),
            status="graded",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

        self._store.update_review_session_v2(session_id, current_step="grading")

        obs_count = self._create_observations(
            session_id, session["course_id"], last_attempt["id"],
            grade, last_attempt.get("agent_run_id"),
        )

        return GradingResult(
            attempt_id=last_attempt["id"],
            grade=grade,
            needs_tutor=_has_gaps(grade),
            next_step="feedback",
            observations_created=obs_count,
        )

    async def complete_session(self, session_id: str) -> ReviewSessionSummary:
        session = self._store.get_review_session_v2(session_id)
        if session is None:
            raise ValueError("session_not_found")
        self._store.update_review_session_v2(session_id, status="completed")
        attempts = self._store.get_session_review_attempts(session_id)
        correct = sum(1 for a in attempts if a.get("grade_json") and json.loads(a["grade_json"]).get("overall") == "correct")
        partial = sum(1 for a in attempts if a.get("grade_json") and json.loads(a["grade_json"]).get("overall") == "partial")
        incorrect = sum(1 for a in attempts if a.get("grade_json") and json.loads(a["grade_json"]).get("overall") == "incorrect")
        obs = self._store.get_session_learner_observations(session_id)
        return ReviewSessionSummary(
            session_id=session_id,
            days_completed=session["current_day"],
            total_attempts=len(attempts),
            correct_attempts=correct,
            partial_attempts=partial,
            incorrect_attempts=incorrect,
            observations_count=len(obs),
            started_at=session.get("started_at", ""),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    async def cancel_session(self, session_id: str) -> dict:
        session = self._store.get_review_session_v2(session_id)
        if session is None:
            raise ValueError("session_not_found")
        prev = session["status"]
        self._store.update_review_session_v2(session_id, status="cancelled")
        return {"session_id": session_id, "previous_status": prev, "current_status": "cancelled"}

    async def get_current_session(self, course_id: str) -> CurrentSessionState:
        session = self._store.get_active_review_session_v2(course_id)
        if session is None:
            return CurrentSessionState(has_active_session=False)

        plan = await self.get_current_plan(course_id)
        is_stale = plan.get("is_stale", False) if plan else False
        stale_reason = None
        if is_stale:
            stale_reason = "Plan is stale due to revision change"

        last_attempt = self._get_last_attempt(session["id"])
        current_attempt = None
        last_grade = None
        if last_attempt:
            if last_attempt["status"] == "awaiting":
                current_attempt = {
                    "id": last_attempt["id"],
                    "question_json": json.loads(last_attempt["question_json"]) if last_attempt.get("question_json") else None,
                    "status": last_attempt["status"],
                }
            elif last_attempt.get("grade_json"):
                last_grade = json.loads(last_attempt["grade_json"])

        return CurrentSessionState(
            has_active_session=True,
            session=session,
            plan=plan,
            current_attempt=current_attempt,
            last_grade=last_grade,
            is_stale=is_stale,
            stale_reason=stale_reason,
        )

    # ---- /btw ----

    async def handle_btw(
        self, session_id: str, question: str, workflow_hint: str = "auto",
    ) -> BtwResult:
        session = self._store.get_review_session_v2(session_id)
        if session is None or session["status"] != "active":
            raise ValueError("no_active_review_session")
        if session["current_step"] not in BTW_ALLOWED_STEPS:
            raise ValueError(f"/btw not available at step: {session['current_step']}")

        anchor = {
            "session_id": session_id,
            "plan_id": session["plan_id"],
            "day": session["current_day"],
            "item_id": session.get("current_item_id", ""),
            "step_id": session["current_step"],
            "step_label": f"第{session['current_day']}天 · 答题中",
        }

        from app.services.quick_answer_service import QuickAnswerService
        from app.services.audited_chat_writer import AuditedChatWriter
        from app.core.config import settings
        import openai

        client = openai.OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_api_base,
        )
        writer = AuditedChatWriter(
            self._store, client=client, model=settings.deepseek_model,
            course_budget_tokens=settings.knowledge_course_default_token_budget,
        )
        qa = QuickAnswerService(self._store, writer)
        qa_result = await qa.answer(
            course_id=session["course_id"],
            session_id=session_id,
            turn_id=f"tn_{uuid.uuid4().hex[:16]}",
            query=question,
            review_context=anchor,
        )

        return BtwResult(
            envelope={"answer": qa_result.envelope.answer if hasattr(qa_result.envelope, 'answer') else str(qa_result.envelope),
                      "confidence_status": qa_result.envelope.confidence_status if hasattr(qa_result.envelope, 'confidence_status') else "grounded"},
            return_anchor=anchor,
        )

    # ---- Observations ----

    async def get_observations(self, course_id: str) -> ObservationList:
        rows = self._store.get_course_learner_observations(course_id)
        by_kc: dict[str, int] = {}
        for row in rows:
            kc_id = row.get("kc_id", "")
            by_kc[kc_id] = by_kc.get(kc_id, 0) + 1
        return ObservationList(observations=rows, total=len(rows), by_kc=by_kc)

    # ---- Internal: Deterministic Scheduler ----

    def _deterministic_plan_scheduler(
        self, exam_date: str, kcs: list, relations: list, outline: Any,
    ) -> dict:
        try:
            exam_dt = datetime.strptime(exam_date, "%Y-%m-%d")
        except ValueError:
            exam_dt = datetime.now() + __import__("datetime").timedelta(days=7)
        today = datetime.now()
        remaining = max(1, min(30, (exam_dt - today).days))

        kc_map: dict[str, dict] = {}
        for kc in kcs:
            kc_map[kc.kc_id] = {
                "kc_id": kc.kc_id,
                "name": kc.name,
                "kind": kc.kind if hasattr(kc, 'kind') else "concept",
                "definition": kc.definition if hasattr(kc, 'definition') else "",
                "section_id": kc.section_id if hasattr(kc, 'section_id') else "",
            }

        prereq_graph: dict[str, list[str]] = {kc_id: [] for kc_id in kc_map}
        dependents_count: dict[str, int] = {kc_id: 0 for kc_id in kc_map}
        for rel in relations:
            if hasattr(rel, 'relation_type') and rel.relation_type == "prerequisite":
                src = rel.source_kc_id if hasattr(rel, 'source_kc_id') else ""
                tgt = rel.target_kc_id if hasattr(rel, 'target_kc_id') else ""
                if src in prereq_graph and tgt in prereq_graph:
                    prereq_graph[src].append(tgt)
                    dependents_count[src] = dependents_count.get(src, 0) + 1

        ordered = self._topological_sort(kc_map, prereq_graph)

        priorities: dict[str, float] = {}
        for kc_id in ordered:
            base = 1.0
            base += dependents_count.get(kc_id, 0) * 0.5
            priorities[kc_id] = base

        kcs_per_day = max(1, (len(ordered) + remaining - 1) // remaining)
        days: list[dict] = []
        idx = 0
        for d in range(1, remaining + 1):
            day_kcs = ordered[idx:idx + kcs_per_day]
            idx += kcs_per_day
            if not day_kcs and d > 1:
                break
            items: list[dict] = []
            for n, kc_id in enumerate(day_kcs, 1):
                kc = kc_map.get(kc_id, {})
                items.append({
                    "item_id": f"day{d}_item{n}",
                    "kc_ids": [kc_id],
                    "topic": kc.get("name", kc_id),
                    "priority": int(priorities.get(kc_id, 1)),
                    "estimated_minutes": 15,
                    "evidence_refs": [],
                })
            section_titles = set()
            for kc_id in day_kcs:
                kc = kc_map.get(kc_id, {})
                sid = kc.get("section_id", "")
                if outline and hasattr(outline, 'sections'):
                    for sec in outline.sections:
                        if sec.section_id == sid:
                            section_titles.add(sec.title)
            day_title = "、".join(sorted(section_titles)[:3]) if section_titles else f"第{d}天"
            days.append({
                "day": d, "title": day_title, "items": items,
                "daily_summary": f"复习{len(day_kcs)}个知识点",
            })

        return {
            "version": 1,
            "algorithm": "topological_weighted_2026_07",
            "days": days,
            "metadata": {
                "total_days": len(days),
                "total_kcs": len(kc_map),
                "exam_date": exam_date,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "has_learning_history": False,
            },
        }

    def _topological_sort(
        self, kc_map: dict[str, dict], prereq_graph: dict[str, list[str]],
    ) -> list[str]:
        in_degree: dict[str, int] = {kc_id: 0 for kc_id in kc_map}
        reverse_graph: dict[str, list[str]] = {kc_id: [] for kc_id in kc_map}
        for src, targets in prereq_graph.items():
            for tgt in targets:
                if tgt in in_degree:
                    in_degree[tgt] += 1
                    reverse_graph[tgt].append(src)

        queue = deque(kc_id for kc_id, deg in in_degree.items() if deg == 0)
        ordered: list[str] = []
        while queue:
            kc_id = queue.popleft()
            ordered.append(kc_id)
            for tgt in prereq_graph.get(kc_id, []):
                if tgt in in_degree:
                    in_degree[tgt] -= 1
                    if in_degree[tgt] == 0:
                        queue.append(tgt)

        remaining = [kc_id for kc_id in kc_map if kc_id not in ordered]
        ordered.extend(sorted(remaining))
        return ordered

    # ---- Internal: Helpers ----

    def _get_kc_defs(self, course_id: str, kc_ids: list[str]) -> list[dict]:
        all_kcs = self._tools.get_current_knowledge_components(course_id)
        kc_map = {kc.kc_id: kc for kc in all_kcs}
        result = []
        for kid in kc_ids:
            kc = kc_map.get(kid)
            if kc:
                result.append({
                    "kc_id": kc.kc_id, "name": kc.name,
                    "kind": kc.kind if hasattr(kc, 'kind') else "concept",
                    "definition": kc.definition[:200] if hasattr(kc, 'definition') else "",
                })
        return result

    def _collect_evidence_text(self, course_id: str, evidence_refs: list[dict]) -> str:
        parts: list[str] = []
        for ref in evidence_refs[:5]:
            fid = ref.get("fragment_id", "")
            if not fid:
                continue
            kcs = self._tools.get_current_knowledge_components(course_id)
            for kc in kcs:
                for ev in (kc.evidence if hasattr(kc, 'evidence') else []):
                    if hasattr(ev, 'fragment_id') and ev.fragment_id == fid:
                        preview = self._tools.open_evidence(course_id, ev)
                        if preview and hasattr(preview, 'text'):
                            parts.append(preview.text[:500])
                        break
        return "\n---\n".join(parts)[:2000]

    def _build_examiner_message(self, kc_defs: list[dict], evidence_text: str) -> str:
        parts = ["复习知识点："]
        for kc in kc_defs:
            parts.append(f"  · [{kc['kc_id']}] {kc['name']}（{kc['kind']}）：{kc['definition'][:200]}")
        if evidence_text:
            parts.append(f"\n课程材料证据：\n{evidence_text[:2000]}")
        parts.append('\n请以 JSON 格式返回题目。')
        return "\n".join(parts)

    def _build_grader_message(self, question: dict, user_answer: str, evidence_text: str) -> str:
        parts = [f"题目：{question.get('question_text', '')}"]
        rubric = question.get("rubric", {})
        parts.append(f"参考答案：{rubric.get('correct_answer', '')}")
        parts.append("评分要点：")
        for i, kp in enumerate(rubric.get("key_points", []), 1):
            parts.append(f"  {i}. {kp}")
        if rubric.get("acceptable_variants"):
            parts.append("可接受替代解法：")
            for v in rubric["acceptable_variants"]:
                parts.append(f"  · {v}")
        if evidence_text:
            parts.append(f"\n课程材料证据：\n{evidence_text[:1500]}")
        parts.append(f"\n学生作答：\n{user_answer}")
        parts.append('\n请以 JSON 格式返回评价。')
        return "\n".join(parts)

    def _build_teaching_brief(self, kc_defs: list[dict]) -> str:
        if not kc_defs:
            return ""
        parts = []
        for kc in kc_defs:
            parts.append(f"**{kc['name']}**（{kc['kind']}）：{kc['definition']}")
        return "\n".join(parts)

    def _build_day_summary(self, session_id: str, day: int) -> str:
        attempts = self._store.get_session_review_attempts(session_id)
        day_attempts = [a for a in attempts if a["day"] == day]
        return f"今天完成了{len(day_attempts)}道题目。"

    def _build_kc_statuses(self, session_id: str) -> dict[str, str]:
        attempts = self._store.get_session_review_attempts(session_id)
        statuses: dict[str, str] = {}
        for attempt in attempts:
            if attempt.get("grade_json"):
                grade = json.loads(attempt["grade_json"])
                kc_assessment = grade.get("kc_assessment", {})
                for kc_id, assessment in kc_assessment.items():
                    statuses[kc_id] = assessment
        return statuses

    def _determine_next_action(self, session: dict, plan_json: dict) -> str:
        current_day = session["current_day"]
        item_id = session.get("current_item_id")
        day_data = plan_json["days"][current_day - 1] if current_day <= len(plan_json["days"]) else None
        if day_data is None:
            return "done"
        items = day_data.get("items", [])
        current_idx = 0
        for i, it in enumerate(items):
            if it.get("item_id") == item_id:
                current_idx = i
                break
        if current_idx + 1 < len(items):
            return "next_item"
        if current_day >= len(plan_json["days"]):
            return "done"
        return "day_recap"

    def _find_item(self, plan_json: dict, day: int, item_id: str | None) -> dict | None:
        if item_id is None:
            return None
        days = plan_json.get("days", [])
        if day < 1 or day > len(days):
            return None
        for item in days[day - 1].get("items", []):
            if item.get("item_id") == item_id:
                return item
        return None

    def _get_last_attempt(self, session_id: str) -> dict | None:
        attempts = self._store.get_session_review_attempts(session_id)
        return attempts[-1] if attempts else None

    def _check_staleness(self, session: dict) -> None:
        course_id = session["course_id"]
        status = build_knowledge_status(self._store, course_id)
        current_source = status.source_revision or _NO_SOURCE_REVISION
        current_knowledge = status.knowledge_revision or _NO_KNOWLEDGE_REVISION
        if (session["source_revision"] != current_source
                or session["knowledge_revision"] != current_knowledge):
            self._store.update_review_session_v2(session["id"], status="stale")
            raise ValueError("session_stale")

    def _create_observations(
        self, session_id: str, course_id: str, attempt_id: str,
        grade: dict, run_id: str | None,
    ) -> int:
        count = 0
        for obs in grade.get("learner_observations", []):
            obs_id = _make_observation_id()
            self._store.insert_learner_observation(
                obs_id, course_id, session_id,
                kc_id=obs.get("kc_id", ""),
                observation_type=obs.get("type", "incorrect_attempt"),
                confidence=obs.get("confidence", 1.0),
                source_attempt_id=attempt_id,
                source_run_id=run_id,
                detail=obs.get("detail"),
            )
            count += 1
        return count

    async def _do_grading(self, session: dict) -> ReviewSessionState:
        """Auto-advance from grading to feedback (or tutor)."""
        last_attempt = self._get_last_attempt(session["id"])
        if last_attempt is None or not last_attempt.get("grade_json"):
            raise ValueError("no_grade_result")
        grade = json.loads(last_attempt["grade_json"])
        has_gaps = _has_gaps(grade)
        self._store.update_review_session_v2(session["id"], current_step="grading")
        return ReviewSessionState(
            session_id=session["id"], plan_id=session["plan_id"],
            course_id=session["course_id"],
            current_day=session["current_day"],
            current_step="grading",
            current_item_id=session.get("current_item_id"),
            grade=grade,
            needs_tutor=has_gaps,
            next_action="tutor_makeup" if has_gaps else "next_item",
        )

    async def _do_tutor(self, session: dict) -> ReviewSessionState:
        """Run tutor make-up model call."""
        last_attempt = self._get_last_attempt(session["id"])
        if last_attempt is None:
            raise ValueError("no_attempt_for_tutor")
        grade = json.loads(last_attempt["grade_json"]) if last_attempt.get("grade_json") else {}
        missing = grade.get("missing_points", [])
        errors = grade.get("error_points", [])

        course_id = session["course_id"]
        item_id = session.get("current_item_id")
        plan = await self.get_current_plan(course_id)
        plan_json = plan["plan_json"] if plan else {"days": []}
        item = self._find_item(plan_json, session["current_day"], item_id)
        kc_ids = item.get("kc_ids", []) if item else []
        kc_defs = self._get_kc_defs(course_id, kc_ids)

        tutor_messages = [
            {"role": "system", "content": TUTOR_SYSTEM_PROMPT},
            {"role": "user", "content": self._build_tutor_message(kc_defs, missing, errors)},
        ]

        run_id = last_attempt.get("agent_run_id") or f"ar_{uuid.uuid4().hex[:16]}"
        run = self._store.get_agent_run(course_id, run_id)
        if run is None:
            status_obj = build_knowledge_status(self._store, course_id)
            source_rev = status_obj.source_revision or _NO_SOURCE_REVISION
            knowledge_rev = status_obj.knowledge_revision or _NO_KNOWLEDGE_REVISION
            now = _now_iso()
            run = AgentRun(
                run_id=run_id, turn_id=f"tn_{uuid.uuid4().hex[:16]}",
                course_id=course_id, session_id=session["id"],
                workflow_kind="review_session",
                source_revision=source_rev,
                knowledge_revision=knowledge_rev,
                status="accepted", token_budget=self._default_token_budget,
                created_at=now, updated_at=now,
            )
            self._store.create_agent_run(run)

        step_id = f"as_{uuid.uuid4().hex[:16]}"
        step = AgentStep(
            step_id=step_id, run_id=run_id,
            agent_role="tutor", step_type="generate",
            status="running", output_type="tutor_makeup",
            created_at=_now_iso(),
        )
        self._store.create_agent_step(step)

        try:
            result = await self._writer.complete(
                run, purpose="review_tutor", messages=tutor_messages,
                max_output_tokens=TUTOR_MAX_OUTPUT_TOKENS,
                temperature=self._temperature, budget_scope="review",
            )
            _tutor_json = _parse_model_json(result.content)
        except (AuditedModelCallError, ValueError, json.JSONDecodeError):
            _tutor_json = {"make_up_text": "\n".join(missing + errors), "hint": ""}

        self._store.update_agent_step(step_id, "completed")
        self._store.update_review_session_v2(session["id"], current_step="feedback")

        return ReviewSessionState(
            session_id=session["id"], plan_id=session["plan_id"],
            course_id=course_id,
            current_day=session["current_day"],
            current_step="feedback",
            current_item_id=item_id,
            grade=grade,
            needs_tutor=False,
            next_action=self._determine_next_action(session, plan_json),
        )

    def _build_tutor_message(
        self, kc_defs: list[dict], missing: list[str], errors: list[str],
    ) -> str:
        parts = ["学生答错的知识点："]
        for kc in kc_defs:
            parts.append(f"  [{kc['kc_id']}] {kc['name']}：{kc['definition']}")
        if missing:
            parts.append("\n缺失的要点：")
            for m in missing:
                parts.append(f"  - {m}")
        if errors:
            parts.append("\n错误的要点：")
            for e in errors:
                parts.append(f"  - {e}")
        parts.append('\n请以 JSON 格式返回补充讲解。')
        return "\n".join(parts)
