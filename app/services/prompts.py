def compose_prompt(
    confirmed_copy: dict,
    strategy_preview: dict,
    asset_role: str,
    instruction: str | None = None,
) -> str:
    base = [
        f"产品名称: {confirmed_copy.get('product_name', '')}",
        f"标题: {confirmed_copy.get('headline', '')}",
        f"卖点: {confirmed_copy.get('selling_points', '')}",
        f"场景: {confirmed_copy.get('usage_scenes', '')}",
        f"规格: {confirmed_copy.get('specs', '')}",
        f"风格: {strategy_preview.get('style_summary', '')}",
        f"本图角色: {asset_role}",
    ]
    if instruction:
        base.append(f"修改指令: {instruction}")
    return " | ".join(base)
