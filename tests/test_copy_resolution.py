from app.services.copy_resolution import (
    COPY_META_KEY,
    apply_explicit_copy_input_with_attribution,
    apply_parameter_snapshot_with_attribution,
    resolve_session_copy,
)
from app.services.detail_pages import _rebuild_detail_copy_blocks_attribution
from app.services.strategy import _apply_main_copy_design


def test_apply_explicit_copy_input_with_attribution_records_sources():
    payload = apply_explicit_copy_input_with_attribution(
        {},
        {
            "product_name": "Air purifier",
            "hero_scene": "living room corner",
            "core_selling_points": ["quiet purification", "pet friendly"],
            "style_preset_id": "preset-1",
            "style_custom": "minimal clean look",
        },
    )

    meta = payload[COPY_META_KEY]
    assert meta["product_name"]["source"] == "explicit_input"
    assert meta["hero_scene"]["source"] == "explicit_input"
    assert [item["source"] for item in meta["core_selling_points"]] == ["explicit_input", "explicit_input"]
    assert meta["style_preset_id"]["source"] == "explicit_input"


def test_resolve_session_copy_prefers_explicit_copy_over_parameter_backfill():
    confirmed_copy = apply_explicit_copy_input_with_attribution(
        {},
        {
            "hero_scene": "explicit scene",
            "core_selling_points": ["explicit point"],
            "style_custom": "explicit style",
        },
    )

    resolution = resolve_session_copy(
        confirmed_copy,
        parameter_snapshot={
            "hero_scene": "parameter scene",
            "core_selling_points": ["parameter point"],
            "product_advantages": ["parameter advantage"],
            "feature_highlights": ["parameter style"],
        },
    )

    assert resolution["copy"]["hero_scene"] == "explicit scene"
    assert resolution["copy"]["core_selling_points"] == ["explicit point"]
    assert resolution["copy"]["style_custom"] == "explicit style"
    assert resolution["copy"]["product_advantages"] == ["parameter advantage"]
    assert resolution["copy_attribution"]["hero_scene"]["source"] == "explicit_input"
    assert resolution["copy_attribution"]["core_selling_points"][0]["source"] == "explicit_input"
    assert resolution["copy_attribution"]["style_custom"]["source"] == "explicit_input"
    assert resolution["copy_attribution"]["product_advantages"][0]["source"] == "parameter_primary"


def test_apply_parameter_snapshot_with_attribution_backfills_only_empty_fields_when_not_overwriting():
    confirmed_copy = apply_explicit_copy_input_with_attribution(
        {},
        {
            "hero_scene": "explicit scene",
            "core_selling_points": ["explicit point"],
        },
    )

    updated = apply_parameter_snapshot_with_attribution(
        confirmed_copy,
        {
            "hero_scene": "parameter scene",
            "core_selling_points": ["parameter point"],
            "product_advantages": ["parameter advantage"],
        },
        overwrite=False,
    )

    assert updated["hero_scene"] == "explicit scene"
    assert updated["core_selling_points"] == ["explicit point"]
    assert updated["product_advantages"] == ["parameter advantage"]
    assert updated[COPY_META_KEY]["hero_scene"]["source"] == "explicit_input"
    assert updated[COPY_META_KEY]["product_advantages"][0]["source"] == "parameter_primary"


def test_apply_main_copy_design_treats_explicit_empty_override_as_session_override():
    asset_plan = [
        {
            "slot_id": "hero",
            "copy_blocks": {
                "headline": "Explicit headline",
                "proof_lines": [],
            },
        }
    ]
    prompt_plan = [
        {
            "slot_id": "hero",
            "copy_blocks": {
                "headline": "Explicit headline",
                "proof_lines": [],
            },
        }
    ]
    copy_design_plan = {
        "hero": {
            "headline": "Planner headline",
            "proof_lines": ["Planner proof"],
        }
    }

    next_asset_plan, next_prompt_plan = _apply_main_copy_design(asset_plan, prompt_plan, copy_design_plan)

    assert next_asset_plan[0]["copy_blocks"]["proof_lines"] == []
    assert next_asset_plan[0]["copy_blocks_attribution"]["proof_lines"]["source"] == "session_override"
    assert next_prompt_plan[0]["copy_blocks"]["proof_lines"] == []
    assert next_prompt_plan[0]["copy_blocks_attribution"]["proof_lines"]["source"] == "session_override"


def test_rebuild_detail_copy_blocks_attribution_marks_changed_fields_as_sanitized():
    rebuilt = _rebuild_detail_copy_blocks_attribution(
        {
            "headline": "fallback headline",
            "supporting": "",
        },
        base_attribution={
            "headline": {
                "source": "rule_based",
                "source_path": "detail_panel_plan.detail_slot_01.copy_blocks.headline",
                "source_stage": "detail_strategy_preview",
                "fallback_used": False,
                "sanitized": False,
            }
        },
        original_copy_blocks={
            "headline": "SAVE $999 NOW!!!",
            "supporting": "",
        },
        sanitized_fields=["headline"],
        default_source="rule_based",
        default_source_path_prefix="detail_panel_plan.detail_slot_01.copy_blocks",
    )

    assert rebuilt["headline"]["sanitized"] is True
    assert rebuilt["headline"]["source"] == "rule_based"
