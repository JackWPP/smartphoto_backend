from app.services.copy_resolution import COPY_META_KEY, parameter_snapshot_to_copy_attribution
from app.services.parameter_snapshot import apply_parameter_snapshot_to_copy


def test_apply_parameter_snapshot_to_copy_overwrite_syncs_legacy_fields():
    confirmed_copy = {
        "product_name": "Air purifier",
        "hero_scene": "bedroom setup",
        "usage_scenes": "old usage scene",
        "core_selling_points": ["old point"],
        "selling_points": "old point",
        "key_parameters": [{"key": "old", "label": "Old Param", "value": "1", "unit": "pc"}],
        "specs": "Old Param 1pc",
        "product_advantages": ["old advantage"],
    }
    parameter_snapshot = {
        "hero_scene": "family sofa corner",
        "core_selling_points": ["pet hair filtration", "allergy protection"],
        "key_parameters": [{"key": "cadr", "label": "CADR", "value": "500", "unit": "m3/h"}],
        "product_advantages": ["quiet companionship"],
        "feature_highlights": ["premium look", "clean composition"],
    }

    updated = apply_parameter_snapshot_to_copy(confirmed_copy, parameter_snapshot, overwrite=True)

    assert updated["hero_scene"] == "family sofa corner"
    assert updated["usage_scenes"] == "family sofa corner"
    assert updated["core_selling_points"] == ["pet hair filtration", "allergy protection"]
    assert updated["selling_points"] == "pet hair filtration\nallergy protection"
    assert updated["key_parameters"][0]["label"] == "CADR"
    assert updated["specs"] == "CADR 500m3/h"
    assert updated["style_custom"] == "premium look，clean composition"
    assert updated[COPY_META_KEY]["hero_scene"]["source"] == "parameter_primary"
    assert updated[COPY_META_KEY]["style_custom"]["source"] == "parameter_highlight_style_fallback"


def test_apply_parameter_snapshot_to_copy_non_overwrite_only_backfills_empty_legacy_fields():
    confirmed_copy = {
        "product_name": "Air purifier",
        "hero_scene": "living room purifier",
        "usage_scenes": "existing legacy scene",
        "core_selling_points": ["quiet purification"],
        "selling_points": "existing legacy points",
        "key_parameters": [{"key": "cadr", "label": "CADR", "value": "300", "unit": "m3/h"}],
        "specs": "existing legacy specs",
        "product_advantages": [],
    }
    parameter_snapshot = {
        "hero_scene": "family sofa corner",
        "core_selling_points": ["pet hair filtration"],
        "key_parameters": [{"key": "cadr", "label": "CADR", "value": "500", "unit": "m3/h"}],
        "product_advantages": ["quiet companionship"],
    }

    updated = apply_parameter_snapshot_to_copy(confirmed_copy, parameter_snapshot, overwrite=False)

    assert updated["hero_scene"] == "living room purifier"
    assert updated["usage_scenes"] == "existing legacy scene"
    assert updated["core_selling_points"] == ["quiet purification"]
    assert updated["selling_points"] == "existing legacy points"
    assert updated["specs"] == "existing legacy specs"
    assert updated["product_advantages"] == ["quiet companionship"]
    assert updated[COPY_META_KEY]["product_advantages"][0]["source"] == "parameter_primary"


def test_parameter_snapshot_to_copy_attribution_marks_primary_and_inferred_sources():
    attribution = parameter_snapshot_to_copy_attribution(
        {
            "hero_scene": "desk setup",
            "core_selling_points": ["fast cooling"],
            "inferred_core_selling_points": ["energy saving"],
            "key_parameters": [{"key": "power", "label": "Power", "value": "20", "unit": "W"}],
            "inferred_key_parameters": [{"key": "noise", "label": "Noise", "value": "30", "unit": "dB"}],
            "product_advantages": ["compact body"],
            "inferred_advantages": ["easy storage"],
            "feature_highlights": ["minimal style"],
        }
    )

    assert attribution["hero_scene"]["source"] == "parameter_primary"
    assert [item["source"] for item in attribution["core_selling_points"]] == [
        "parameter_primary",
        "parameter_inferred",
    ]
    assert [item["source"] for item in attribution["key_parameters"]] == [
        "parameter_primary",
        "parameter_inferred",
    ]
    assert [item["source"] for item in attribution["product_advantages"]] == [
        "parameter_primary",
        "parameter_inferred",
    ]
    assert attribution["style_custom"]["source"] == "parameter_highlight_style_fallback"
