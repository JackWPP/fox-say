"""PDF 类型探测器。

用 PyMuPDF 快速判断 PDF 是电子版（可提取文字）还是扫描件（需要 OCR）。
判定标准：>30% 的页面文字少于 20 字符且包含图片 → 扫描件。
"""

import logging

logger = logging.getLogger(__name__)

SCANNED_PAGE_TEXT_THRESHOLD = 20
SCANNED_PAGE_RATIO_THRESHOLD = 0.3


def detect_pdf_type(file_path: str) -> str:
    """探测 PDF 类型。

    Returns:
        "DIGITAL_PDF" 或 "SCANNED_PDF"
    """
    import fitz

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        logger.warning("PyMuPDF failed to open %s: %s, assuming DIGITAL_PDF", file_path, e)
        return "DIGITAL_PDF"

    total = len(doc)
    if total == 0:
        doc.close()
        return "DIGITAL_PDF"

    scanned_pages = 0
    for page in doc:
        text_len = len(page.get_text().strip())
        has_images = len(page.get_images()) > 0
        if text_len < SCANNED_PAGE_TEXT_THRESHOLD and has_images:
            scanned_pages += 1

    doc.close()

    ratio = scanned_pages / total
    pdf_type = "SCANNED_PDF" if ratio > SCANNED_PAGE_RATIO_THRESHOLD else "DIGITAL_PDF"
    logger.info(
        "PDF type detection for %s: %d/%d scanned pages (%.1f%%) → %s",
        file_path, scanned_pages, total, ratio * 100, pdf_type,
    )
    return pdf_type
