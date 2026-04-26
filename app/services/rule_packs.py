from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from app.db import session as db_session
from app.models.rule_pack import RulePackModel
from app.models.rule_pack_version import RulePackVersionModel

DEFAULT_MAIN_RULE_PACK_ID = "default_main_gallery_v2"
ALIBABA_MAIN_RULE_PACK_ID = "alibaba_core_5_slot"
DETAIL_RULE_PACK_ID = "ecommerce_detail_v2"
ALIBABA_DETAIL_RULE_PACK_ID = "alibaba_detail_v1"

_SHARED_HARNESS_BLOCKS: dict[str, Any] = {
    "fidelity_config": {
        "default_fidelity_tier": "high",
        "force_fidelity_validation": True,
        "force_text_language_validation": True,
        "component_lock_enabled": True,
    },
    "style_templates": {
        "default_lighting": "主体采用柔和环绕光与一侧主光源的三点布光法，保持阴影面积不超过主体 15%，高光区域需突出材质质感但不过曝。",
        "default_background": "背景采用柔和渐变单色调，模拟专业棚拍无缝背景纸效果，不出现明显分割线、拼接痕迹或复杂场景。",
        "default_space": "主体占画面 50-65% 面积，周围预留均匀留白空间。",
    },
    "selling_point_policy": {
        "exclusive_allocation": True,
        "max_points_per_slot": 2,
    },
    "validation_policy": {
        "fidelity_check": "always",
        "text_language_check": "always",
        "max_retry_on_fail": 1,
    },
}

BUILTIN_RULE_PACKS: list[dict[str, Any]] = [
    {
        "name": "默认主图库规则",
        "asset_family": "main_gallery",
        "platform_id": None,
        "rule_pack_key": DEFAULT_MAIN_RULE_PACK_ID,
        "config_snapshot": {
            "slot_plan": [
                {"slot_id": "hero", "slot_label": "主图", "slot_family": "hero", "compat_role": "hero", "role_label": "主图", "goal": "突出商品主体与第一卖点，适合作为电商主图首屏", "background_mode": "clean_studio", "text_policy": "no_text", "composition_hint": "单商品主体清晰，居中或偏中心构图，画面简洁有高级感", "copy_policy": "minimal", "layout_policy": "single_subject", "proof_policy": "soft", "requires_white_bg_validation": False, "reference_role_hint": "hero", "candidate_expression_modes": ["clean_conversion_kv", "floating_focus", "lifestyle_kv"]},
                {"slot_id": "white_bg", "slot_label": "白底图", "slot_family": "white_bg", "compat_role": "white_bg", "role_label": "白底图", "goal": "输出标准电商白底图，方便平台审核与商品展示", "background_mode": "pure_white", "text_policy": "no_text", "composition_hint": "单产品完整展示，纯白无缝背景，轮廓干净无遮挡", "copy_policy": "none", "layout_policy": "single_subject", "proof_policy": "none", "requires_white_bg_validation": True, "reference_role_hint": "white_bg", "candidate_expression_modes": ["pure_white_standard", "pure_white_shadow"]},
                {"slot_id": "selling_point", "slot_label": "卖点图", "slot_family": "selling_point", "compat_role": "selling_point", "role_label": "卖点图", "goal": "聚焦一个核心卖点，用画面直接表达功能或优势", "background_mode": "simple_feature_bg", "text_policy": "no_text", "composition_hint": "围绕单一卖点做近景或功能化构图，不做拼贴海报", "copy_policy": "headline_optional", "layout_policy": "feature_focus", "proof_policy": "medium", "requires_white_bg_validation": False, "reference_role_hint": "selling_point", "candidate_expression_modes": ["single_feature_focus", "benefit_proof_card", "feature_matrix"]},
                {"slot_id": "scene", "slot_label": "场景图", "slot_family": "scene", "compat_role": "scene", "role_label": "场景图", "goal": "把商品放进真实使用情境，体现人群、空间或使用方式", "background_mode": "real_scene", "text_policy": "no_text", "composition_hint": "真实生活化场景，中景构图，商品与环境关系清晰", "copy_policy": "headline_optional", "layout_policy": "immersive_scene", "proof_policy": "soft", "requires_white_bg_validation": False, "reference_role_hint": "scene", "candidate_expression_modes": ["immersive_scene", "benefit_scene", "comparison_scene"]},
                {"slot_id": "detail", "slot_label": "细节图", "slot_family": "detail", "compat_role": "detail", "role_label": "细节图", "goal": "突出材质、结构、做工或局部细节", "background_mode": "soft_focus_bg", "text_policy": "no_text", "composition_hint": "局部特写或微距构图，强调工艺、纹理与质感", "copy_policy": "headline_optional", "layout_policy": "macro_closeup", "proof_policy": "medium", "requires_white_bg_validation": False, "reference_role_hint": "detail", "candidate_expression_modes": ["macro_texture_closeup", "structure_cutaway", "material_process_focus"]},
            ],
            **copy.deepcopy(_SHARED_HARNESS_BLOCKS),
            "negative_prompt_library": {
                "universal": [
                    "不要重建产品外观",
                    "不要改变产品颜色",
                    "不要添加参考图中不存在的部件",
                ],
                "per_slot": {
                    "white_bg": ["不要任何道具/人物/场景"],
                    "hero": ["不要拼贴海报风格"],
                },
            },
        },
    },
    {
        "name": "阿里主图库规则",
        "asset_family": "main_gallery",
        "platform_id": "1688",
        "rule_pack_key": ALIBABA_MAIN_RULE_PACK_ID,
        "config_snapshot": {
            "slot_plan": [
                {"slot_id": "primary_kv", "slot_label": "首图KV", "slot_family": "primary_kv", "compat_role": "primary_kv", "role_label": "首图KV", "goal": "首图需要一眼说明产品是什么、解决什么问题，并承担点击入口", "background_mode": "clean_studio", "text_policy": "short_copy_required", "composition_hint": "产品主体约占画面一半，预留大标题和短副文案空间", "copy_policy": "headline_plus_supporting", "layout_policy": "headline_first", "proof_policy": "soft", "requires_white_bg_validation": False, "reference_role_hint": "hero", "candidate_expression_modes": ["click_through_headline", "benefit_kv", "problem_solution_kv"]},
                {"slot_id": "reason_why", "slot_label": "理由图", "slot_family": "reason_why", "compat_role": "reason_why", "role_label": "理由图", "goal": "承接首图点击后用户的好奇心，说明为什么有效或具体有什么能力", "background_mode": "feature_dark", "text_policy": "short_copy_required", "composition_hint": "优先做理由卡、机制卡、能力摘要，不做纯白底展示", "copy_policy": "headline_plus_supporting", "layout_policy": "reason_card", "proof_policy": "medium", "requires_white_bg_validation": False, "reference_role_hint": "selling_point", "candidate_expression_modes": ["reason_card", "mechanism_card", "what_you_get"]},
                {"slot_id": "proof_authority", "slot_label": "佐证图", "slot_family": "proof_authority", "compat_role": "proof_authority", "role_label": "佐证图", "goal": "展现最强卖点，并用认证、参数、证书或实验做佐证", "background_mode": "proof_stage", "text_policy": "short_copy_required", "composition_hint": "突出证明性元素，文案短而硬，版式可以更信息化", "copy_policy": "headline_plus_proof", "layout_policy": "proof_card", "proof_policy": "hard", "requires_white_bg_validation": False, "reference_role_hint": "selling_point", "candidate_expression_modes": ["certificate_proof", "lab_proof", "spec_proof"]},
                {"slot_id": "benefit_scene_or_compare", "slot_label": "利益场景/对比图", "slot_family": "benefit_scene_or_compare", "compat_role": "benefit_scene_or_compare", "role_label": "利益场景/对比图", "goal": "强调消费者利益点，可走真实场景代入或对比优势", "background_mode": "real_scene", "text_policy": "short_copy_required", "composition_hint": "场景或对比服务于利益点，不允许空洞卖点和纯抽象氛围", "copy_policy": "benefit_copy", "layout_policy": "scene_or_compare", "proof_policy": "medium", "requires_white_bg_validation": False, "reference_role_hint": "scene", "candidate_expression_modes": ["real_scene_benefit", "compare_superiority", "coverage_scene"]},
                {"slot_id": "closing_selling_point", "slot_label": "尾屏卖点图", "slot_family": "closing_selling_point", "compat_role": "closing_selling_point", "role_label": "尾屏卖点图", "goal": "承接剩余高优卖点，做卖点矩阵、参数亮点或尾屏总结", "background_mode": "clean_feature_bg", "text_policy": "short_copy_required", "composition_hint": "可做卖点矩阵、参数亮点收束或尾屏总结，完成转化闭环", "copy_policy": "matrix_copy", "layout_policy": "matrix_or_summary", "proof_policy": "medium", "requires_white_bg_validation": False, "reference_role_hint": "detail", "candidate_expression_modes": ["selling_point_matrix", "parameter_highlight", "tail_summary"]},
            ],
            **copy.deepcopy(_SHARED_HARNESS_BLOCKS),
            "negative_prompt_library": {
                "universal": [
                    "不要重建产品外观",
                    "不要改变产品颜色",
                    "不要添加参考图中不存在的部件",
                ],
                "per_slot": {
                    "white_bg": ["不要任何道具/人物/场景"],
                    "primary_kv": ["不要拼贴海报风格"],
                },
            },
        },
    },
    {
        "name": "默认详情页规则",
        "asset_family": "detail_page",
        "platform_id": None,
        "rule_pack_key": DETAIL_RULE_PACK_ID,
        "config_snapshot": {
            "panel_type_library": {
                "brand_authority": {"label": "品牌背书", "layout_template": "authority_banner", "copy_policy": "headline_plus_supporting"},
                "sales_proof": {"label": "销售实力", "layout_template": "social_proof", "copy_policy": "headline_plus_supporting"},
                "promo_gift": {"label": "活动礼赠", "layout_template": "promo_offer", "copy_policy": "headline_plus_supporting"},
                "product_selector": {"label": "产品选购", "layout_template": "selector_grid", "copy_policy": "list_compare"},
                "kv_problem_solution": {"label": "首屏KV", "layout_template": "hero_kv", "copy_policy": "headline_plus_supporting"},
                "icon_island": {"label": "Icon岛", "layout_template": "icon_grid", "copy_policy": "icon_points"},
                "feature_proof": {"label": "卖点佐证", "layout_template": "proof_card", "copy_policy": "headline_plus_supporting"},
                "feature_scene": {"label": "场景卖点", "layout_template": "immersive_scene", "copy_policy": "headline_plus_supporting"},
                "feature_benefit": {"label": "利益点详解", "layout_template": "benefit_story", "copy_policy": "headline_plus_supporting"},
                "feature_compare": {"label": "对比优势", "layout_template": "compare_board", "copy_policy": "list_compare"},
                "feature_exploded_view": {"label": "爆炸结构", "layout_template": "exploded_view", "copy_policy": "headline_plus_supporting"},
                "feature_process_material": {"label": "工艺材质", "layout_template": "material_process", "copy_policy": "headline_plus_supporting"},
                "detail_closeup": {"label": "细节特写", "layout_template": "macro_closeup", "copy_policy": "headline_plus_supporting"},
                "parameter_explainer": {"label": "参数解释", "layout_template": "parameter_board", "copy_policy": "list_compare"},
            },
            "slot_plan": [
                {"slot_id": "detail_slot_01", "panel_id": "panel_01_cover", "panel_label": "首屏槽位", "default_panel_type": "kv_problem_solution", "candidate_panel_types": ["brand_authority", "sales_proof", "promo_gift", "product_selector", "kv_problem_solution"]},
                {"slot_id": "detail_slot_02", "panel_id": "panel_02_overview", "panel_label": "概览槽位", "default_panel_type": "icon_island", "candidate_panel_types": ["icon_island", "product_selector", "brand_authority", "sales_proof"]},
                {"slot_id": "detail_slot_03", "panel_id": "panel_03_feature_a", "panel_label": "卖点槽位A", "default_panel_type": "feature_proof", "candidate_panel_types": ["feature_proof", "feature_benefit", "feature_compare", "feature_exploded_view"]},
                {"slot_id": "detail_slot_04", "panel_id": "panel_04_feature_b", "panel_label": "卖点槽位B", "default_panel_type": "feature_scene", "candidate_panel_types": ["feature_scene", "feature_benefit", "feature_compare", "feature_process_material"]},
                {"slot_id": "detail_slot_05", "panel_id": "panel_05_scene", "panel_label": "卖点槽位C", "default_panel_type": "feature_benefit", "candidate_panel_types": ["feature_benefit", "feature_scene", "feature_proof", "feature_compare"]},
                {"slot_id": "detail_slot_06", "panel_id": "panel_06_detail", "panel_label": "卖点槽位D", "default_panel_type": "feature_compare", "candidate_panel_types": ["feature_compare", "feature_exploded_view", "feature_process_material", "feature_scene"]},
                {"slot_id": "detail_slot_07", "panel_id": "panel_07_specs", "panel_label": "细节/参数槽位", "default_panel_type": "detail_closeup", "candidate_panel_types": ["detail_closeup", "feature_process_material", "feature_exploded_view", "parameter_explainer"]},
                {"slot_id": "detail_slot_08", "panel_id": "panel_08_closing", "panel_label": "收束槽位", "default_panel_type": "parameter_explainer", "candidate_panel_types": ["parameter_explainer", "promo_gift", "sales_proof", "brand_authority", "kv_problem_solution"]},
            ],
        },
    },
    # ── 1688 / 淘宝专属详情页规则包 ──────────────────────────────────────────────
    {
        "name": "1688详情页规则",
        "asset_family": "detail_page",
        "platform_id": "1688",
        "rule_pack_key": ALIBABA_DETAIL_RULE_PACK_ID,
        "config_snapshot": {
            # 平台约束：亮底、主体占比、禁止暗黑风格
            "platform_constraints": {
                "background_style": "bright_clean",          # 亮底/白底/浅灰底
                "subject_ratio_min": 0.55,                   # 主体占画面比例 ≥ 55%
                "forbidden_styles": ["dark_moody", "cyberpunk", "kv_poster", "magazine_spread"],
                "copy_max_chars_headline": 12,               # 标题最多 12 汉字
                "copy_max_chars_supporting": 20,             # 副文案最多 20 汉字
                "thumbnail_readable": True,                  # 缩略图可读
                "module_style": "card_modular",              # 模块化卡片风格
            },
            # 叙事模板：1688 移动端货架叙事结构
            "detail_narrative_template": {
                "structure": [
                    "trust_overview",   # 首屏：品类定位 + 核心利益点
                    "mechanism",        # 机制/原理：为什么有效
                    "feature_a",        # 核心卖点 A 深度展开
                    "feature_b",        # 核心卖点 B 深度展开
                    "usage_scene",      # 使用场景可视化
                    "parameter_proof", # 参数/认证/实验佐证
                    "differentiator",  # 差异化亮点
                    "closing_cta",     # 尾屏总结 + 行动号召
                ],
                "min_panels": 5,
                "max_panels": 8,
                "trust_module_required": True,
                "evidence_module_required": True,
                "panel_descriptions": {
                    "trust_overview": "首屏货架信任入场：品牌/品类定位 + 核心利益点（亮底，短标题，主体突出）",
                    "mechanism": "机制/原理卡：理由卡，解释为什么有效，可用图解或数据",
                    "feature_a": "核心卖点 A 深度展开：证据卡，用参数/认证/对比佐证",
                    "feature_b": "核心卖点 B 深度展开：场景利益卡，真实场景代入",
                    "usage_scene": "使用场景可视化：生活化场景，体现人群和使用方式",
                    "parameter_proof": "参数板/认证/实验数据：结构化参数展示",
                    "differentiator": "差异化亮点：对比竞品或展示独有功能",
                    "closing_cta": "尾屏总结收束：精简核心卖点矩阵 + 行动号召",
                },
            },
            # 面板类型库：1688 货架语义（替换 Amazon 语义词汇）
            "panel_type_library": {
                # 1688 专属货架类型
                "first_screen_shelf": {"label": "首屏货架图", "layout_template": "shelf_hero", "copy_policy": "headline_plus_supporting"},
                "reason_why_card": {"label": "理由卡", "layout_template": "reason_card", "copy_policy": "headline_plus_supporting"},
                "evidence_card": {"label": "证据卡", "layout_template": "proof_card", "copy_policy": "headline_plus_supporting"},
                "scene_benefit_card": {"label": "场景利益卡", "layout_template": "immersive_scene", "copy_policy": "headline_plus_supporting"},
                "closing_summary": {"label": "尾屏总结", "layout_template": "summary_matrix", "copy_policy": "matrix_copy"},
                # 通用类型（保留）
                "parameter_board": {"label": "参数板", "layout_template": "parameter_board", "copy_policy": "list_compare"},
                "feature_proof": {"label": "卖点佐证", "layout_template": "proof_card", "copy_policy": "headline_plus_supporting"},
                "feature_scene": {"label": "场景卖点", "layout_template": "immersive_scene", "copy_policy": "headline_plus_supporting"},
                "feature_compare": {"label": "对比优势", "layout_template": "compare_board", "copy_policy": "list_compare"},
                "feature_exploded_view": {"label": "爆炸结构", "layout_template": "exploded_view", "copy_policy": "headline_plus_supporting"},
                "detail_closeup": {"label": "细节特写", "layout_template": "macro_closeup", "copy_policy": "headline_plus_supporting"},
                "feature_benefit": {"label": "利益点详解", "layout_template": "benefit_story", "copy_policy": "headline_plus_supporting"},
                "feature_process_material": {"label": "工艺材质", "layout_template": "material_process", "copy_policy": "headline_plus_supporting"},
                "icon_island": {"label": "Icon岛", "layout_template": "icon_grid", "copy_policy": "icon_points"},
                "product_selector": {"label": "产品选购", "layout_template": "selector_grid", "copy_policy": "list_compare"},
                "promo_gift": {"label": "活动礼赠", "layout_template": "promo_offer", "copy_policy": "headline_plus_supporting"},
                "sales_proof": {"label": "销售实力", "layout_template": "social_proof", "copy_policy": "headline_plus_supporting"},
            },
            # 槽位规划：首屏→理由→证据→卖点×2→场景→参数→尾屏
            "slot_plan": [
                {"slot_id": "detail_slot_01", "panel_id": "panel_01_cover", "panel_label": "首屏货架", "default_panel_type": "first_screen_shelf", "candidate_panel_types": ["first_screen_shelf", "sales_proof", "promo_gift", "product_selector"]},
                {"slot_id": "detail_slot_02", "panel_id": "panel_02_reason", "panel_label": "理由/机制", "default_panel_type": "reason_why_card", "candidate_panel_types": ["reason_why_card", "icon_island", "product_selector", "feature_benefit"]},
                {"slot_id": "detail_slot_03", "panel_id": "panel_03_feature_a", "panel_label": "卖点A佐证", "default_panel_type": "evidence_card", "candidate_panel_types": ["evidence_card", "feature_proof", "feature_compare", "feature_exploded_view"]},
                {"slot_id": "detail_slot_04", "panel_id": "panel_04_feature_b", "panel_label": "卖点B场景", "default_panel_type": "scene_benefit_card", "candidate_panel_types": ["scene_benefit_card", "feature_scene", "feature_benefit", "feature_process_material"]},
                {"slot_id": "detail_slot_05", "panel_id": "panel_05_scene", "panel_label": "使用场景", "default_panel_type": "feature_benefit", "candidate_panel_types": ["feature_benefit", "feature_scene", "feature_proof", "feature_compare"]},
                {"slot_id": "detail_slot_06", "panel_id": "panel_06_diff", "panel_label": "差异化", "default_panel_type": "feature_compare", "candidate_panel_types": ["feature_compare", "feature_exploded_view", "feature_process_material", "feature_scene"]},
                {"slot_id": "detail_slot_07", "panel_id": "panel_07_params", "panel_label": "参数/细节", "default_panel_type": "parameter_board", "candidate_panel_types": ["parameter_board", "detail_closeup", "feature_process_material", "feature_exploded_view"]},
                {"slot_id": "detail_slot_08", "panel_id": "panel_08_closing", "panel_label": "尾屏总结", "default_panel_type": "closing_summary", "candidate_panel_types": ["closing_summary", "promo_gift", "sales_proof", "parameter_board"]},
            ],
        },
    },
]


def ensure_system_rule_packs(db: Session) -> None:
    """按 rule_pack_key 做 upsert，确保新增 builtin 时不会因已有记录而跳过。"""
    existing_keys: set[str] = {
        row.rule_pack_key
        for row in db.query(RulePackModel.rule_pack_key).filter(RulePackModel.is_system.is_(True)).all()
    }
    for item in BUILTIN_RULE_PACKS:
        if item["rule_pack_key"] in existing_keys:
            continue
        rule_pack = RulePackModel(
            name=item["name"],
            asset_family=item["asset_family"],
            platform_id=item["platform_id"],
            rule_pack_key=item["rule_pack_key"],
            is_system=True,
            is_active=True,
            current_version_no=1,
            created_by=None,
        )
        db.add(rule_pack)
        db.flush()
        db.add(
            RulePackVersionModel(
                rule_pack_id=rule_pack.id,
                version_no=1,
                asset_family=item["asset_family"],
                platform_id=item["platform_id"],
                rule_pack_key=item["rule_pack_key"],
                config_snapshot=copy.deepcopy(item["config_snapshot"]),
                is_published=True,
                published_by=None,
            )
        )
    db.flush()


def get_published_rule_pack_config(
    db: Session,
    *,
    asset_family: str,
    rule_pack_key: str | None = None,
    platform_id: str | None = None,
) -> tuple[RulePackModel | None, RulePackVersionModel | None, dict[str, Any] | None]:
    ensure_system_rule_packs(db)
    query = (
        db.query(RulePackModel, RulePackVersionModel)
        .join(RulePackVersionModel, RulePackVersionModel.rule_pack_id == RulePackModel.id)
        .filter(
            RulePackModel.asset_family == asset_family,
            RulePackModel.is_active.is_(True),
            RulePackVersionModel.is_published.is_(True),
        )
    )
    if rule_pack_key:
        query = query.filter(RulePackModel.rule_pack_key == rule_pack_key)
    if platform_id:
        query = query.filter((RulePackModel.platform_id == platform_id) | (RulePackModel.platform_id.is_(None)))
    row = (
        query.order_by(RulePackModel.platform_id.desc(), RulePackVersionModel.version_no.desc())
        .first()
    )
    if not row:
        return None, None, None
    rule_pack, version = row
    return rule_pack, version, copy.deepcopy(version.config_snapshot or {})


def load_published_rule_pack_config(
    *,
    asset_family: str,
    rule_pack_key: str | None = None,
    platform_id: str | None = None,
    db: Session | None = None,
) -> tuple[RulePackModel | None, RulePackVersionModel | None, dict[str, Any] | None]:
    if db is not None:
        return get_published_rule_pack_config(
            db,
            asset_family=asset_family,
            rule_pack_key=rule_pack_key,
            platform_id=platform_id,
        )
    with db_session.SessionLocal() as owned_db:
        return get_published_rule_pack_config(
            owned_db,
            asset_family=asset_family,
            rule_pack_key=rule_pack_key,
            platform_id=platform_id,
        )


_DEFAULT_HARNESS_CONFIG: dict[str, Any] = {
    "fidelity_config": {
        "default_fidelity_tier": "high",
        "force_fidelity_validation": True,
        "force_text_language_validation": True,
        "component_lock_enabled": True,
    },
    "negative_prompt_library": {
        "universal": [],
        "per_slot": {},
    },
    "style_templates": {},
    "expression_library": {},
    "selling_point_policy": {
        "exclusive_allocation": True,
        "max_points_per_slot": 2,
    },
    "validation_policy": {
        "fidelity_check": "always",
        "text_language_check": "always",
        "max_retry_on_fail": 1,
    },
    "detail_narrative_template": {
        "structure": [
            "trust_overview",
            "mechanism",
            "feature_a",
            "feature_b",
            "usage_scene",
            "parameter_proof",
            "closing_cta",
        ],
        "min_panels": 5,
        "max_panels": 8,
        "trust_module_required": True,
        "evidence_module_required": True,
        "panel_descriptions": {
            "trust_overview": "首屏信任入场：品牌/品类定位 + 核心利益点",
            "mechanism": "机制/原理解释：为什么有效",
            "feature_a": "核心卖点 A 深度展开",
            "feature_b": "核心卖点 B 深度展开",
            "usage_scene": "使用场景可视化",
            "parameter_proof": "参数/认证/实验数据佐证",
            "closing_cta": "尾屏总结收束 + 行动号召",
        },
    },
}


def get_harness_config(
    *,
    platform_id: str,
    asset_family: str = "main_gallery",
    db: Session | None = None,
) -> dict[str, Any]:
    """Load admin-configurable harness settings from Rule Pack config_snapshot.

    Falls back to sensible defaults for any missing keys.
    """
    from app.services.main_gallery_rules import get_main_rule_pack_id

    rule_pack_key = get_main_rule_pack_id(platform_id)
    _, _, config = load_published_rule_pack_config(
        asset_family=asset_family,
        rule_pack_key=rule_pack_key,
        platform_id=platform_id,
        db=db,
    )
    config = config or {}
    result: dict[str, Any] = {}
    for key, default_value in _DEFAULT_HARNESS_CONFIG.items():
        stored = config.get(key)
        if isinstance(stored, dict) and isinstance(default_value, dict):
            result[key] = {**default_value, **stored}
        else:
            result[key] = stored if stored is not None else copy.deepcopy(default_value)
    return result

