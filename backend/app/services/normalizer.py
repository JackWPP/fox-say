"""Markdown 归一化引擎。

将各解析器（Docling、MinerU、MarkItDown、VLM）的原始输出统一为
符合 FoxSay 标准的 Markdown：

1. 页面锚定：<!-- PAGE_START N --> / <!-- PAGE_END N -->
2. 表格保护：复杂表格（含 rowspan/colspan）保留 HTML <table> 格式
3. 公式对齐：行内 $...$，块级独行 $$...$$
4. 全局编号：[Image_1], [Table_1], [Formula_1] 顺序递增
5. 标题统一：所有标题映射为 # / ## / ### 标准格式
"""

import logging
import re
import uuid
from dataclasses import dataclass, field

from app.services.parser_interface import ExtractedAssetMeta

logger = logging.getLogger(__name__)


@dataclass
class NormalizedOutput:
    markdown_content: str
    extracted_assets: list[ExtractedAssetMeta] = field(default_factory=list)
    page_count: int = 0
    table_count: int = 0
    image_count: int = 0
    formula_count: int = 0


class NormalizationEngine:
    """将任意解析器输出归一化为 FoxSay 标准 Markdown。"""

    def normalize(
        self,
        raw_markdown: str,
        source_type: str,
        extracted_assets: list[ExtractedAssetMeta] | None = None,
    ) -> NormalizedOutput:
        text = raw_markdown

        # 1. 标题统一化
        text = self._normalize_headings(text)

        # 2. 公式对齐
        text, formula_count = self._normalize_formulas(text)

        # 3. 表格保护（确保复杂表格不被切碎）
        text, table_count = self._protect_tables(text)

        # 4. 全局编号（图片、表格、公式）
        text, image_count = self._assign_sequential_labels(text)

        # 5. 页面锚定（如果缺失则补全）
        text, page_count = self._ensure_page_anchors(text)

        # 6. 清理多余空行
        text = self._cleanup_blank_lines(text)

        assets = extracted_assets or []

        return NormalizedOutput(
            markdown_content=text,
            extracted_assets=assets,
            page_count=page_count,
            table_count=table_count,
            image_count=image_count,
            formula_count=formula_count,
        )

    def _normalize_headings(self, text: str) -> str:
        """统一标题格式：确保 # 后有空格，层级不超过 6。"""
        lines = text.split("\n")
        result = []
        for line in lines:
            m = re.match(r"^(#{1,6})\s*(.*)", line)
            if m:
                hashes = m.group(1)
                title = m.group(2).strip()
                if title:
                    result.append(f"{hashes} {title}")
                else:
                    result.append(line)
            else:
                result.append(line)
        return "\n".join(result)

    def _normalize_formulas(self, text: str) -> tuple[str, int]:
        """统一公式格式：行内 $...$，块级独行 $$...$$。"""
        formula_count = 0

        # 将 \[...\] 转为 $$...$$
        text = re.sub(
            r"\\\[([^\]]+)\\\]",
            lambda m: f"\n$${m.group(1).strip()}$$\n",
            text,
        )

        # 将 \(...\) 转为 $...$
        text = re.sub(
            r"\\\(([^)]+)\\\)",
            lambda m: f"${m.group(1).strip()}$",
            text,
        )

        # 给块级公式编号
        def _tag_formula(m):
            nonlocal formula_count
            formula_count += 1
            formula = m.group(1).strip()
            return f"\n$${formula}$$\n\\tag{{Formula_{formula_count}}}\n"

        text = re.sub(
            r"\n\$\$(.+?)\$\$\n",
            _tag_formula,
            text,
            flags=re.DOTALL,
        )

        return text, formula_count

    def _protect_tables(self, text: str) -> tuple[str, int]:
        """确保 HTML 表格完整，不被后续 chunker 切碎。"""
        table_count = 0

        # 计算已有的 [Table_N] 标签
        existing = re.findall(r"\[Table_(\d+)\]", text)
        if existing:
            table_count = max(int(x) for x in existing)

        # 给没有标签的 HTML 表格添加编号
        def _tag_html_table(m):
            nonlocal table_count
            table_count += 1
            return f"\n[Table_{table_count}]\n{m.group(0)}"

        text = re.sub(
            r"<table[^>]*>.*?</table>",
            _tag_html_table,
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        return text, table_count

    def _assign_sequential_labels(self, text: str) -> tuple[str, int]:
        """给图片分配全局顺序编号。"""
        image_count = 0

        existing = re.findall(r"\[Image_(\d+)\]", text)
        if existing:
            image_count = max(int(x) for x in existing)

        # 给没有编号的图片标记添加编号
        def _tag_image(m):
            nonlocal image_count
            image_count += 1
            alt = m.group(1)
            src = m.group(2)
            return f"![{f'[Image_{image_count}]'} {alt}]({src})"

        text = re.sub(
            r"!\[([^\]]*)\]\(([^)]+)\)",
            _tag_image,
            text,
        )

        return text, image_count

    def _ensure_page_anchors(self, text: str) -> tuple[str, int]:
        """确保文档有页面锚定标记。"""
        if "<!-- PAGE_START" in text:
            pages = re.findall(r"<!-- PAGE_START (\d+) -->", text)
            page_count = max(int(p) for p in pages) if pages else 1
            return text, page_count

        # 没有页面标记，整个文档视为第 1 页
        return f"<!-- PAGE_START 1 -->\n{text}\n<!-- PAGE_END 1 -->", 1

    def _cleanup_blank_lines(self, text: str) -> str:
        """清理连续 3 个以上的空行。"""
        return re.sub(r"\n{4,}", "\n\n\n", text)
