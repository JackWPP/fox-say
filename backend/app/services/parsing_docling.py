"""PDF parsing via Docling for hierarchical structure preservation."""

import logging

logger = logging.getLogger(__name__)


def parse_pdf_docling(file_path: str) -> list[dict]:
    """Parse a PDF using Docling, preserving headings, pages, and hierarchy.

    Returns a list of chunks, each with: text, heading, level, page.
    Falls back to returning empty list on any error.
    """
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        logger.warning("Docling not installed, falling back to pdfplumber")
        return []

    try:
        converter = DocumentConverter()
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
    """Convert Docling chunks to a flat text representation with structure markers."""
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
