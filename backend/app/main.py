from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.courses import router as courses_router
from app.api.materials import router as materials_router
from app.api.review import router as review_router
from app.api.skeleton import router as skeleton_router
from app.core.config import settings
from app.db.sqlite_store import SqliteStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = SqliteStore(db_path=settings.sqlite_path)
    app.state.store = store
    yield
    store.close()


app = FastAPI(title="FoxSay API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


def _register_routers() -> None:
    app.include_router(courses_router)
    app.include_router(materials_router)
    app.include_router(skeleton_router)
    app.include_router(chat_router)
    app.include_router(review_router)


_register_routers()
