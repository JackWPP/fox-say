import json
import logging
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.schemas.foxsay import CourseSkeleton, CourseSkeletonChapter

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = settings.deepseek_api_key or "placeholder"
        _client = OpenAI(api_key=api_key, base_url=settings.deepseek_api_base)
    return _client


SKELETON_FALLBACK_PROMPT = (
    "你是一个课程骨架分析助手。请根据提供的课程材料文本分析课程结构，"
    "以 JSON 格式返回章节组织。\n"
    "{\n"
    '  "chapters": [\n'
    '    {"id": "ch-1", "title": "章节标题", "key_concepts": ["概念1"], "importance": "high|medium|low", "exam_weight": 0.3}\n'
    "  ]\n"
    "}\n"
    "只返回 JSON，不要包含其他文字。"
)


async def generate_skeleton(
    course_id: str,
    course_title: str,
    materials_text: str,
    store: Any = None,
) -> CourseSkeleton:
    # NOTE: `store` is kept in the signature for backward compatibility with callers
    # (e.g. pipeline._generate_and_store_skeleton) — the store is now consumed
    # *after* generate_skeleton returns, and not used inside.
    try:
        return await _llm_generate(course_id, course_title, materials_text)
    except Exception:
        logger.exception("LLM skeleton generation failed for course %s, falling back", course_id)
        return _fallback_generate(course_id, materials_text)


async def _llm_generate(
    course_id: str,
    course_title: str,
    materials_text: str,
) -> CourseSkeleton:
    user_content = f"课程名：{course_title}\n\n课程材料文本：\n{materials_text[:8000]}"

    client = _get_client()
    response = client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": SKELETON_FALLBACK_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )

    raw = response.choices[0].message.content or ""
    parsed = _parse_llm_json(raw)
    chapters_data = parsed.get("chapters", [])

    chapters: list[CourseSkeletonChapter] = []
    for ch in chapters_data:
        chapters.append(CourseSkeletonChapter(
            id=ch["id"],
            title=ch["title"],
            key_concepts=ch.get("key_concepts", []),
            importance=ch.get("importance", "medium"),
            exam_weight=ch.get("exam_weight", 0.0),
        ))

    return CourseSkeleton(
        course_id=course_id,
        chapters=chapters,
        core_concepts=[],
        difficulty_areas=[],
        prerequisite_chain=[],
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
    materials_text: str,
) -> CourseSkeleton:
    chunk_size = 1500
    chunks: list[str] = []
    for i in range(0, len(materials_text), chunk_size):
        chunks.append(materials_text[i : i + chunk_size])

    chapters: list[CourseSkeletonChapter] = []
    for idx, chunk in enumerate(chunks):
        title = chunk[:50].strip().split("\n")[0] or f"第{idx + 1}部分"
        chapters.append(CourseSkeletonChapter(
            id=f"ch-{idx + 1}",
            title=title,
            key_concepts=[],
            importance="medium",
            exam_weight=round(1.0 / max(len(chunks), 1), 2),
        ))

    return CourseSkeleton(
        course_id=course_id,
        chapters=chapters,
        core_concepts=[],
        difficulty_areas=[],
        prerequisite_chain=[],
    )


# =============================================================================
# Wiki-First Pipeline 集成(阶段 2 新增)
# =============================================================================


async def generate_skeleton_from_wiki(
    course_id: str, store: Any
) -> "CourseSkeleton | None":
    """从 Wiki 课程索引 + 章节摘要派生骨架。

    行为:
    - 读 store.get_course_index(course_id)。没有 / 解析失败 / chapters 为空 → return None。
    - 读 store.get_chapter_wikis_by_course(course_id) 作为 key_concepts 来源。
    - 把 CourseIndex.chapters 转成 CourseSkeletonChapter,带 course_id 显式声明。
    - 不调 LLM(纯本地派生);Wiki building 与 skeleton generation 没有 lock,
      上层需要保证先 build_wiki 再调本函数,否则会拿到 None。
    - 不在 Wiki 还在 building 时做特殊处理 — 调用方负责 race。
    """
    from app.schemas.foxsay import CourseIndex  # local import to avoid cycle

    raw = store.get_course_index(course_id)
    if not raw:
        return None
    try:
        ci = CourseIndex.model_validate_json(raw)
    except Exception:
        logger.warning("generate_skeleton_from_wiki: course_index parse failed for %s", course_id)
        return None
    if not ci.chapters:
        return None

    # 拿章节 wiki 的 key_concepts 做骨架的 key_concepts(优先)
    cws = {cw.chapter_id: cw for cw in store.get_chapter_wikis_by_course(course_id)}

    chapters: list[CourseSkeletonChapter] = []
    for c in ci.chapters:
        cw = cws.get(c.id)
        key_concepts = c.key_concepts or (cw.key_concepts if cw else [])
        chapters.append(
            CourseSkeletonChapter(
                id=c.id,
                title=c.title,
                key_concepts=key_concepts,
                importance=c.importance,  # type: ignore[arg-type]
                exam_weight=0.0,
            )
        )

    # 构造 prerequisite_chain:依赖关系展平成 [a, b] 形式
    prereq_chain: list[list[str]] = []
    for c in ci.chapters:
        for dep in c.depends_on:
            prereq_chain.append([dep, c.id])

    return CourseSkeleton(
        course_id=course_id,
        chapters=chapters,
        core_concepts=ci.core_topics,
        difficulty_areas=[],
        prerequisite_chain=prereq_chain,
    )
