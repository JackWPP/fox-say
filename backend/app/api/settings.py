from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore

router = APIRouter(prefix="/user")


class UserSettingsResponse(BaseModel):
    mode: str
    onboarding_done: bool


class UpdateModeRequest(BaseModel):
    mode: str


@router.get("/settings", response_model=UserSettingsResponse)
async def get_settings(store: SqliteStore = Depends(get_store)):
    mode = store.get_user_setting("mode", "study")
    onboarding_done = store.get_user_setting("onboarding_done", "") == "true"
    return UserSettingsResponse(mode=mode, onboarding_done=onboarding_done)


@router.put("/settings/mode")
async def update_mode(body: UpdateModeRequest, store: SqliteStore = Depends(get_store)):
    if body.mode not in ("exam", "study"):
        return {"error": "mode must be 'exam' or 'study'"}, 400
    store.set_user_setting("mode", body.mode)
    return {"mode": body.mode}


@router.put("/settings/onboarding")
async def complete_onboarding(store: SqliteStore = Depends(get_store)):
    store.set_user_setting("onboarding_done", "true")
    return {"onboarding_done": True}
