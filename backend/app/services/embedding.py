from openai import OpenAI

from app.core.config import Settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        settings = Settings()
        api_key = settings.deepseek_api_key or "placeholder"
        _client = OpenAI(api_key=api_key, base_url=settings.deepseek_api_base)
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = _get_client()
    response = client.embeddings.create(
        model="text-embedding-v3",
        input=texts,
    )
    return [item.embedding for item in response.data]
