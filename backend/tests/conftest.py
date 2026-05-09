import os
import sys
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).parent))

from app.db.sqlite_store import SqliteStore
from app.main import app


@pytest.fixture
async def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    store = SqliteStore(db_path=db_path)
    app.state.store = store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    store.close()
    os.unlink(db_path)
