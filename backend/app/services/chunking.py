"""语义感知切块器。

基于 LangChain TextSplitter 实现：
1. 先按 Markdown 标题层级切分（保留标题层级上下文）
2. 表格作为不可分割的整体（HTML <table> 或 GFM 表格不会被切断）
3. 段落内按语义边界切分（不在句子、公式、表格中间断）
4. 每个 chunk 自动 prepend 父级标题路径作为上下文
"""

import logging
import re

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 100

_HEADING_KEYS = [
    ("#", "H1"),
    ("##", "H2"),
    ("###", "H3"),
    ("####", "H4"),
    ("#####", "H5"),
    ("######", "H6"),
]


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[dict]:
    """语义感知切块。

    流程：
    1. 提取并保护表格块（HTML 和 GFM 表格）
    2. 用 MarkdownHeaderTextSplitter 按标题层级切分
    3. 对超长段落用 RecursiveCharacterTextSplitter 二次切分
    4. 表格块作为独立 chunk
    5. 每个 chunk prepend 父级标题路径

    Returns:
        list[dict] with keys: text, index, heading_path (optional)
    """
    if not text:
        return []

    # Step 1: 提取表格块，替换为占位符
    text, table_blocks = _extract_table_blocks(text)

    # Step 2: 按标题层级切分
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=_HEADING_KEYS,
        strip_headers=False,
    )
    header_chunks = header_splitter.split_text(text)

    # Step 3: 对超长 chunk 做二次切分
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", ".", " ", ""],
    )

    final_chunks: list[dict] = []
    index = 0

    for hc in header_chunks:
        heading_path = _build_heading_path(hc.metadata)
        content = hc.page_content

        # 还原表格占位符
        content = _restore_table_blocks(content, table_blocks)

        if len(content) <= chunk_size:
            final_chunks.append({
                "text": _prepend_heading(content, heading_path),
                "index": index,
                "heading_path": heading_path,
            })
            index += 1
        else:
            # 二次切分，保留 heading_path
            sub_chunks = char_splitter.split_text(content)
            for sc in sub_chunks:
                final_chunks.append({
                    "text": _prepend_heading(sc, heading_path),
                    "index": index,
                    "heading_path": heading_path,
                })
                index += 1

    # Step 4: 表格块作为独立 chunk
    for table_text, table_heading in table_blocks:
        if table_text.strip():
            full_table = _prepend_heading(table_text, table_heading)
            final_chunks.append({
                "text": full_table,
                "index": index,
                "heading_path": table_heading,
                "is_table": True,
            })
            index += 1

    return final_chunks


def _extract_table_blocks(text: str) -> tuple[str, list[tuple[str, str]]]:
    """提取表格块（HTML <table> 和 GFM 表格），替换为占位符。

    Returns:
        (modified_text, list_of_(table_content, nearest_heading))
    """
    table_blocks: list[tuple[str, str]] = []
    placeholder_id = 0

    # 提取 HTML 表格
    def _replace_html_table(m):
        nonlocal placeholder_id
        placeholder_id += 1
        table_blocks.append((m.group(0), ""))
        return f"{{{{TABLE_PLACEHOLDER_{placeholder_id - 1}}}}}"

    text = re.sub(
        r"<table[^>]*>.*?</table>",
        _replace_html_table,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 提取 GFM 表格（以 | 开头且包含 --- 分隔行的连续块）
    lines = text.split("\n")
    result_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # 检测 GFM 表格起始：当前行是 | 开头，下一行是分隔行
        if (line.strip().startswith("|")
                and i + 1 < len(lines)
                and re.match(r"^\s*\|[\s\-:|]+\|", lines[i + 1])):
            table_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            table_text = "\n".join(table_lines)
            placeholder_id += 1
            table_blocks.append((table_text, ""))
            result_lines.append(f"{{{{TABLE_PLACEHOLDER_{placeholder_id - 1}}}}}")
        else:
            result_lines.append(line)
            i += 1

    return "\n".join(result_lines), table_blocks


def _restore_table_blocks(text: str, table_blocks: list[tuple[str, str]]) -> str:
    """将表格占位符还原为实际内容（表格块会在后续作为独立 chunk 处理）。"""
    for i, (table_text, _) in enumerate(table_blocks):
        placeholder = f"{{{{TABLE_PLACEHOLDER_{i}}}}}"
        # 在非表格 chunk 中，只保留表格编号标记
        label_match = re.search(r"\[Table_\d+\]", table_text)
        label = label_match.group(0) if label_match else f"[Table_{i + 1}]"
        text = text.replace(placeholder, f"\n{label} (见独立表格块)\n")
    return text


def _build_heading_path(metadata: dict) -> str:
    """从 MarkdownHeaderTextSplitter 的 metadata 构建标题路径。"""
    parts = []
    for key in ("H1", "H2", "H3", "H4", "H5", "H6"):
        if key in metadata and metadata[key]:
            parts.append(metadata[key])
    return " > ".join(parts)


def _prepend_heading(content: str, heading_path: str) -> str:
    """如果内容本身不包含标题信息，prepend 标题路径作为上下文。"""
    if not heading_path:
        return content
    # 如果内容已经以 # 开头，不再 prepend
    stripped = content.lstrip()
    if stripped.startswith("#"):
        return content
    return f"[{heading_path}]\n{content}"
