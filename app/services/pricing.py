from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class PricingRule:
    rule_id: str
    action: str
    credits: int
    description: str


def get_pricing_rule(action: str) -> PricingRule:
    settings = get_settings()
    rules = settings.parsed_credit_pricing_rules()
    config = rules.get(action) or {"credits": 0, "description": action}
    return PricingRule(
        rule_id=f"pricing:{action}",
        action=action,
        credits=int(config.get("credits") or 0),
        description=str(config.get("description") or action),
    )


def list_pricing_rules() -> list[PricingRule]:
    settings = get_settings()
    rules = settings.parsed_credit_pricing_rules()
    ordered = []
    for action in (
        "generate_gallery",
        "generate_detail_page",
        "global_edit",
        "regenerate_asset",
        "regenerate_detail_panel",
        "regenerate_gallery",
    ):
        config = rules.get(action)
        if config is None:
            continue
        ordered.append(
            PricingRule(
                rule_id=f"pricing:{action}",
                action=action,
                credits=int(config.get("credits") or 0),
                description=str(config.get("description") or action),
            )
        )
    return ordered
