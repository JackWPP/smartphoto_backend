from fastapi import APIRouter

from app.api.admin import assets, audit, auth, dashboard, jobs, prompt_presets, rule_packs, sessions, system, users

router = APIRouter()
router.include_router(auth.router)
router.include_router(dashboard.router)
router.include_router(sessions.router)
router.include_router(jobs.router)
router.include_router(assets.router)
router.include_router(prompt_presets.router)
router.include_router(rule_packs.router)
router.include_router(audit.router)
router.include_router(users.router)
router.include_router(system.router)
