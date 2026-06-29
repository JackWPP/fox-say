import logging

import pdfplumber

logger = logging.getLogger(__name__)


def parse_pdf(file_path: str, use_docling: bool | None = None) -> str:
    if use_docling is None:
        from app.core.config import settings
        use_docling = settings.pdf_parser == "docling"

    if use_docling:
        try:
            from app.services.parsing_docling import parse_pdf_docling, docling_to_flat_text

            chunks = parse_pdf_docling(file_path)
            if chunks:
                return docling_to_flat_text(chunks)
        except Exception:
            logger.warning("Docling parse failed for %s, falling back to pdfplumber", file_path)

    pages: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


def parse_text(file_path: str) -> str:
    with open(file_path, encoding="utf-8") as f:
        return f.read()


def parse_pptx(file_path: str) -> str:
    from pptx import Presentation

    prs = Presentation(file_path)
    slides: list[str] = []
    for slide in prs.slides:
        texts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = para.text.strip()
                    if t:
                        texts.append(t)
        if texts:
            slides.append("[Slide] " + "\n".join(texts))
    return "\n\n".join(slides)


def parse_with_markitdown(file_path: str) -> str:
    """Layer 1: markitdown 统一解析入口,支持 PDF/PPT/Word/HTML/图片等格式。

    输出 Markdown 文本。失败时抛异常给上层(HEC-1,不静默吞错)。
    """
    from markitdown import MarkItDown

    md = MarkItDown()
    result = md.convert(file_path)
    return result.text_content or ""


def parse_image_via_mineru(file_path: str) -> str:
    """Layer 3 for image: 走 MinerU 云端 OCR。

    复用 mineru.py 现有的 parse_pdf_mineru 流程(MinerU API 对 PDF/图片用同一端点)。
    [未验证] MinerU 对图片的支持,若不支持会返回 error,上层会捕获并标记 failed。
    """
    from app.services.mineru import parse_pdf_mineru

    md_text, err = parse_pdf_mineru(file_path)
    if err:
        raise RuntimeError(f"MinerU image OCR failed: {err}")
    if not md_text:
        raise RuntimeError("MinerU image OCR returned empty content")
    return md_text


def parse_document(file_path: str, kind: str) -> str:
    """三层 fallback 解析链:

    Layer 1: markitdown 统一入口(支持 pdf/ppt/word/html/图片)
    Layer 2: 原生解析器(pdfplumber / python-pptx / utf-8 open)
    Layer 3: MinerU 云端 OCR(仅 PDF/图片,作为最后兜底)

    所有 Layer 失败时抛异常(HEC-1),由调用方决定降级或标记 failed。
    """
    # Layer 1: markitdown 统一入口
    try:
        text = parse_with_markitdown(file_path)
        if text and len(text.strip()) > 50:
            return text
        logger.info(
            "markitdown returned thin content for %s (len=%d), falling back to native parser",
            file_path, len(text.strip() if text else 0),
        )
    except Exception as e:
        logger.warning("markitdown failed for %s: %s, falling back to native parser", file_path, e)

    # Layer 2: 原生解析器
    if kind == "pdf":
        return parse_pdf(file_path)
    if kind == "ppt":
        return parse_pptx(file_path)
    if kind == "text_note":
        return parse_text(file_path)
    if kind == "image":
        # Layer 3 for image: MinerU OCR(markitdown 失败后无原生解析器,直接走云端)
        return parse_image_via_mineru(file_path)
    raise ValueError(f"Unsupported material kind: {kind}")
