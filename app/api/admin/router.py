from fastapi import APIRouter

from app.api.admin import assets, audit, auth, brands, category_catalog, dashboard, jobs, platform_configs, prompt_presets, rule_packs, sessions, system

router = APIRouter()
router.include_router(auth.router)
router.include_router(dashboard.router)
router.include_router(sessions.router)
router.include_router(jobs.router)
router.include_router(assets.router)
router.include_router(prompt_presets.router)
router.include_router(brands.router)
router.include_router(category_catalog.router)
router.include_router(rule_packs.router)
router.include_router(audit.router)
router.include_router(system.router)
router.include_router(platform_configs.router)
