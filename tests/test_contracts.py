from __future__ import annotations

from app.contracts.copy import DetailCopyBlocks, MainCopyBlocks
from app.contracts.detail_strategy import DetailStrategyPreviewPayload
from app.contracts.generation import DetailGenerationSnapshot, MainGenerationSnapshot
from app.contracts.parameter import ParameterSnapshotPayload
from app.contracts.strategy import StrategyPreviewPayload


def test_main_copy_blocks_round_trip_preserves_extra_fields() -> None:
    raw = {
        "headline": "主标题",
        "supporting": "副文案",
        "proof_lines": ["证明1"],
        "matrix_lines": ["矩阵1"],
        "extra_debug": {"source": "fixture"},
    }

    model = MainCopyBlocks.from_dict(raw)

    assert model.to_dict() == raw


def test_detail_copy_blocks_round_trip_preserves_extra_fields() -> None:
    raw = {
        "headline": "标题",
        "supporting": "说明",
        "bullet_points": ["点1"],
        "proof_lines": ["证据"],
        "cta_line": "立即查看",
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
                "composition_hint": "主体居中",
                "expression_mode": "hero_scene",
                "copy_blocks": {
                    "headline": "空气净化器",
                    "supporting": "",
                    "proof_lines": ["低噪音"],
                    "matrix_lines": [],
                },
                "platform_rule_pack": "default_main_gallery_v2",
                "rule_modules_used": ["hero_scene"],
                "truth_contract": {"hard_constraint_summary": "保持主体结构"},
                "future_field": "passthrough",
            }
        ],
        "prompt_plan": [
            {
                "slot_id": "hero",
                "role": "hero",
                "display_order": 1,
                "copy_blocks": {
                    "headline": "空气净化器",
                    "supporting": "",
                    "proof_lines": ["低噪音"],
                    "matrix_lines": [],
                },
                "reference_image_ids": ["img-1"],
                "reference_slots": ["front"],
                "final_prompt_base": "生成首图",
                "must_keep": ["保持主体"],
                "must_avoid": ["不要人物"],
                "background_rule": "轻场景",
                "composition_rule": "主体完整",
                "lighting_rule": "光线干净",
                "fidelity_rule": "严格保真",
                "platform_overlay": {"overlay_id": "temu", "copy_language": "en"},
                "truth_contract": {"hard_constraint_summary": "保持主体结构"},
                "resolved_constraints": ["不要人物"],
                "rule_modules_used": ["hero_scene"],
                "debug_extra": 1,
            }
        ],
        "slot_preferences": [],
        "strategy_overrides": [],
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
        "detail_story_brief": {"trust_overview": "可信赖"},
        "panel_plan": [
            {
                "slot_id": "detail_slot_01",
                "panel_id": "detail_slot_01",
                "display_order": 1,
                "narrative_section": "trust_overview",
                "panel_goal": "建立信任",
                "copy_focus": "核心卖点",
                "panel_type": "feature_benefit",
                "visual_truth_mode": "real_product",
                "origin_note": "",
                "copy_blocks": {
                    "headline": "高效除湿",
                    "supporting": "物理循环",
                    "bullet_points": ["卖点1"],
                    "proof_lines": ["参数1"],
                    "cta_line": "",
                },
                "product_reference_ids": ["p1"],
                "style_reference_ids": ["s1"],
                "layout_template": "feature_card",
                "rule_modules_used": ["feature_benefit"],
                "truth_contract": {"hard_constraint_summary": "保持上传商品结构"},
                "display_module_title": "高效除湿",
                "extra_trace": {"llm": False},
            }
        ],
        "detail_rule_pack": "detail_prompt_matrix_v1",
        "panel_preferences": [],
        "strategy_overrides": [],
        "input_hash": "detail-hash",
        "debug_flag": True,
    }

    model = DetailStrategyPreviewPayload.from_dict(raw)

    assert model.to_dict() == raw


def test_main_generation_snapshot_contract_round_trip() -> None:
    raw = {
        "final_prompt": "生成主图",
        "prompt_blocks": {"goal": "主图"},
        "copy_blocks": {
            "headline": "空气净化器",
            "supporting": "",
            "proof_lines": ["低噪音"],
            "matrix_lines": [],
        },
        "sanitized_fields": [],
        "copy_safety_notes": [],
        "reference_image_ids": ["img-1"],
        "reference_slots": ["front"],
        "upstream_endpoint": "/v1/images/edits",
        "planner_instruction": "更干净",
        "aspect_ratio": "1:1",
        "size": "1024x1024",
        "planner_source": "rule_based",
        "truth_contract": {"hard_constraint_summary": "保持主体结构"},
        "risk_flags": [],
        "slot_id": "hero",
        "expression_mode": "hero_scene",
        "rule_pack_id": "default_main_gallery_v2",
        "rule_modules_used": ["hero_scene"],
        "resolved_constraints": ["不要人物"],
        "platform_overlay": {"overlay_id": "temu"},
        "timing": {"render_total_ms": 123},
        "download_retry_count": 0,
        "download_rescued": False,
        "sync_quality_check": {"passed": True},
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
        "panel_label": "高效除湿",
        "final_prompt": "生成详情页",
        "prompt_blocks": {"layout": "feature card"},
        "copy_blocks": {
            "headline": "高效除湿",
            "supporting": "物理循环",
            "bullet_points": ["卖点1"],
            "proof_lines": ["参数1"],
            "cta_line": "",
        },
        "sanitized_fields": [],
        "copy_safety_notes": [],
        "truth_contract": {"hard_constraint_summary": "保持上传商品结构"},
        "risk_flags": [],
        "product_reference_image_ids": ["p1"],
        "style_reference_image_ids": ["s1"],
        "effective_reference_image_ids": ["p1", "s1"],
        "upstream_endpoint": "/v1/images/edits",
        "planner_instruction": "更干净",
        "planner_source": "rule_based",
        "slot_id": "detail_slot_01",
        "narrative_section": "trust_overview",
        "panel_goal": "建立信任",
        "copy_focus": "核心卖点",
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
    except Exception as exc:
        message = str(exc)
    else:
        raise AssertionError("expected validation error")

    assert "slot_id" in message
    assert "role" in message


def test_parameter_snapshot_contract_round_trip() -> None:
    raw = {
        "hero_scene": "客厅角落",
        "core_selling_points": ["低噪音"],
        "key_parameters": [{"key": "cadr", "label": "CADR", "value": "500", "unit": "m3/h"}],
        "product_advantages": ["陪伴感强"],
        "feature_highlights": ["高级感", "干净"],
        "inferred_core_selling_points": ["宠物友好"],
        "inferred_key_parameters": [{"key": "noise", "label": "噪音", "value": "30", "unit": "dB"}],
        "inferred_advantages": ["易维护"],
        "source_mode": "extract",
        "confidence_notes": ["来自商品图"],
        "debug": {"keep": True},
    }

    model = ParameterSnapshotPayload.from_dict(raw)

    assert model.to_dict() == raw
