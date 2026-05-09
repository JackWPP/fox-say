from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.courses import router as courses_router
from app.api.materials import router as materials_router
from app.api.review import router as review_router
from app.api.skeleton import router as skeleton_router

app = FastAPI(title="FoxSay API")

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
