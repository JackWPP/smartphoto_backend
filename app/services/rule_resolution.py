from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.services.detail_panel_library import DETAIL_PANEL_SLOT_PRESETS, DETAIL_PANEL_TYPE_LIBRARY
from app.services.main_gallery_rules import (
    DEFAULT_MAIN_RULE_PACK_ID,
    EXPRESSION_LIBRARY,
    MAIN_GALLERY_SLOT_PRESETS,
    PLATFORM_GRAMMAR_FAMILIES,
    PLATFORM_OVERLAYS,
    build_copy_blocks,
    ensure_system_platform_configs,
    get_main_rule_pack_id,
    recommend_expression_mode,
)
from app.services.platforms import get_platform_or_none
from app.services.rule_packs import DETAIL_RULE_PACK_ID, get_harness_config, load_published_rule_pack_config
from app.services.visible_copy_policy import (
    simplified_chinese_visible_copy_constraints,
    visible_copy_language_for_platform,
)


@dataclass(frozen=True)
class MainGalleryRuleContext:
    platform_id: str
    overlay: dict[str, Any]
    grammar_family: dict[str, Any] | None
    rule_pack_id: str
    rule_pack: Any | None
    rule_pack_version: Any | None
    rule_pack_config: dict[str, Any]
    harness_config: dict[str, Any]


@dataclass(frozen=True)
class ResolvedMainSlotRule:
    slot_blueprint: dict[str, Any]
    expression_library: dict[str, dict[str, Any]]

    @property
    def slot_id(self) -> str:
        return str(self.slot_blueprint.get("slot_id") or self.slot_blueprint.get("compat_role") or "").strip()

    def expression_metadata(self, expression_mode: str) -> dict[str, Any]:
        value = self.expression_library.get(expression_mode, {})
        return {
            "expression_mode": expression_mode,
            "expression_label": value.get("label", expression_mode),
            "rule_modules_used": [str(item) for item in value.get("prompt_modules", []) if str(item).strip()],
            "layout_policy": value.get("layout_policy"),
            "copy_policy": value.get("copy_policy"),
            "layout_recipe_override": dict(value.get("layout_recipe_override") or {}),
        }


@dataclass(frozen=True)
class DetailPageRuleContext:
    platform_id: str
    overlay: dict[str, Any]
    copy_language: str
    rule_pack_id: str
    rule_pack: Any | None
    rule_pack_version: Any | None
    rule_pack_config: dict[str, Any]
    panel_type_library: dict[str, dict[str, Any]]
    panel_slots: list[dict[str, Any]]


@dataclass(frozen=True)
class ResolvedDetailPanelRule:
    panel_slot: dict[str, Any]
    panel_type_library: dict[str, dict[str, Any]]

    @property
    def slot_id(self) -> str:
        return str(self.panel_slot.get("slot_id") or "").strip()

    @property
    def panel_id(self) -> str:
        return str(self.panel_slot.get("panel_id") or "").strip()

    def panel_type_metadata(self, panel_type: str) -> dict[str, Any]:
        value = self.panel_type_library.get(panel_type, {})
        return {
            "panel_type": panel_type,
            "panel_type_label": value.get("label", panel_type),
            "layout_template": value.get("layout_template", "feature_card"),
            "copy_policy": value.get("copy_policy", "headline_plus_supporting"),
        }

    def display_module_title(self, panel_type: str) -> str:
        slot_id = self.slot_id
        return {
            "detail_slot_01": "首屏亮点",
            "detail_slot_02": "核心概览",
            "detail_slot_03": "核心卖点",
            "detail_slot_04": "场景价值",
            "detail_slot_05": "使用收益",
            "detail_slot_06": "结构工艺",
            "detail_slot_07": "细节参数",
            "detail_slot_08": "收尾总结",
        }.get(slot_id) or {
            "kv_problem_solution": "首屏亮点",
            "icon_island": "核心概览",
            "feature_proof": "卖点佐证",
            "feature_scene": "场景价值",
            "feature_benefit": "利益说明",
            "feature_compare": "对比优势",
            "feature_exploded_view": "结构示意",
            "feature_process_material": "工艺材质",
            "detail_closeup": "细节特写",
            "parameter_explainer": "参数说明",
            "brand_authority": "品牌背书",
            "sales_proof": "实力证明",
            "promo_gift": "活动亮点",
            "product_selector": "选购建议",
        }.get(panel_type, "详情模块")

    def display_module_kind(self, panel_type: str) -> str:
        return {
            "kv_problem_solution": "首屏亮点",
            "icon_island": "核心概览",
            "feature_proof": "卖点佐证",
            "feature_scene": "场景价值",
            "feature_benefit": "利益说明",
            "feature_compare": "对比优势",
            "feature_exploded_view": "结构示意",
            "feature_process_material": "工艺材质",
            "detail_closeup": "细节特写",
            "parameter_explainer": "参数说明",
            "brand_authority": "品牌背书",
            "sales_proof": "实力证明",
            "promo_gift": "活动亮点",
            "product_selector": "选购建议",
        }.get(panel_type, "详情模块")

    def display_module_intent(
        self,
        *,
        panel_type: str,
        panel_goal: str,
        copy_focus: str,
        panel_type_reason: str,
        sanitize: callable | None = None,
        is_internal_label: callable | None = None,
    ) -> str:
        sanitizer = sanitize or (lambda value: str(value or "").strip())
        internal_detector = is_internal_label or (lambda value: False)
        explicit = sanitizer(panel_goal) or sanitizer(copy_focus)
        if explicit and not internal_detector(explicit):
            return explicit
        fallback = {
            "kv_problem_solution": "突出产品核心价值和第一卖点",
            "icon_island": "汇总核心卖点并快速建立认知",
            "feature_proof": "突出核心卖点并补充可信佐证",
            "feature_scene": "强调真实使用场景中的收益",
            "feature_benefit": "解释用户能获得的实际好处",
            "feature_compare": "说明产品相较同类的优势",
            "feature_exploded_view": "解释结构能力与工作逻辑",
            "feature_process_material": "说明材质、做工与细节质感",
            "detail_closeup": "放大关键细节与结构特征",
            "parameter_explainer": "用更清晰的方式呈现参数与要点",
            "brand_authority": "补充品牌与信任信息",
            "sales_proof": "加强实力与认可度表达",
            "promo_gift": "补充下单理由与优惠信息",
            "product_selector": "帮助用户快速判断适合场景",
        }.get(panel_type, "")
        reason = sanitizer(panel_type_reason)
        if reason and not internal_detector(reason):
            return reason
        return fallback or "围绕商品核心价值做清晰表达"

    def display_tags(
        self,
        *,
        display_module_kind: str,
        narrative_section: str,
        visual_truth_mode: str,
    ) -> list[str]:
        section_label = {
            "trust_overview": "可信概览",
            "mechanism": "机制说明",
            "feature_a": "核心卖点",
            "feature_b": "场景延展",
            "usage_scene": "使用场景",
            "parameter_proof": "参数佐证",
            "differentiator": "差异优势",
            "closing_cta": "收尾总结",
        }.get(str(narrative_section or "").strip(), "")
        truth_label = {
            "faithful_closeup": "真实局部图",
            "mechanism_illustration": "机制示意图",
            "scene_reconstruction": "场景重建图",
            "parameter_board": "参数说明图",
        }.get(str(visual_truth_mode or "").strip(), "")
        result: list[str] = []
        seen: set[str] = set()
        for item in (display_module_kind, section_label, truth_label):
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result


def _merge_rule_list(
    configured_items: list[dict[str, Any]] | None,
    seed_items: list[dict[str, Any]],
    *,
    key_field: str,
) -> list[dict[str, Any]]:
    if not configured_items:
        return [{**item} for item in seed_items]
    seed_by_key = {
        str(item.get(key_field) or "").strip(): item
        for item in seed_items
        if str(item.get(key_field) or "").strip()
    }
    merged: list[dict[str, Any]] = []
    for item in configured_items:
        if not isinstance(item, dict):
            continue
        item_key = str(item.get(key_field) or "").strip()
        merged.append({
            **dict(seed_by_key.get(item_key, {})),
            **item,
        })
    return merged


def resolve_main_gallery_context(
    platform_id: str | None,
    *,
    db: Session | None = None,
) -> MainGalleryRuleContext:
    active_platform_id = str(platform_id or "").strip() or "default"
    profile = get_platform_or_none(active_platform_id)
    rule_pack_id = profile.main_rule_pack_id if profile else get_main_rule_pack_id(active_platform_id)
    rule_pack, version, config = load_published_rule_pack_config(
        asset_family="main_gallery",
        rule_pack_key=rule_pack_id,
        platform_id=active_platform_id,
        db=db,
    )
    overlay = resolve_main_platform_overlay(active_platform_id, db=db)
    grammar_family = None
    family_id = str(overlay.get("grammar_family") or "").strip()
    if family_id:
        grammar_family = dict(PLATFORM_GRAMMAR_FAMILIES.get(family_id, {})) or None
    if grammar_family is None:
        for family in PLATFORM_GRAMMAR_FAMILIES.values():
            if active_platform_id in family.get("platforms", []):
                grammar_family = dict(family)
                break
    harness_config = get_harness_config(platform_id=active_platform_id, db=db)
    return MainGalleryRuleContext(
        platform_id=active_platform_id,
        overlay=overlay,
        grammar_family=grammar_family,
        rule_pack_id=rule_pack_id,
        rule_pack=rule_pack,
        rule_pack_version=version,
        rule_pack_config=dict(config or {}),
        harness_config=harness_config,
    )


def resolve_main_platform_overlay(
    platform_id: str | None,
    *,
    db: Session | None = None,
) -> dict[str, Any]:
    active_platform_id = str(platform_id or "").strip() or "default"
    if db is not None:
        try:
            ensure_system_platform_configs(db)
            from app.models.platform_config import PlatformConfigModel

            db_config = (
                db.query(PlatformConfigModel)
                .filter(PlatformConfigModel.platform_id == active_platform_id, PlatformConfigModel.is_active.is_(True))
                .first()
            )
            if db_config:
                base = {**PLATFORM_OVERLAYS["default"]}
                base.update({
                    "id": db_config.platform_id,
                    "overlay_id": db_config.platform_id,
                    "copy_language": db_config.copy_language,
                    "allow_dense_copy": db_config.allow_dense_copy,
                    "allow_certificate_elements": db_config.allow_certificate_elements,
                    "allow_compare_overlay": db_config.allow_compare_overlay,
                    "hero_text_overlay": db_config.hero_text_overlay,
                    "white_bg_mandatory": db_config.white_bg_mandatory,
                    "prohibited_elements": list(db_config.prohibited_elements or []),
                    "negative_prompt_additions": list(db_config.negative_prompt_additions or []),
                    "constraints": list(db_config.constraints or base.get("constraints", [])),
                })
                if profile := get_platform_or_none(active_platform_id):
                    base.setdefault("locale", profile.locale)
                return base
        except Exception:
            pass

    overlay = {**PLATFORM_OVERLAYS["default"], **PLATFORM_OVERLAYS.get(active_platform_id, {})}
    overlay["overlay_id"] = overlay.get("id")
    return overlay


def resolve_main_slot_rules(
    platform_id: str | None,
    *,
    db: Session | None = None,
) -> list[ResolvedMainSlotRule]:
    context = resolve_main_gallery_context(platform_id, db=db)
    seed_slot_blueprints = MAIN_GALLERY_SLOT_PRESETS.get(
        context.rule_pack_id,
        MAIN_GALLERY_SLOT_PRESETS[DEFAULT_MAIN_RULE_PACK_ID],
    )
    configured_slot_plan = (context.rule_pack_config or {}).get("slot_plan")
    merged_slot_plan = _merge_rule_list(
        configured_slot_plan,
        seed_slot_blueprints,
        key_field="slot_id",
    )

    raw_expression_library = (context.rule_pack_config or {}).get("expression_library")
    if isinstance(raw_expression_library, dict) and raw_expression_library:
        expression_library = {
            expression_mode: {
                **dict(EXPRESSION_LIBRARY.get(expression_mode, {})),
                **dict(value or {}),
            }
            for expression_mode, value in raw_expression_library.items()
        }
    else:
        harness_expression_library = context.harness_config.get("expression_library")
        expression_library = (
            {
                expression_mode: {
                    **dict(EXPRESSION_LIBRARY.get(expression_mode, {})),
                    **dict(value or {}),
                }
                for expression_mode, value in harness_expression_library.items()
            }
            if isinstance(harness_expression_library, dict) and harness_expression_library
            else {key: dict(value) for key, value in EXPRESSION_LIBRARY.items()}
        )

    rules: list[ResolvedMainSlotRule] = []
    for item in merged_slot_plan:
        slot_blueprint = {
            **item,
            "platform_rule_pack": context.rule_pack.id if context.rule_pack is not None else context.rule_pack_id,
            "platform_rule_pack_key": context.rule_pack.rule_pack_key if context.rule_pack is not None else context.rule_pack_id,
            "platform_rule_pack_version": context.rule_pack_version.version_no if context.rule_pack_version is not None else 1,
        }
        rules.append(
            ResolvedMainSlotRule(
                slot_blueprint=slot_blueprint,
                expression_library=expression_library,
            )
        )
    return rules


def resolve_main_slot_preferences(
    platform_id: str | None,
    incoming: list[dict[str, Any]] | None,
    *,
    db: Session | None = None,
) -> dict[str, dict[str, Any]]:
    valid_slots = {rule.slot_id for rule in resolve_main_slot_rules(platform_id, db=db)}
    resolved: dict[str, dict[str, Any]] = {}
    for item in incoming or []:
        if not isinstance(item, dict):
            continue
        slot_id = str(item.get("slot_id") or "").strip()
        if slot_id not in valid_slots:
            continue
        expression_mode = str(item.get("expression_mode") or "").strip() or None
        resolved[slot_id] = {
            "slot_id": slot_id,
            "expression_mode": expression_mode,
            "locked": bool(item.get("locked")),
            **({"display_order": int(item.get("display_order") or 0)} if item.get("display_order") is not None else {}),
        }
    return resolved


def resolve_main_expression_metadata(
    expression_mode: str,
    *,
    platform_id: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    context = resolve_main_gallery_context(platform_id, db=db)
    expression_library = {}
    raw_expression_library = (context.rule_pack_config or {}).get("expression_library")
    if isinstance(raw_expression_library, dict) and raw_expression_library:
        expression_library = raw_expression_library
    else:
        harness_expression_library = context.harness_config.get("expression_library")
        if isinstance(harness_expression_library, dict):
            expression_library = harness_expression_library
    value = {
        **dict(EXPRESSION_LIBRARY.get(expression_mode, {})),
        **dict(expression_library.get(expression_mode, {})),
    }
    return {
        "expression_mode": expression_mode,
        "expression_label": value.get("label", expression_mode),
        "rule_modules_used": [str(item) for item in value.get("prompt_modules", []) if str(item).strip()],
        "layout_policy": value.get("layout_policy"),
        "copy_policy": value.get("copy_policy"),
        "layout_recipe_override": dict(value.get("layout_recipe_override") or {}),
    }


def resolve_detail_page_context(
    platform_id: str | None,
    *,
    db: Session | None = None,
) -> DetailPageRuleContext:
    active_platform_id = str(platform_id or "").strip() or "amazon"
    profile = get_platform_or_none(active_platform_id)
    rule_pack_id = profile.detail_rule_pack_id if profile else DETAIL_RULE_PACK_ID
    rule_pack, version, config = load_published_rule_pack_config(
        asset_family="detail_page",
        rule_pack_key=rule_pack_id,
        platform_id=active_platform_id,
        db=db,
    )
    overlay = resolve_detail_platform_overlay(active_platform_id, db=db)
    copy_language = str(overlay.get("copy_language") or "en")

    raw_panel_library = (config or {}).get("panel_type_library")
    if isinstance(raw_panel_library, dict) and raw_panel_library:
        panel_type_library = {
            panel_type: {
                **dict(DETAIL_PANEL_TYPE_LIBRARY.get(panel_type, {})),
                **dict(value or {}),
            }
            for panel_type, value in raw_panel_library.items()
        }
    else:
        panel_type_library = {key: dict(value) for key, value in DETAIL_PANEL_TYPE_LIBRARY.items()}

    raw_slot_plan = (config or {}).get("slot_plan")
    panel_slots = _merge_rule_list(raw_slot_plan, DETAIL_PANEL_SLOT_PRESETS, key_field="slot_id")
    return DetailPageRuleContext(
        platform_id=active_platform_id,
        overlay=overlay,
        copy_language=copy_language,
        rule_pack_id=rule_pack_id,
        rule_pack=rule_pack,
        rule_pack_version=version,
        rule_pack_config=dict(config or {}),
        panel_type_library=panel_type_library,
        panel_slots=panel_slots,
    )


def resolve_detail_platform_overlay(
    platform_id: str | None,
    *,
    db: Session | None = None,
) -> dict[str, Any]:
    active_platform_id = str(platform_id or "").strip().lower() or "amazon"
    profile = get_platform_or_none(active_platform_id)
    base_overlay = dict(resolve_main_platform_overlay(active_platform_id, db=db))
    copy_language = visible_copy_language_for_platform(active_platform_id)
    locale = profile.locale if profile is not None else ("zh-CN" if copy_language == "zh" else "en-US")
    constraints = [str(item) for item in base_overlay.get("constraints", []) if str(item).strip()]
    if copy_language == "zh":
        constraints.extend(simplified_chinese_visible_copy_constraints())
    else:
        constraints.append("Visible copy should stay concise and commercially usable.")
    return {
        "id": active_platform_id,
        "overlay_id": active_platform_id,
        "locale": locale,
        "copy_language": copy_language,
        "constraints": list(dict.fromkeys(constraints)),
    }


def resolve_detail_panel_rules(
    platform_id: str | None,
    *,
    db: Session | None = None,
) -> list[ResolvedDetailPanelRule]:
    context = resolve_detail_page_context(platform_id, db=db)
    return [
        ResolvedDetailPanelRule(panel_slot=dict(item), panel_type_library=context.panel_type_library)
        for item in context.panel_slots
    ]


def resolve_detail_panel_preferences(
    incoming: list[dict[str, Any]] | None,
    *,
    platform_id: str | None = None,
    db: Session | None = None,
) -> dict[str, dict[str, Any]]:
    context = resolve_detail_page_context(platform_id, db=db)
    valid_slots = {item["slot_id"] for item in context.panel_slots}
    valid_panel_types = set(context.panel_type_library)
    resolved: dict[str, dict[str, Any]] = {}
    for item in incoming or []:
        if not isinstance(item, dict):
            continue
        slot_id = str(item.get("slot_id") or "").strip()
        panel_type = str(item.get("panel_type") or "").strip()
        if slot_id not in valid_slots or panel_type not in valid_panel_types:
            continue
        resolved[slot_id] = {
            "slot_id": slot_id,
            "panel_type": panel_type,
            "display_order": int(item.get("display_order") or 0),
            "locked": bool(item.get("locked")),
            **({"panel_type_reason": str(item.get("panel_type_reason") or "").strip()} if item.get("panel_type_reason") else {}),
        }
    return resolved


def recommend_detail_panel_types(
    *,
    confirmed_copy: dict[str, Any],
    analysis_snapshot: dict[str, Any],
    platform_id: str,
    style_images_present: bool,
    db: Session | None = None,
) -> list[dict[str, Any]]:
    context = resolve_detail_page_context(platform_id, db=db)
    panel_rules = resolve_detail_panel_rules(platform_id, db=db)

    from app.services.detail_panel_library import _analysis_value, _parameter_strings, _split_points
    from app.services.copy_normalization import is_low_information_copy_text, key_parameter_strings, normalize_copy_payload

    normalized_copy = normalize_copy_payload(confirmed_copy)
    selling_points = _split_points(normalized_copy.get("core_selling_points") or normalized_copy.get("selling_points"))
    usage_scenes = _split_points(normalized_copy.get("hero_scene") or normalized_copy.get("usage_scenes"))
    product_name = str(normalized_copy.get("product_name") or "").strip()
    usage_scenes = [item for item in usage_scenes if not is_low_information_copy_text(item, product_name=product_name)]
    specs = key_parameter_strings(normalized_copy.get("key_parameters")) or _split_points(normalized_copy.get("specs"))
    parameters = _parameter_strings(normalized_copy.get("key_parameters"))
    must_keep = _analysis_value(analysis_snapshot, "reference_summary", "must_keep")

    recommended: list[dict[str, Any]] = []
    for rule in panel_rules:
        slot = rule.panel_slot
        slot_id = rule.slot_id
        panel_type = str(slot.get("default_panel_type") or "")
        reason = "按默认详情页推荐组合生成。"
        if slot_id == "detail_slot_01":
            panel_type = "kv_problem_solution"
            reason = "首屏优先说明产品是什么、解决什么问题。"
        elif slot_id == "detail_slot_02":
            panel_type = "icon_island"
            reason = "概览槽位优先汇总核心卖点，形成 icon 岛。"
        elif slot_id == "detail_slot_03":
            panel_type = "feature_proof" if specs or parameters else "feature_benefit"
            reason = "检测到参数/规格信息，优先做卖点佐证。" if specs or parameters else "缺少强参数时优先做利益点解释。"
        elif slot_id == "detail_slot_04":
            panel_type = "feature_scene" if usage_scenes else "feature_compare"
            reason = "存在场景文案，优先做场景代入。" if usage_scenes else "缺少场景文案时用对比优势强化卖点。"
        elif slot_id == "detail_slot_05":
            panel_type = "feature_benefit"
            reason = "中段继续承接消费者利益点。"
        elif slot_id == "detail_slot_06":
            panel_type = "feature_process_material" if must_keep else "feature_exploded_view"
            reason = "有结构/材质提示，优先做工艺材质说明。" if must_keep else "默认用爆炸结构说明内部能力。"
        elif slot_id == "detail_slot_07":
            panel_type = "detail_closeup"
            reason = "后段优先补充产品细节特写。"
        elif slot_id == "detail_slot_08":
            panel_type = "parameter_explainer" if parameters or specs else "sales_proof"
            reason = "收尾优先补参数解释。" if parameters or specs else "无强参数时用销量/实力类收尾。"

        if style_images_present and panel_type == "kv_problem_solution":
            reason += " 已上传风格图，首屏会优先跟随风格参考。"
        if context.platform_id == "1688" and slot_id == "detail_slot_08":
            panel_type = "promo_gift"
            reason = "1688 详情页收尾可优先给出促销/赠品下单理由。"

        recommended.append({"slot_id": slot_id, "panel_type": panel_type, "panel_type_reason": reason})
    return recommended


def resolve_detail_panel_by_panel_id(
    panel_id: str,
    *,
    platform_id: str | None = None,
    db: Session | None = None,
) -> ResolvedDetailPanelRule | None:
    target_panel_id = str(panel_id or "").strip()
    for rule in resolve_detail_panel_rules(platform_id, db=db):
        if rule.panel_id == target_panel_id:
            return rule
    return None


def resolve_detail_visual_truth_mode(panel_type: str) -> str:
    if panel_type in {"feature_exploded_view", "feature_process_material"}:
        return "mechanism_illustration"
    if panel_type in {"feature_scene", "feature_compare", "feature_benefit", "kv_problem_solution"}:
        return "scene_reconstruction"
    if panel_type in {"parameter_explainer", "sales_proof"}:
        return "parameter_board"
    return "faithful_closeup"


def resolve_detail_display_module_title(panel_type: str, slot_id: str) -> str:
    return ResolvedDetailPanelRule(
        panel_slot={"slot_id": slot_id, "panel_id": slot_id},
        panel_type_library={},
    ).display_module_title(panel_type)


def resolve_detail_display_module_kind(panel_type: str) -> str:
    return ResolvedDetailPanelRule(
        panel_slot={"slot_id": "", "panel_id": ""},
        panel_type_library={},
    ).display_module_kind(panel_type)


def resolve_detail_display_module_intent(
    *,
    panel_type: str,
    panel_goal: str,
    copy_focus: str,
    panel_type_reason: str,
    sanitize: callable | None = None,
    is_internal_label: callable | None = None,
) -> str:
    return ResolvedDetailPanelRule(
        panel_slot={"slot_id": "", "panel_id": ""},
        panel_type_library={},
    ).display_module_intent(
        panel_type=panel_type,
        panel_goal=panel_goal,
        copy_focus=copy_focus,
        panel_type_reason=panel_type_reason,
        sanitize=sanitize,
        is_internal_label=is_internal_label,
    )


def resolve_detail_display_tags(
    *,
    display_module_kind: str,
    narrative_section: str,
    visual_truth_mode: str,
) -> list[str]:
    return ResolvedDetailPanelRule(
        panel_slot={"slot_id": "", "panel_id": ""},
        panel_type_library={},
    ).display_tags(
        display_module_kind=display_module_kind,
        narrative_section=narrative_section,
        visual_truth_mode=visual_truth_mode,
    )
