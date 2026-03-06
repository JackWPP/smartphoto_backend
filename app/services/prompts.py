def compose_prompt(
    confirmed_copy: dict,
    strategy_preview: dict,
    asset_role: str,
    instruction: str | None = None,
) -> str:
    product_name = confirmed_copy.get("product_name", "") or "产品"
    headline = confirmed_copy.get("headline", "")
    selling_points = confirmed_copy.get("selling_points", "")
    usage_scenes = confirmed_copy.get("usage_scenes", "")
    specs = confirmed_copy.get("specs", "")
    style = (
        strategy_preview.get("style_summary")
        or confirmed_copy.get("style_custom")
        or confirmed_copy.get("style_choice")
        or "简洁电商风格"
    )

    parts = [
        f"请生成一张用于电商展示的{asset_role}图片，主体是{product_name}。",
        f"重点表达{headline}。" if headline else "",
        f"突出这些卖点：{selling_points}。" if selling_points else "",
        f"适用场景为：{usage_scenes}。" if usage_scenes else "",
        f"可体现这些规格信息：{specs}。" if specs else "",
        f"整体视觉风格为：{style}。",
        "画面保持干净、主体清晰、适合商品展示。",
    ]
    if instruction:
        parts.append(f"另外请遵循这个修改要求：{instruction}。")
    return " ".join(part for part in parts if part)
