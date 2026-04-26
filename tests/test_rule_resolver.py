from app.services.rule_resolution import (
    resolve_detail_display_module_intent,
    resolve_detail_display_module_kind,
    resolve_detail_display_module_title,
    resolve_detail_page_context,
    resolve_detail_panel_rules,
    resolve_main_expression_metadata,
    resolve_main_platform_overlay,
    resolve_main_slot_rules,
)


def test_main_rule_resolver_uses_single_source_for_temu_defaults() -> None:
    rules = resolve_main_slot_rules("temu")

    assert [rule.slot_blueprint["slot_id"] for rule in rules] == [
        "hero",
        "white_bg",
        "selling_point",
        "scene",
        "detail",
    ]
    hero_rule = rules[0]
    assert hero_rule.slot_blueprint["platform_rule_pack_key"] == "default_main_gallery_v2"
    assert hero_rule.expression_metadata("clean_conversion_kv")["expression_label"]


def test_main_rule_resolver_keeps_alibaba_overlay_and_expression_metadata() -> None:
    overlay = resolve_main_platform_overlay("1688")
    meta = resolve_main_expression_metadata("click_through_headline", platform_id="1688")

    assert overlay["overlay_id"] == "1688"
    assert overlay["copy_language"] == "zh"
    assert meta["expression_mode"] == "click_through_headline"
    assert meta["copy_policy"] == "headline_plus_supporting"


def test_detail_rule_resolver_is_platform_aware_and_keeps_display_metadata() -> None:
    context = resolve_detail_page_context("1688")
    rules = resolve_detail_panel_rules("1688")

    assert context.rule_pack_id == "alibaba_detail_v1"
    assert context.overlay["overlay_id"] == "1688"
    assert context.copy_language == "zh"
    assert len(rules) == 8
    assert rules[0].panel_slot["slot_id"] == "detail_slot_01"
    assert resolve_detail_display_module_title("feature_proof", "detail_slot_03") == "核心卖点"
    assert resolve_detail_display_module_kind("feature_proof") == "卖点佐证"


def test_detail_display_intent_prefers_explicit_non_internal_text() -> None:
    intent = resolve_detail_display_module_intent(
        panel_type="feature_proof",
        panel_goal="静音除湿",
        copy_focus="",
        panel_type_reason="",
        sanitize=lambda value: str(value or "").strip(),
        is_internal_label=lambda value: "槽位" in str(value),
    )
    fallback_intent = resolve_detail_display_module_intent(
        panel_type="feature_proof",
        panel_goal="卖点槽位A",
        copy_focus="",
        panel_type_reason="",
        sanitize=lambda value: str(value or "").strip(),
        is_internal_label=lambda value: "槽位" in str(value),
    )

    assert intent == "静音除湿"
    assert fallback_intent == "突出核心卖点并补充可信佐证"


def test_detail_rule_resolver_split_points_keeps_legacy_full_width_bar_behavior() -> None:
    from app.services.detail_panel_library import _split_points

    assert _split_points("卖点A｜卖点B；卖点C") == ["卖点A", "卖点B", "卖点C"]
    assert _split_points("卖点A。卖点B") == ["卖点A。卖点B"]
