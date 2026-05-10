import json
import logging

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = settings.deepseek_api_key or "placeholder"
        _client = OpenAI(api_key=api_key, base_url=settings.deepseek_api_base)
    return _client


EXTRACTION_SYSTEM_PROMPT = (
    "你是一个课程知识图谱构建助手。你的任务是从课程材料的文本片段中抽取结构化的知识点三元组。\n\n"
    "规则：\n"
    "1. 只抽取当前文本片段中明确出现的知识点关系，不要编造。\n"
    "2. 每个三元组形式为 (主体, 关系, 客体)，主体和客体是具体的概念/术语/知识点。\n"
    "3. 关系类型必须从以下五种中选择：\n"
    "   - contains: 概念包含子概念 (如: 微积分 contains 定积分)\n"
    "   - depends_on: 概念依赖另一个概念 (如: 定积分 depends_on 不定积分)\n"
    "   - has_prerequisite: 学习某概念需要先掌握另一个概念\n"
    "   - relates_to: 两个概念相关但不属于上述类别\n"
    "   - has_application: 概念有具体应用场景\n"
    "4. 为每个三元组提供 source_text 字段：从源文本中截取支持该三元组的关键句子（不超过100字）。\n"
    "5. 如果没有明确的三元组可抽取，返回空列表。\n\n"
    "输出格式：纯 JSON 数组，每个元素包含 subject、relation、object、source_text 四个字段。\n"
    '示例：[{"subject": "微积分", "relation": "contains", "object": "定积分", "source_text": "微积分主要包括微分学和积分学两大部分..."}]'
)


def _parse_llm_json(raw: str) -> list[dict]:
    """Parse LLM response as JSON list, stripping markdown code fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON for triple extraction: %s", raw[:200])
        return []


_REQUIRED_FIELDS = {"subject", "relation", "object"}
_VALID_RELATIONS = {"contains", "depends_on", "has_prerequisite", "relates_to", "has_application"}


def _validate_triple(triple: dict) -> bool:
    if not _REQUIRED_FIELDS.issubset(triple.keys()):
        return False
    if triple["relation"] not in _VALID_RELATIONS:
        return False
    if not triple["subject"].strip() or not triple["object"].strip():
        return False
    return True


def extract_triples(chunk_text: str, chunk_index: int, material_id: str, file_name: str) -> list[dict]:
    """Extract knowledge triples from a single text chunk via LLM."""
    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"请从以下课程材料片段中抽取知识三元组：\n\n{chunk_text[:3000]}"},
            ],
            temperature=0.1,
        )
        raw = response.choices[0].message.content or ""
    except Exception:
        logger.exception("LLM call failed for chunk %d of material %s", chunk_index, material_id)
        return []

    triples = _parse_llm_json(raw)
    validated: list[dict] = []
    for t in triples:
        if _validate_triple(t):
            t["material_id"] = material_id
            t["chunk_index"] = chunk_index
            t["file_name"] = file_name
            validated.append(t)
        else:
            logger.debug("Skipping invalid triple: %s", t)

    return validated


def extract_triples_batch(
    chunks: list[dict],
    material_id: str,
    file_name: str,
) -> list[dict]:
    """Extract triples from all chunks. Per-chunk errors are isolated."""
    all_triples: list[dict] = []
    for chunk in chunks:
        chunk_text = chunk.get("text", "")
        chunk_index = chunk.get("index", 0)
        try:
            triples = extract_triples(chunk_text, chunk_index, material_id, file_name)
            all_triples.extend(triples)
        except Exception:
            logger.exception("Triple extraction failed for chunk %d of material %s, skipping", chunk_index, material_id)
    return all_triples
