def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[dict]:
    if not text:
        return []
    chunks: list[dict] = []
    start = 0
    index = 0
    while start < len(text):
        end = start + chunk_size
        chunk_content = text[start:end]
        chunks.append({
            "index": index,
            "text": chunk_content,
        })
        index += 1
        start = end - overlap
        if start >= len(text):
            break
    return chunks
