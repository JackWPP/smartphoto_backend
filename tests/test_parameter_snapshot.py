from app.services.parameter_snapshot import apply_parameter_snapshot_to_copy


def test_apply_parameter_snapshot_to_copy_overwrite_syncs_legacy_fields():
    confirmed_copy = {
        "product_name": "空气净化器",
        "hero_scene": "卧室床头",
        "usage_scenes": "旧卧室场景",
        "core_selling_points": ["旧卖点"],
        "selling_points": "旧卖点",
        "key_parameters": [{"key": "old", "label": "旧参数", "value": "1", "unit": "项"}],
        "specs": "旧参数 1项",
        "product_advantages": ["旧优势"],
    }
    parameter_snapshot = {
        "hero_scene": "宠物家庭沙发旁净化",
        "core_selling_points": ["宠物浮毛过滤", "过敏防护"],
        "key_parameters": [{"key": "cadr", "label": "CADR", "value": "500", "unit": "m3/h"}],
        "product_advantages": ["低噪陪伴"],
    }

    updated = apply_parameter_snapshot_to_copy(confirmed_copy, parameter_snapshot, overwrite=True)

    assert updated["hero_scene"] == "宠物家庭沙发旁净化"
    assert updated["usage_scenes"] == "宠物家庭沙发旁净化"
    assert updated["core_selling_points"] == ["宠物浮毛过滤", "过敏防护"]
    assert updated["selling_points"] == "宠物浮毛过滤\n过敏防护"
    assert updated["key_parameters"][0]["label"] == "CADR"
    assert updated["specs"] == "CADR 500m3/h"


def test_apply_parameter_snapshot_to_copy_non_overwrite_only_backfills_empty_legacy_fields():
    confirmed_copy = {
        "product_name": "空气净化器",
        "hero_scene": "客厅角落净化",
        "usage_scenes": "已有 legacy 场景",
        "core_selling_points": ["静音净化"],
        "selling_points": "已有 legacy 卖点",
        "key_parameters": [{"key": "cadr", "label": "CADR", "value": "300", "unit": "m3/h"}],
        "specs": "已有 legacy 参数",
        "product_advantages": [],
    }
    parameter_snapshot = {
        "hero_scene": "宠物家庭沙发旁净化",
        "core_selling_points": ["宠物浮毛过滤"],
        "key_parameters": [{"key": "cadr", "label": "CADR", "value": "500", "unit": "m3/h"}],
        "product_advantages": ["低噪陪伴"],
    }

    updated = apply_parameter_snapshot_to_copy(confirmed_copy, parameter_snapshot, overwrite=False)

    assert updated["hero_scene"] == "客厅角落净化"
    assert updated["usage_scenes"] == "已有 legacy 场景"
    assert updated["core_selling_points"] == ["静音净化"]
    assert updated["selling_points"] == "已有 legacy 卖点"
    assert updated["specs"] == "已有 legacy 参数"
