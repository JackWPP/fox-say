from openai import OpenAI

from app.core.config import settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = settings.embedding_api_key or settings.deepseek_api_key or "placeholder"
        base_url = settings.embedding_api_base
        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client


EMBEDDING_BATCH_SIZE = 64


def embed_text(text: str) -> list[float]:
    if not text:
        return []
    embeddings = embed_texts([text])
    return embeddings[0] if embeddings else []


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = _get_client()
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + EMBEDDING_BATCH_SIZE]
        response = client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
        )
        all_embeddings.extend(item.embedding for item in response.data)
    return all_embeddings
