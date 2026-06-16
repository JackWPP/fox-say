import json
import logging
from datetime import date, datetime

from openai import OpenAI

from app.core.config import settings
from app.schemas.foxsay import CourseSkeleton, ReviewPlan, ReviewPlanDay

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = settings.deepseek_api_key or "placeholder"
        _client = OpenAI(api_key=api_key, base_url=settings.deepseek_api_base, timeout=30)
    return _client


SYSTEM_PROMPT = (
    "你是一个课程复习计划生成助手。根据课程信息和骨架数据生成复习计划。\n"
    "你必须严格遵守课程隔离原则：只基于提供的课程数据生成计划，不得使用模型常识补充。\n"
    "请以 JSON 格式返回：\n"
    "{\n"
    '  "daily_plan": [\n'
    '    {"day_index": 1, "focus": "复习重点", "suggested_minutes": 60, "priority": "high|medium|low"}\n'
    "  ],\n"
    '  "likely_exam_points": ["考试重点1"],\n'
    '  "weak_areas": ["薄弱区域1"]\n'
    "}\n"
    "只返回 JSON，不要包含其他文字。"
)


def _calc_remaining_days(exam_date_str: str) -> int:
    exam_date = datetime.strptime(exam_date_str, "%Y-%m-%d").date()
    today = date.today()
    delta = (exam_date - today).days
    return max(delta, 1)


async def generate_review_plan(
    course_id: str,
    course_title: str,
    exam_date: str,
    skeleton: CourseSkeleton,
) -> ReviewPlan:
    remaining_days = _calc_remaining_days(exam_date)

    try:
        plan = await _llm_generate(course_id, course_title, exam_date, remaining_days, skeleton)
    except Exception:
        logger.exception("LLM review plan generation failed for course %s, falling back to weight-based allocation", course_id)
        plan = _fallback_generate(course_id, remaining_days, skeleton)

    return plan


async def _llm_generate(
    course_id: str,
    course_title: str,
    exam_date: str,
    remaining_days: int,
    skeleton: CourseSkeleton,
) -> ReviewPlan:
    client = _get_client()

    chapters_desc = []
    for ch in skeleton.chapters:
        chapters_desc.append(
            f"章节: {ch.title}, 核心概念: {', '.join(ch.key_concepts)}, "
            f"重要性: {ch.importance}, 考试权重: {ch.exam_weight}"
        )
    chapters_text = "\n".join(chapters_desc)

    user_content = (
        f"课程名：{course_title}\n"
        f"考试日期：{exam_date}\n"
        f"剩余天数：{remaining_days}\n"
        f"核心概念：{', '.join(skeleton.core_concepts)}\n"
        f"难点区域：{', '.join(skeleton.difficulty_areas)}\n"
        f"章节信息：\n{chapters_text}"
    )

    response = client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
    )

    raw = response.choices[0].message.content or ""
    parsed = _parse_llm_json(raw)

    daily_plan = [
        ReviewPlanDay(
            day_index=d["day_index"],
            focus=d["focus"],
            suggested_minutes=d["suggested_minutes"],
            priority=d["priority"],
        )
        for d in parsed.get("daily_plan", [])
    ]
    likely_exam_points = parsed.get("likely_exam_points", [])
    weak_areas = parsed.get("weak_areas", [])

    return ReviewPlan(
        course_id=course_id,
        remaining_days=remaining_days,
        daily_plan=daily_plan,
        likely_exam_points=likely_exam_points,
        weak_areas=weak_areas,
    )


def _parse_llm_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


def _fallback_generate(
    course_id: str,
    remaining_days: int,
    skeleton: CourseSkeleton,
) -> ReviewPlan:
    total_weight = sum(ch.exam_weight for ch in skeleton.chapters) or 1.0
    daily_plan: list[ReviewPlanDay] = []
    day_index = 0

    for ch in skeleton.chapters:
        days_for_ch = max(1, round(remaining_days * ch.exam_weight / total_weight))
        for i in range(days_for_ch):
            day_index += 1
            if day_index > remaining_days:
                break
            priority = ch.importance
            suggested_minutes = 90 if ch.importance == "high" else 60 if ch.importance == "medium" else 30
            daily_plan.append(ReviewPlanDay(
                day_index=day_index,
                focus=ch.title if i == 0 else f"{ch.title}（续）",
                suggested_minutes=suggested_minutes,
                priority=priority,
            ))

    likely_exam_points = [ch.title for ch in skeleton.chapters if ch.importance == "high"]
    weak_areas = list(skeleton.difficulty_areas)

    return ReviewPlan(
        course_id=course_id,
        remaining_days=remaining_days,
        daily_plan=daily_plan,
        likely_exam_points=likely_exam_points,
        weak_areas=weak_areas,
    )
