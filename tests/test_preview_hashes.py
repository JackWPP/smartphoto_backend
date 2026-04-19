from app.services.detail_pages import _detail_preview_hash_bundle
from app.services.preview_hashing import PREVIEW_HASH_POLICY_VERSION
from app.services.strategy import _main_preview_hash_bundle


def _main_hash_bundle(**overrides):
    payload = {
        "normalized_copy": {
            "product_name": "Air purifier",
            "category": "home_appliance",
            "headline": "Quiet clean air",
            "hero_scene": "living room corner",
            "core_selling_points": ["quiet purification"],
            "key_parameters": [{"key": "cadr", "label": "CADR", "value": "500", "unit": "m3/h"}],
            "product_advantages": ["pet friendly"],
            "style_preset_id": "preset-1",
            "style_custom": "clean premium",
            "resolved_style_preset": {"id": "preset-1", "name": "Premium", "style_summary": "clean premium"},
        },
        "active_platform_id": "temu",
        "overlay": {"overlay_id": "temu", "copy_language": "en"},
        "slot_blueprints": [
            {
                "slot_id": "hero",
                "slot_family": "hero",
                "candidate_expression_modes": ["hero_scene"],
                "layout_recipe": {"headline_zone": "top"},
                "platform_rule_pack": "default_main_gallery_v2",
            }
        ],
        "analysis_snapshot": {
            "reference_summary": {"shape": "cylindrical"},
            "risk_flags": ["scene_entity_sensitive"],
            "selling_point_entities": ["filter"],
            "detected_view_slots": ["front"],
            "reanalysis_required": False,
            "scene_tags": ["home"],
            "supplement_image_recommendations": [{"slot_type": "side"}],
        },
        "parameter_snapshot": {
            "feature_highlights": ["premium look"],
            "evidence_summary": [{"source": "attachment"}],
        },
        "planner_instruction": "keep it clean",
        "resolved_slot_preferences": {"hero": {"slot_id": "hero", "expression_mode": "hero_scene"}},
        "resolved_prompt_overrides": {
            "hero": {
                "copy_blocks_override": {"headline": "Override headline"},
                "raw_prompt_override": "extra clean",
                "applied_preset_id": "preset-1",
                "applied_preset": {"copy_blocks_template": {"headline": "Template headline"}},
            }
        },
        "reference_manifest": [{"image_id": "img-1", "slot_type": "front", "display_order": 1, "width": 1000}],
        "strategy_reference_manifest": [{"image_id": "style-1", "slot_type": "extra", "display_order": 2, "width": 900}],
        "planner_profile": "default",
        "planner_provider": "whatai",
        "planner_model": "gemini-main",
    }
    payload.update(overrides)
    return _main_preview_hash_bundle(**payload)


def _detail_hash_bundle(**overrides):
    class _RulePack:
        rule_pack_key = "detail_default"

    class _RulePackVersion:
        version_no = 3

    class _PanelRule:
        def __init__(self):
            self.panel_slot = {
                "slot_id": "detail_slot_01",
                "panel_id": "panel_01_cover",
                "default_panel_type": "feature_benefit",
                "candidate_panel_types": ["feature_benefit", "feature_scene"],
            }

    class _Context:
        rule_pack_id = "detail_rule_pack"
        rule_pack = _RulePack()
        rule_pack_version = _RulePackVersion()
        panel_rules = [_PanelRule()]
        panel_type_library = {
            "feature_benefit": {"label": "benefit", "layout_template": "feature_card", "copy_policy": "headline_plus_supporting"}
        }

    payload = {
        "confirmed_copy": {
            "product_name": "Dryer",
            "category": "appliance",
            "headline": "Fast drying",
            "hero_scene": "bathroom",
            "core_selling_points": ["fast dry"],
            "key_parameters": [{"key": "power", "label": "Power", "value": "1200", "unit": "W"}],
            "product_advantages": ["compact"],
            "style_preset_id": "preset-2",
            "style_custom": "clean modern",
            "resolved_style_preset": {"id": "preset-2", "name": "Modern", "style_summary": "clean modern"},
        },
        "product_manifest": [{"image_id": "product-1", "slot_type": "front", "display_order": 1, "width": 1200}],
        "style_manifest": [{"image_id": "style-1", "display_order": 1, "width": 800}],
        "planner_instruction": "short headline",
        "panel_preferences": {"detail_slot_01": {"slot_id": "detail_slot_01", "panel_type": "feature_benefit"}},
        "active_platform_id": "1688",
        "prompt_overrides": {
            "detail_slot_01": {
                "copy_blocks_override": {"headline": "Rule override"},
                "raw_prompt_override": "use bold title",
            }
        },
        "analysis_snapshot": {
            "reference_summary": {"shape": "tower"},
            "risk_flags": ["needs_simple_layout"],
            "reanalysis_required": False,
        },
        "planner_profile": "default",
        "planner_provider": "whatai",
        "planner_model": "gemini-detail",
        "detail_rule_context": _Context(),
        "platform_overlay": {"overlay_id": "1688", "copy_language": "zh"},
    }
    payload.update(overrides)
    return _detail_preview_hash_bundle(**payload)


def test_main_hash_bundle_exposes_layer_metadata():
    result = _main_hash_bundle()

    assert result["hash_policy_version"] == PREVIEW_HASH_POLICY_VERSION
    assert set(result["hash_layers"].keys()) == {"config_hash", "content_hash", "reference_hash", "memory_hash"}
    assert result["input_hash"]


def test_main_hash_ignores_non_consumed_debug_fields():
    base = _main_hash_bundle()
    changed = _main_hash_bundle(
        analysis_snapshot={
            "reference_summary": {"shape": "cylindrical"},
            "risk_flags": ["scene_entity_sensitive"],
            "selling_point_entities": ["filter"],
            "detected_view_slots": ["front"],
            "reanalysis_required": True,
            "scene_tags": ["office", "home"],
            "supplement_image_recommendations": [{"slot_type": "extra"}],
        },
        parameter_snapshot={
            "feature_highlights": ["premium look"],
            "evidence_summary": [{"source": "db"}],
        },
    )

    assert changed["hash_layers"]["content_hash"] == base["hash_layers"]["content_hash"]
    assert changed["input_hash"] == base["input_hash"]


def test_main_hash_changes_when_consumed_content_or_reference_changes():
    base = _main_hash_bundle()
    content_changed = _main_hash_bundle(parameter_snapshot={"feature_highlights": ["editorial look"]})
    reference_changed = _main_hash_bundle(reference_manifest=[{"image_id": "img-2", "slot_type": "front", "display_order": 1}])

    assert content_changed["hash_layers"]["content_hash"] != base["hash_layers"]["content_hash"]
    assert reference_changed["hash_layers"]["reference_hash"] != base["hash_layers"]["reference_hash"]


def test_detail_hash_ignores_non_consumed_debug_fields():
    base = _detail_hash_bundle()
    changed = _detail_hash_bundle(
        analysis_snapshot={
            "reference_summary": {"shape": "tower"},
            "risk_flags": ["needs_simple_layout"],
            "reanalysis_required": True,
            "category_candidates": [{"name": "dryer"}],
        }
    )

    assert changed["hash_layers"]["content_hash"] == base["hash_layers"]["content_hash"]
    assert changed["input_hash"] == base["input_hash"]


def test_detail_hash_changes_when_headline_override_or_reference_changes():
    base = _detail_hash_bundle()
    headline_changed = _detail_hash_bundle(
        confirmed_copy={
            "product_name": "Dryer",
            "category": "appliance",
            "headline": "Ultra fast drying",
            "hero_scene": "bathroom",
            "core_selling_points": ["fast dry"],
            "key_parameters": [{"key": "power", "label": "Power", "value": "1200", "unit": "W"}],
            "product_advantages": ["compact"],
            "style_preset_id": "preset-2",
            "style_custom": "clean modern",
        }
    )
    reference_changed = _detail_hash_bundle(style_manifest=[{"image_id": "style-2", "display_order": 1}])

    assert headline_changed["hash_layers"]["content_hash"] != base["hash_layers"]["content_hash"]
    assert reference_changed["hash_layers"]["reference_hash"] != base["hash_layers"]["reference_hash"]
