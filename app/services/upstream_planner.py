"""Upstream Planner API — facade for planner-related methods on WhataiClient.

Usage:
    from app.services.upstream_planner import WhataiClient
    client = WhataiClient()
    plan = client.plan_prompt_plan(...)
    narrative = client.plan_detail_page_narrative(...)
    copy_blocks = client.design_main_copy_blocks(...)
    refreshed = client.regenerate_copy(...)
"""
from app.services.upstream import WhataiClient

__all__ = ["WhataiClient"]
