from fastapi import APIRouter

from app.api.v2.account import router as account_router
from app.api.v2.auth import router as auth_router
from app.api.v2.assets import router as assets_router
from app.api.v2.jobs import router as jobs_router
from app.api.v2.platforms import router as platforms_router
from app.api.v2.prompt_presets import router as prompt_presets_router
from app.api.v2.sessions import router as sessions_router
from app.api.v2.uploads import router as uploads_router

router = APIRouter()
router.include_router(platforms_router)
router.include_router(auth_router)
router.include_router(account_router)
router.include_router(uploads_router)
router.include_router(sessions_router)
router.include_router(jobs_router)
router.include_router(assets_router)
router.include_router(prompt_presets_router)
