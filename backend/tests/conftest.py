import os
import sys
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).parent))


def _make_fake_embedding(dim: int = 1024) -> list[float]:
    return [0.1] * dim


@pytest.fixture
async def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    with tempfile.TemporaryDirectory() as qdrant_dir:
        os.environ["SQLITE_PATH"] = db_path
        os.environ["QDRANT_URL"] = ""
        os.environ["QDRANT_LOCAL_PATH"] = qdrant_dir
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        os.environ["EMBEDDING_API_KEY"] = "test-key"

        import importlib

        import app.core.config as config_module
        importlib.reload(config_module)
        from app.core.config import Settings
        config_module.settings = Settings(
            sqlite_path=db_path,
            qdrant_url="",
            qdrant_local_path=qdrant_dir,
            deepseek_api_key="test-key",
            embedding_api_key="test-key",
        )

        import app.services.vectorstore as vs_module
        vs_module._client = None

        import app.services.embedding as emb_module
        emb_module._client = None

        from unittest.mock import AsyncMock, patch

        from app.db.sqlite_store import SqliteStore
        from app.main import app

        store = SqliteStore(db_path=db_path)
        app.state.store = store

        with patch("app.services.embedding.embed_text") as mock_embed_text, \
             patch("app.services.embedding.embed_texts") as mock_embed_texts, \
             patch("app.api.notes.embed_text") as mock_notes_embed_text:
            mock_embed_text.side_effect = lambda text: _make_fake_embedding() if text else []
            mock_embed_texts.side_effect = lambda texts: [_make_fake_embedding() for _ in texts] if texts else []
            mock_notes_embed_text.side_effect = lambda text: _make_fake_embedding() if text else []

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac

        store.close()
        vs_module._client = None
        emb_module._client = None

    try:
        os.unlink(db_path)
    except OSError:
        pass
