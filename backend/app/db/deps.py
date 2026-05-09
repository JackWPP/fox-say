from fastapi import Request

from app.db.sqlite_store import SqliteStore


def get_store(request: Request) -> SqliteStore:
    return request.app.state.store
