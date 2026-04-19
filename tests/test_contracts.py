from __future__ import annotations

from pydantic import ValidationError

from app.contracts.copy import DetailCopyBlocks, MainCopyBlocks
from app.contracts.detail_strategy import DetailStrategyPreviewPayload
from app.contracts.generation import DetailGenerationSnapshot, MainGenerationSnapshot
from app.contracts.parameter import ParameterSnapshotPayload
from app.contracts.strategy import StrategyPreviewPayload


def test_main_copy_blocks_round_trip_preserves_extra_fields() -> None:
    raw = {
        "headline": "Main headline",
        "supporting": "Support copy",
        "proof_lines": ["Proof 1"],
        "matrix_lines": ["Matrix 1"],
        "extra_debug": {"source": "fixture"},
    }

    model = MainCopyBlocks.from_dict(raw)

    assert model.to_dict() == raw


def test_detail_copy_blocks_round_trip_preserves_extra_fields() -> None:
    raw = {
        "headline": "Headline",
        "supporting": "Support",
        "bullet_points": ["Point 1"],
        "proof_lines": ["Proof"],
        "cta_line": "See more",
        "debug_note": "keep-me",
    }

    model = DetailCopyBlocks.from_dict(raw)

    assert model.to_dict() == raw


def test_strategy_preview_contract_round_trip() -> None:
    raw = {
        "platform_rule_pack": "default_main_gallery_v2",
        "platform_overlay": {"overlay_id": "temu", "copy_language": "en"},
        "reference_manifest": [{"image_id": "img-1", "slot_type": "front", "display_order": 1}],
        "strategy_reference_manifest": [],
        "asset_plan": [
            {
                "slot_id": "hero",
                "role": "hero",
                "display_order": 1,
                "aspect_ratio": "1:1",
                "text_policy": "short_copy_required",
                "background_mode": "scene",
                "composition_hint": "center composition",
                "expression_mode": "hero_scene",
                "copy_blocks": {
                    "headline": "Air purifier",
                    "supporting": "",
                    "proof_lines": ["Quiet mode"],
                    "matrix_lines": [],
                },
                "copy_blocks_attribution": {"headline": {"source": "session_override"}},
                "platform_rule_pack": "default_main_gallery_v2",
                "rule_modules_used": ["hero_scene"],
                "truth_contract": {"hard_constraint_summary": "keep product structure"},
                "future_field": "passthrough",
            }
        ],
        "prompt_plan": [
            {
                "slot_id": "hero",
                "role": "hero",
                "display_order": 1,
                "copy_blocks": {
                    "headline": "Air purifier",
                    "supporting": "",
                    "proof_lines": ["Quiet mode"],
                    "matrix_lines": [],
                },
                "copy_blocks_attribution": {"headline": {"source": "planner_enriched"}},
                "reference_image_ids": ["img-1"],
                "reference_slots": ["front"],
                "final_prompt_base": "Generate hero image",
                "must_keep": ["keep product"],
                "must_avoid": ["no people"],
                "background_rule": "light scene",
                "composition_rule": "complete subject",
                "lighting_rule": "clean lighting",
                "fidelity_rule": "strict fidelity",
                "platform_overlay": {"overlay_id": "temu", "copy_language": "en"},
                "truth_contract": {"hard_constraint_summary": "keep product structure"},
                "resolved_constraints": ["no people"],
                "rule_modules_used": ["hero_scene"],
                "debug_extra": 1,
            }
        ],
        "slot_preferences": [],
        "strategy_overrides": [],
        "resolved_copy_attribution": {"hero_scene": {"source": "explicit_input"}},
        "hash_policy_version": "preview_hash_layers_v1",
        "hash_layers": {"config_hash": "cfg", "content_hash": "content", "reference_hash": "ref", "memory_hash": "mem"},
        "input_hash": "hash-1",
        "provider_debug": "keep",
    }

    model = StrategyPreviewPayload.from_dict(raw)

    assert model.to_dict() == raw


def test_detail_strategy_preview_contract_round_trip() -> None:
    raw = {
        "use_case": "amazon_detail",
        "aspect_ratio": "21:9",
        "panel_count": 8,
        "platform_overlay": {"overlay_id": "1688", "copy_language": "zh"},
        "copy_language": "zh",
        "product_reference_manifest": [{"image_id": "p1", "slot_type": "front", "display_order": 1}],
        "style_reference_manifest": [{"image_id": "s1", "display_order": 1}],
        "detail_story_brief": {"trust_overview": "trust overview"},
        "panel_plan": [
            {
                "slot_id": "detail_slot_01",
                "panel_id": "detail_slot_01",
                "display_order": 1,
                "narrative_section": "trust_overview",
                "panel_goal": "build trust",
                "copy_focus": "core benefit",
                "panel_type": "feature_benefit",
                "visual_truth_mode": "real_product",
                "origin_note": "",
                "copy_blocks": {
                    "headline": "Fast drying",
                    "supporting": "Physical cycle",
                    "bullet_points": ["Point 1"],
                    "proof_lines": ["Proof 1"],
                    "cta_line": "",
                },
                "copy_blocks_attribution": {"headline": {"source": "rule_based"}},
                "copy_lines_attribution": [{"source": "rule_based"}],
                "product_reference_ids": ["p1"],
                "style_reference_ids": ["s1"],
                "layout_template": "feature_card",
                "rule_modules_used": ["feature_benefit"],
                "truth_contract": {"hard_constraint_summary": "keep uploaded structure"},
                "display_module_title": "Fast drying",
                "extra_trace": {"llm": False},
            }
        ],
        "detail_rule_pack": "detail_prompt_matrix_v1",
        "panel_preferences": [],
        "strategy_overrides": [],
        "resolved_copy_attribution": {"hero_scene": {"source": "explicit_input"}},
        "hash_policy_version": "preview_hash_layers_v1",
        "hash_layers": {"config_hash": "cfg", "content_hash": "content", "reference_hash": "ref", "memory_hash": "mem"},
        "input_hash": "detail-hash",
        "debug_flag": True,
    }

    model = DetailStrategyPreviewPayload.from_dict(raw)

    assert model.to_dict() == raw


def test_main_generation_snapshot_contract_round_trip() -> None:
    raw = {
        "final_prompt": "Generate main image",
        "prompt_blocks": {"goal": "main image"},
        "copy_blocks": {
            "headline": "Air purifier",
            "supporting": "",
            "proof_lines": ["Quiet mode"],
            "matrix_lines": [],
        },
        "copy_blocks_attribution": {"headline": {"source": "session_override"}},
        "sanitized_fields": [],
        "copy_safety_notes": [],
        "reference_image_ids": ["img-1"],
        "reference_slots": ["front"],
        "upstream_endpoint": "/v1/images/edits",
        "planner_instruction": "cleaner",
        "aspect_ratio": "1:1",
        "size": "1024x1024",
        "planner_source": "rule_based",
        "truth_contract": {"hard_constraint_summary": "keep product structure"},
        "risk_flags": [],
        "slot_id": "hero",
        "expression_mode": "hero_scene",
        "rule_pack_id": "default_main_gallery_v2",
        "rule_modules_used": ["hero_scene"],
        "resolved_constraints": ["no people"],
        "platform_overlay": {"overlay_id": "temu"},
        "timing": {"render_total_ms": 123},
        "download_retry_count": 0,
        "download_rescued": False,
        "sync_quality_check": {"passed": True},
    }

    model = MainGenerationSnapshot.from_dict(raw)

    assert model.to_dict() == raw


def test_main_generation_snapshot_accepts_structured_component_locks() -> None:
    raw = {
        "final_prompt": "Generate main image",
        "truth_contract": {
            "hard_constraint_summary": "keep product structure",
            "component_locks": [
                {
                    "component": "LCD显示屏",
                    "position": "机身正面中央",
                    "constraint": "preserve_exact",
                },
                {
                    "component": "前固定面板",
                    "position": "正面外壳",
                    "constraint": "preserve_exact",
                    "source": "analysis_component_registry",
                },
            ],
        },
    }

    model = MainGenerationSnapshot.from_dict(raw)

    assert model.to_dict() == raw


def test_main_generation_snapshot_keeps_legacy_component_lock_strings() -> None:
    raw = {
        "final_prompt": "Generate main image",
        "truth_contract": {
            "component_locks": ["keep LCD display", "keep front panel"],
        },
    }

    model = MainGenerationSnapshot.from_dict(raw)

    assert model.to_dict() == raw


def test_detail_generation_snapshot_contract_round_trip() -> None:
    raw = {
        "asset_family": "detail_page",
        "asset_kind": "panel",
        "use_case": "amazon_detail",
        "aspect_ratio": "21:9",
        "image_size": "1792x768",
        "size": "1792x768",
        "panel_label": "Fast drying",
        "final_prompt": "Generate detail panel",
        "prompt_blocks": {"layout": "feature card"},
        "copy_blocks": {
            "headline": "Fast drying",
            "supporting": "Physical cycle",
            "bullet_points": ["Point 1"],
            "proof_lines": ["Proof 1"],
            "cta_line": "",
        },
        "copy_blocks_attribution": {"headline": {"source": "rule_based"}},
        "sanitized_fields": [],
        "copy_safety_notes": [],
        "truth_contract": {"hard_constraint_summary": "keep uploaded structure"},
        "risk_flags": [],
        "product_reference_image_ids": ["p1"],
        "style_reference_image_ids": ["s1"],
        "effective_reference_image_ids": ["p1", "s1"],
        "upstream_endpoint": "/v1/images/edits",
        "planner_instruction": "cleaner",
        "planner_source": "rule_based",
        "slot_id": "detail_slot_01",
        "narrative_section": "trust_overview",
        "panel_goal": "build trust",
        "copy_focus": "core benefit",
        "visual_truth_mode": "real_product",
        "origin_note": "",
        "panel_type": "feature_benefit",
        "rule_modules_used": ["feature_benefit"],
        "display_order": 1,
        "layout_template": "feature_card",
        "timing": {"render_total_ms": 222},
        "submission_batch_no": 1,
        "submission_batch_size": 8,
        "submit_strategy_version": "batched_submit_v1",
        "debug_key": "keep",
    }

    model = DetailGenerationSnapshot.from_dict(raw)

    assert model.to_dict() == raw


def test_strategy_preview_contract_requires_minimum_fields() -> None:
    try:
        StrategyPreviewPayload.from_dict({"asset_plan": [{}]})
    except ValidationError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected validation error")

    assert "slot_id" in message
    assert "role" in message


def test_parameter_snapshot_contract_round_trip() -> None:
    raw = {
        "hero_scene": "living room corner",
        "core_selling_points": ["quiet purification"],
        "key_parameters": [{"key": "cadr", "label": "CADR", "value": "500", "unit": "m3/h"}],
        "product_advantages": ["strong companionship"],
        "feature_highlights": ["premium look", "clean composition"],
        "inferred_core_selling_points": ["pet friendly"],
        "inferred_key_parameters": [{"key": "noise", "label": "Noise", "value": "30", "unit": "dB"}],
        "inferred_advantages": ["easy maintenance"],
        "source_mode": "analysis_then_copy",
        "evidence_priority": "analysis_then_copy",
        "evidence_summary": [{"source": "analysis", "note": "from product image"}],
        "confidence_notes": ["from product image"],
        "debug": {"keep": True},
    }

    model = ParameterSnapshotPayload.from_dict(raw)

    assert model.to_dict() == raw
