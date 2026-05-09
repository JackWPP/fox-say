import pdfplumber


def parse_pdf(file_path: str) -> str:
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


def parse_document(file_path: str, kind: str) -> str:
    if kind == "pdf":
        return parse_pdf(file_path)
    if kind == "text_note":
        return parse_text(file_path)
    if kind == "ppt":
        return parse_pptx(file_path)
    raise ValueError(f"Unsupported material kind: {kind}")
