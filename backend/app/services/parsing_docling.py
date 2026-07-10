"""Docling 本地 PDF 解析器。

处理电子版 PDF：利用 Docling 的 DoclingDocument 结构树提取标题层级，
TableFormer 还原复杂表格，输出带页面锚定的结构化 Markdown。
"""

import logging
import uuid
from pathlib import Path

from app.services.parser_interface import (
    BaseDocumentParser,
    BoundingBox,
    DocumentParsingException,
    ExtractedAssetMeta,
    UnifiedParserOutput,
)

logger = logging.getLogger(__name__)

_converter = None


def _get_converter():
    global _converter
    if _converter is None:
        from docling.document_converter import DocumentConverter
        _converter = DocumentConverter()
    return _converter


class DoclingParser(BaseDocumentParser):
    """电子版 PDF 解析器，基于 IBM Docling。"""

    def can_handle(self, file_extension: str) -> bool:
        return file_extension.lower() == ".pdf"

    def parse(self, file_path: Path, storage_root: Path, **kwargs) -> UnifiedParserOutput:
        try:
            converter = _get_converter()
        except ImportError:
            raise DocumentParsingException(
                file_path, "Docling is not installed. Run: uv add docling"
            )

        try:
            result = converter.convert(str(file_path))
            doc = result.document
        except Exception as e:
            raise DocumentParsingException(file_path, "Docling conversion failed", e)

        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        # 使用 export_to_markdown() 获取完整的结构化 Markdown
        try:
            markdown_content = doc.export_to_markdown()
        except Exception as e:
            raise DocumentParsingException(file_path, "Docling markdown export failed", e)

        if not markdown_content or not markdown_content.strip():
            raise DocumentParsingException(file_path, "Docling produced empty markdown")

        # 提取资产（图片、表格）
        extracted_assets: list[ExtractedAssetMeta] = []
        page_count = 0
        img_output_dir = storage_root / doc_id
        img_output_dir.mkdir(parents=True, exist_ok=True)

        # 统计页面数
        try:
            page_count = len(doc.pages) if hasattr(doc, "pages") else 0
        except Exception:
            pass

        # 尝试提取图片资产
        img_counter = 0
        try:
            for item in doc.iterate_items():
                item_label = str(getattr(item, "label", ""))
                if item_label in ("picture", "Picture", "figure", "Figure", "PIC"):
                    img_counter += 1
                    img_name = f"page_{img_counter}_img_{img_counter}.png"
                    img_path = img_output_dir / img_name
                    saved = False
                    try:
                        if hasattr(item, "save_as_image"):
                            item.save_as_image(str(img_path))
                            saved = img_path.exists()
                    except Exception:
                        pass
                    if saved:
                        asset = ExtractedAssetMeta(
                            element_id=f"img_{uuid.uuid4().hex[:8]}",
                            element_type="Image",
                            sequential_label=f"[Image_{img_counter}]",
                            page_number=img_counter,
                            storage_path=f"images/{doc_id}/{img_name}",
                        )
                        extracted_assets.append(asset)
        except Exception as e:
            logger.warning("Failed to extract assets from Docling: %s", e)

        # 添加页面锚定（如果 export_to_markdown 没有自带的话）
        if "<!-- PAGE_START" not in markdown_content and page_count > 0:
            markdown_content = f"<!-- PAGE_START 1 -->\n{markdown_content}\n<!-- PAGE_END {page_count} -->"

        logger.info(
            "Docling parsed %s: %d chars, %d pages, %d assets",
            file_path.name, len(markdown_content), page_count, len(extracted_assets),
        )

        return UnifiedParserOutput(
            document_id=doc_id,
            raw_input_type="DIGITAL_PDF",
            markdown_content=markdown_content,
            extracted_assets=extracted_assets,
            page_count=page_count,
            parser_name="Docling",
        )

    def _extract_table_html(self, item) -> str | None:
        """尝试从 Docling item 提取表格 HTML。"""
        try:
            if hasattr(item, "export_to_html"):
                return item.export_to_html()
        except Exception:
            pass
        return None

    def _table_to_markdown(self, item) -> str:
        """尝试将简单表格转为 Markdown GFM 格式。"""
        try:
            if hasattr(item, "export_to_markdown"):
                return item.export_to_markdown()
        except Exception:
            pass
        return str(getattr(item, "text", ""))

    def _extract_image(self, item, output_path: Path) -> bool:
        """尝试从 Docling item 提取图片到文件。"""
        try:
            if hasattr(item, "save_as_image"):
                item.save_as_image(str(output_path))
                return output_path.exists()
        except Exception:
            pass
        return False

    def _extract_bbox(self, item) -> BoundingBox | None:
        """从 Docling item 提取 BBox 坐标。"""
        try:
            if hasattr(item, "bbox") and item.bbox is not None:
                bbox = item.bbox
                return BoundingBox(
                    x0=float(bbox.l),
                    y0=float(bbox.t),
                    x1=float(bbox.r),
                    y1=float(bbox.b),
                )
        except Exception:
            pass
        return None


# 模块级便捷函数（兼容旧调用方式）
def parse_pdf_docling(file_path: str) -> list[dict]:
    """向后兼容的便捷接口。返回旧格式 chunks。新代码请使用 DoclingParser 类。"""
    try:
        converter = _get_converter()
    except ImportError:
        logger.warning("Docling not installed, falling back to pdfplumber")
        return []

    try:
        result = converter.convert(file_path)
        doc = result.document
    except Exception:
        logger.exception("Docling conversion failed for %s", file_path)
        return []

    chunks: list[dict] = []
    try:
        current_heading = ""
        current_level = 0
        for item in doc.iterate_items():
            text = ""
            page = 0

            if hasattr(item, "label"):
                lvl_str = str(item.label)
                if lvl_str.startswith("heading"):
                    try:
                        current_level = int(lvl_str.replace("heading", ""))
                    except ValueError:
                        current_level = 1
                    current_heading = str(item.text) if hasattr(item, "text") and item.text else ""
                    continue

            if hasattr(item, "text") and item.text:
                text = str(item.text).strip()
            if hasattr(item, "page_no") and item.page_no is not None:
                page = int(item.page_no)

            if text:
                chunks.append({
                    "text": text,
                    "heading": current_heading,
                    "level": current_level,
                    "page": page,
                })
    except Exception:
        logger.exception("Error iterating Docling document for %s", file_path)
        return []

    return chunks


def docling_to_flat_text(chunks: list[dict]) -> str:
    """Convert Docling chunks to flat text with structure markers."""
    parts: list[str] = []
    current_heading = ""
    for chunk in chunks:
        heading = chunk.get("heading", "")
        level = chunk.get("level", 0)
        text = chunk.get("text", "")
        if heading and heading != current_heading:
            prefix = "#" * min(level + 1, 6) if level > 0 else "#"
            parts.append(f"\n{prefix} {heading}")
            current_heading = heading
        if text:
            parts.append(text)
    return "\n\n".join(parts)
