"""Helper functions that build category-aware prompt sections for LLM calls.

These are extracted from upstream.py to keep Chinese text encoding safe.
"""

from __future__ import annotations

from typing import Any


def build_category_kb_section(
    analysis_snapshot: dict[str, Any] | None,
    category_parameter_rules: dict[str, Any] | None,
) -> str:
    """Build the category knowledge base section for extract_parameters prompt."""
    recognized = (analysis_snapshot or {}).get("recognized_product") or {}
    category = str(recognized.get("category", "")).strip() if isinstance(recognized, dict) else ""
    category_slug = str(recognized.get("category_slug", "") or "").strip()
    rules = category_parameter_rules or {}

    if rules:
        core_params = rules.get("core_purchase_parameters") or []
        core_parts = []
        for p in core_params:
            label = p.get("label", "")
            key = p.get("key", "")
            core_parts.append(f"{label}({key})")
        core_params_text = "、".join(core_parts) if core_parts else "请根据你的品类知识判断"
        anti_text = "、".join(rules.get("anti_patterns") or []) or "无"
        hints_text = "；".join(rules.get("parameter_extraction_hints") or []) or "无"
        reasoning = rules.get("category_reasoning_hints") or ""
        cat_id = f"{category}（{category_slug}）" if category_slug else category
        return (
            f"【品类知识】当前品类：{cat_id}。\n"
            f"品类背景：{reasoning}\n\n"
            f"【参数规则】\n"
            f"核心参数类型（优先识别）：{core_params_text}\n"
            f"提取指引：{hints_text}\n"
            f"不要提取以下内容为核心参数：{anti_text}\n\n"
            f"【推理要求】\n"
            f"1. 上述品类知识是你的背景——请结合你对这个品类的理解，判断什么参数对消费者真正重要\n"
            f"2. 检查商品图，提取你能观测到的所有结构化信息\n"
            f"3. 将外观特征（颜色/形状/材质/按钮布局等）归入 product_advantages 或 feature_highlights，不要混入 key_parameters\n"
            f"4. key_parameters 只放影响购买决策的核心性能/规格参数\n\n"
        )
    elif category:
        return (
            f"【品类知识】当前品类：{category}。请结合你对这个品类的训练知识，"
            f"判断什么参数是消费者购买决策的核心，优先提取性能/规格参数，"
            f"不要将外观特征（形状、颜色、按钮布局）作为核心参数。\n\n"
        )
    return ""


def build_completion_kb_section(
    analysis_snapshot: dict[str, Any] | None,
    category_parameter_rules: dict[str, Any] | None,
) -> str:
    """Build the category knowledge base section for complete_parameters prompt."""
    recognized = (analysis_snapshot or {}).get("recognized_product") or {}
    category = str(recognized.get("category", "")).strip() if isinstance(recognized, dict) else ""
    rules = category_parameter_rules or {}

    if rules:
        core_params = rules.get("core_purchase_parameters") or []
        core_parts = []
        for p in core_params:
            label = p.get("label", "")
            key = p.get("key", "")
            core_parts.append(f"{label}({key})")
        core_params_text = "、".join(core_parts) if core_parts else "请根据你的品类知识补充"
        reasoning = rules.get("category_reasoning_hints") or ""
        return (
            f"【品类背景】当前品类：{category}。{reasoning}\n"
            f"核心参数（优先补全）：{core_params_text}\n\n"
        )
    elif category:
        return (
            f"【品类背景】当前品类：{category}。请结合你对这个品类的训练知识，"
            f"补充首轮提取中遗漏的核心购买决策参数。\n\n"
        )
    return ""


def build_copy_design_kb_section(
    analysis_snapshot: dict[str, Any] | None,
    category_parameter_rules: dict[str, Any] | None,
) -> str:
    """Build the category selling point section for design_main_copy_blocks prompt."""
    recognized = (analysis_snapshot or {}).get("recognized_product") or {}
    category = str(recognized.get("category", "")).strip() if isinstance(recognized, dict) else ""
    rules = category_parameter_rules or {}

    if rules:
        themes = rules.get("selling_point_themes") or []
        theme_names = [t.get("theme", "") for t in themes if t.get("theme")]
        themes_text = "、".join(theme_names) if theme_names else "通用卖点"
        reasoning = rules.get("category_reasoning_hints") or ""
        return (
            f"【品类卖点方向】当前品类：{category}。{reasoning}\n"
            f"常见卖点方向：{themes_text}\n"
            f"【设计要求】\n"
            f"- headline 必须体现品类核心价值，禁止使用'品质之选''匠心制造'等空洞营销词\n"
            f"- proof_lines 要从品类核心参数中选取，每一条都是消费者可感知的具体价值点\n"
            f"- 针对不同 slot 角色设计不同角度文案\n\n"
        )
    elif category:
        return (
            f"【品类卖点方向】当前品类：{category}。请结合你的训练知识，"
            f"为该品类设计有区分度的卖点文案，禁止使用空洞营销词。\n\n"
        )
    return ""
