from app.services.platforms import get_platform_or_none


def build_strategy_preview(confirmed_copy: dict, active_platform_id: str) -> dict:
    profile = get_platform_or_none(active_platform_id)
    image_count = profile.default_image_count if profile else 5
    platform_name = profile.name if profile else active_platform_id

    if image_count >= 7:
        roles = ["hero", "selling_point", "scene", "detail", "lifestyle", "comparison", "white_bg"]
    else:
        roles = ["hero", "selling_point", "scene", "detail", "white_bg"]

    asset_plan = [{"role": role, "display_order": idx + 1} for idx, role in enumerate(roles)]

    return {
        "product_name": confirmed_copy.get("product_name", ""),
        "core_selling_point": confirmed_copy.get("selling_points", ""),
        "core_scene": confirmed_copy.get("usage_scenes", ""),
        "core_performance": confirmed_copy.get("specs", ""),
        "headline": confirmed_copy.get("headline", ""),
        "style_summary": " + ".join(
            [v for v in [confirmed_copy.get("style_choice"), confirmed_copy.get("style_custom")] if v]
        ),
        "platform_strategy": f"{platform_name} 主图标准，输出 {image_count} 张主图",
        "asset_plan": asset_plan,
    }
