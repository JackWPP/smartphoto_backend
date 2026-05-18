"""Copy Planner Agent — dedicated LLM node for planning image text layout.

Uses DeepSeek (fast, cheap) to plan what text goes on each image slot.
Returns structured TextPlan that feeds into prompt composition.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.llm_router import LLMRouter

logger = logging.getLogger(__name__)

COPY_PLANNER_PROMPT = """你是电商主图文案规划师。根据商品信息，为每个主图槽位规划图上文字。

商品信息：
- 产品名：{product_name}
- 主标题：{headline}
- 核心卖点：{selling_points}
- 使用场景：{hero_scene}
- 产品优势：{advantages}
- 关键参数：{key_params}

{slot_name}的职责：{slot_goal}

要求：
1. 最多 {max_elements} 个文字元素
2. 每个元素不超过 {max_chars} 字
3. 使用给定的产品信息，不要编造
4. 不要使用"品质之选""匠心制造"等空洞营销词
5. 场景描述（如"{hero_scene}"）是构图参考，不要作为图上文字

只返回 JSON：
{{"elements": [{{"role": "headline|supporting|label", "text": "..."}}]}}"""


def plan_slot_copy(
    *,
    confirmed_copy: dict[str, Any],
    slot_id: str,
    slot_goal: str,
    slot_name: str,
    max_elements: int = 4,
    max_chars: int = 16,
    router: LLMRouter | None = None,
) -> list[dict[str, str]]:
    """Plan text elements for a single image slot using DeepSeek."""
    if router is None:
        router = LLMRouter()

    if not router.is_available_for_route("deepseek_text"):
        # Fallback: use template-based planning
        from app.services.prompts import build_text_elements
        from app.services.main_gallery_rules import build_copy_blocks, get_main_gallery_slot_blueprints
        for bp in get_main_gallery_slot_blueprints("taobao"):
            if bp["slot_id"] == slot_id:
                cb = build_copy_blocks(platform_id="taobao", slot_blueprint=bp, confirmed_copy=confirmed_copy, expression_mode="clean_packshot")
                return build_text_elements(cb)
        return build_text_elements(confirmed_copy)

    product_name = str(confirmed_copy.get("product_name", ""))
    headline = str(confirmed_copy.get("headline", ""))
    selling_points = ", ".join(confirmed_copy.get("core_selling_points") or [])
    hero_scene = str(confirmed_copy.get("hero_scene", ""))
    advantages = ", ".join(confirmed_copy.get("product_advantages") or [])
    key_params = ", ".join(
        f"{p.get('label','')}{p.get('value','')}{p.get('unit','')}"
        for p in (confirmed_copy.get("key_parameters") or [])[:5]
    )

    prompt = COPY_PLANNER_PROMPT.format(
        product_name=product_name, headline=headline,
        selling_points=selling_points, hero_scene=hero_scene,
        advantages=advantages, key_params=key_params,
        slot_name=slot_name, slot_goal=slot_goal,
        max_elements=max_elements, max_chars=max_chars,
    )

    try:
        result = router.complete_json_with_meta(
            task="main_copy_design",
            messages=[{"role": "user", "content": prompt}],
            error_key="copy_planner",
            temperature=0.3,
        )
        parsed = result.get("result") or {}
        elements = parsed.get("elements") or []
        # Ensure each element has id
        for i, e in enumerate(elements):
            if "id" not in e:
                e["id"] = f"e{i+1}"
        return elements
    except Exception:
        logger.exception("Copy planner LLM call failed, using template fallback")
        from app.services.prompts import build_text_elements
        return build_text_elements(confirmed_copy)
