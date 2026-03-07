from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from app.services.copy_normalization import normalize_copy_payload
from app.services.reference_images import LoadedReferenceImage, build_reference_manifest, load_reference_images
from app.services.upstream import WhataiClient

DETAIL_PAGE_USE_CASE = "amazon_detail"
DETAIL_PAGE_ASPECT_RATIO = "21:9"
DETAIL_PAGE_IMAGE_SIZE = "1792x768"
DETAIL_PAGE_PANEL_COUNT = 8

DETAIL_PANEL_SPECS: list[dict[str, str]] = [
    {"panel_id": "panel_01_cover", "panel_label": "首屏总览", "layout_notes": "单屏强主视觉，突出标题和第一卖点。"},
    {"panel_id": "panel_02_overview", "panel_label": "产品概览", "layout_notes": "横向信息排布，主产品完整清晰，适合概览型文案。"},
    {"panel_id": "panel_03_feature_a", "panel_label": "卖点一", "layout_notes": "围绕单一核心卖点构图，文案短促清晰。"},
    {"panel_id": "panel_04_feature_b", "panel_label": "卖点二", "layout_notes": "补充第二卖点，保留强对比和功能特写。"},
    {"panel_id": "panel_05_scene", "panel_label": "场景展示", "layout_notes": "展示使用场景，但画面主体仍是商品。"},
    {"panel_id": "panel_06_detail", "panel_label": "细节工艺", "layout_notes": "局部特写或结构剖面，适合材质与工艺说明。"},
    {"panel_id": "panel_07_specs", "panel_label": "参数信息", "layout_notes": "保留参数/要点排版空间，适合规格信息展示。"},
    {"panel_id": "panel_08_closing", "panel_label": "收束总结", "layout_notes": "作为结尾模块，统一强调产品价值和整体质感。"},
]


def build_detail_strategy_preview(
    confirmed_copy: dict[str, Any],
    *,
    product_images: list[Any],
    style_images: list[Any] | None = None,
    analysis_snapshot: dict[str, Any] | None = None,
    planner_instruction: str | None = None,
) -> dict[str, Any]:
    normalized_copy = normalize_copy_payload(confirmed_copy)
    product_loaded = load_reference_images(product_images) if product_images else []
    style_loaded = load_reference_images(style_images or []) if style_images else []

    if not product_loaded:
        return {
            "use_case": DETAIL_PAGE_USE_CASE,
            "aspect_ratio": DETAIL_PAGE_ASPECT_RATIO,
            "panel_count": DETAIL_PAGE_PANEL_COUNT,
            "planner_instruction": planner_instruction,
            "product_reference_manifest": [],
            "style_reference_manifest": [],
            "style_summary": _style_summary(normalized_copy, style_loaded),
            "style_source": "style_images" if style_loaded else "copy_fields",
            "panel_plan": [],
        }

    product_manifest = build_reference_manifest(product_loaded)
    style_manifest = build_reference_manifest(style_loaded)
    fallback_plan = _build_default_panel_plan(
        confirmed_copy=normalized_copy,
        product_manifest=product_manifest,
        style_manifest=style_manifest,
        analysis_snapshot=analysis_snapshot or {},
        planner_instruction=planner_instruction,
    )

    client = WhataiClient()
    product_grid, style_grid = build_detail_reference_grids(product_loaded, style_loaded)
    llm_plan = client.plan_detail_page_panels(
        confirmed_copy=normalized_copy,
        product_manifest=product_manifest,
        style_manifest=style_manifest,
        product_grid=product_grid,
        style_grid=style_grid,
        planner_instruction=planner_instruction,
        analysis_snapshot=analysis_snapshot or {},
    )

    merged_plan = _merge_panel_plan(fallback_plan, llm_plan)
    return {
        "use_case": DETAIL_PAGE_USE_CASE,
        "aspect_ratio": DETAIL_PAGE_ASPECT_RATIO,
        "panel_count": DETAIL_PAGE_PANEL_COUNT,
        "planner_instruction": planner_instruction,
        "product_reference_manifest": product_manifest,
        "style_reference_manifest": style_manifest,
        "style_summary": _style_summary(normalized_copy, style_loaded),
        "style_source": "style_images" if style_loaded else "copy_fields",
        "panel_plan": merged_plan,
    }


def normalize_detail_strategy_preview(
    strategy_preview: dict[str, Any] | None,
    confirmed_copy: dict[str, Any],
    *,
    product_images: list[Any],
    style_images: list[Any] | None = None,
    analysis_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if (
        isinstance(strategy_preview, dict)
        and strategy_preview.get("panel_plan")
        and _manifest_count(strategy_preview.get("product_reference_manifest")) == len(product_images)
        and _manifest_count(strategy_preview.get("style_reference_manifest")) == len(style_images or [])
    ):
        return strategy_preview
    return build_detail_strategy_preview(
        confirmed_copy,
        product_images=product_images,
        style_images=style_images,
        analysis_snapshot=analysis_snapshot,
        planner_instruction=(strategy_preview or {}).get("planner_instruction") if strategy_preview else None,
    )


def build_detail_reference_grids(
    product_loaded: list[LoadedReferenceImage],
    style_loaded: list[LoadedReferenceImage],
) -> tuple[LoadedReferenceImage, LoadedReferenceImage | None]:
    product_grid = _build_reference_grid_image(product_loaded, image_id="detail_product_grid", file_name="detail_product_grid.jpg")
    style_grid = (
        _build_reference_grid_image(style_loaded, image_id="detail_style_grid", file_name="detail_style_grid.jpg")
        if style_loaded
        else None
    )
    return product_grid, style_grid


def build_detail_prompt_previews(
    confirmed_copy: dict[str, Any],
    strategy_preview: dict[str, Any],
    instruction: str | None = None,
) -> list[dict[str, Any]]:
    manifest_by_product_id = {
        item["image_id"]: item
        for item in strategy_preview.get("product_reference_manifest", [])
        if isinstance(item, dict) and item.get("image_id")
    }
    manifest_by_style_id = {
        item["image_id"]: item
        for item in strategy_preview.get("style_reference_manifest", [])
        if isinstance(item, dict) and item.get("image_id")
    }

    previews: list[dict[str, Any]] = []
    for item in strategy_preview.get("panel_plan", []):
        if not isinstance(item, dict) or not item.get("panel_id"):
            continue
        preview = compose_detail_panel_prompt(
            confirmed_copy=confirmed_copy,
            strategy_preview=strategy_preview,
            panel_id=str(item["panel_id"]),
            instruction=instruction,
            panel_plan_item=item,
        )
        preview["product_reference_images_used"] = [
            manifest_by_product_id[image_id]
            for image_id in preview.get("product_reference_ids", [])
            if image_id in manifest_by_product_id
        ]
        preview["style_reference_images_used"] = [
            manifest_by_style_id[image_id]
            for image_id in preview.get("style_reference_ids", [])
            if image_id in manifest_by_style_id
        ]
        previews.append(preview)
    return previews


def compose_detail_panel_prompt(
    *,
    confirmed_copy: dict[str, Any],
    strategy_preview: dict[str, Any],
    panel_id: str,
    instruction: str | None = None,
    panel_plan_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = panel_plan_item or find_detail_panel_plan_item(strategy_preview, panel_id)
    product_name = _fallback_text(confirmed_copy.get("product_name"), "product")
    style_summary = _fallback_text(strategy_preview.get("style_summary"), "clean ecommerce detail page style")
    copy_lines = [str(item).strip() for item in plan.get("copy_lines", []) if str(item).strip()]
    planner_base = _fallback_text(
        plan.get("planner_prompt_base"),
        f"Create one Amazon detail page panel for {product_name} with clear layout and strong product fidelity.",
    )
    reference_rule = (
        "Use the uploaded product multi-angle grid as the primary fidelity reference. "
        "If style/font reference images exist, follow their color and typography direction."
    )

    blocks = {
        "goal": planner_base,
        "subject": f"Keep {product_name} as the dominant subject. Preserve silhouette, structure, color and proportions.",
        "layout": _fallback_text(plan.get("layout_notes"), "Single 21:9 panel layout with clear hierarchy for image and text."),
        "text": _build_text_block(copy_lines),
        "style": f"Use an Amazon-ready detail page look. Style direction: {style_summary}. {reference_rule}",
        "constraints": (
            "Render one single horizontal detail page panel only. "
            "All visible text should be in English, short, legible and integrated into the composition. "
            "Do not create a 5-image gallery, watermark, UI screenshot, poster collage, duplicated product or irrelevant props."
        ),
        "instruction": _fallback_text(instruction, "No extra edit instruction."),
    }
    final_prompt = (
        f"Create a single Amazon detail page panel image in a {DETAIL_PAGE_ASPECT_RATIO} horizontal layout. "
        f"Visible text must be English. "
        f"Goal: {blocks['goal']} "
        f"Subject: {blocks['subject']} "
        f"Layout: {blocks['layout']} "
        f"On-image copy: {blocks['text']} "
        f"Style: {blocks['style']} "
        f"Constraints: {blocks['constraints']} "
        f"Additional instruction: {blocks['instruction']}"
    )

    return {
        "panel_id": panel_id,
        "panel_label": str(plan.get("panel_label") or panel_id),
        "display_order": int(plan.get("display_order") or 0),
        "aspect_ratio": DETAIL_PAGE_ASPECT_RATIO,
        "use_case": DETAIL_PAGE_USE_CASE,
        "blocks": blocks,
        "strategy_fields_used": [
            "detail_strategy_preview.style_summary",
            "detail_strategy_preview.panel_plan.copy_lines",
            "detail_strategy_preview.panel_plan.layout_notes",
            "detail_strategy_preview.panel_plan.planner_prompt_base",
        ],
        "product_reference_ids": [str(item) for item in plan.get("product_reference_ids", []) if str(item).strip()],
        "style_reference_ids": [str(item) for item in plan.get("style_reference_ids", []) if str(item).strip()],
        "planner_source": str(plan.get("planner_source") or "rule_based"),
        "planner_base": planner_base,
        "final_prompt": final_prompt,
    }


def find_detail_panel_plan_item(strategy_preview: dict[str, Any], panel_id: str) -> dict[str, Any]:
    for item in strategy_preview.get("panel_plan", []):
        if isinstance(item, dict) and item.get("panel_id") == panel_id:
            return item
    spec = next((item for item in DETAIL_PANEL_SPECS if item["panel_id"] == panel_id), None)
    return {
        "panel_id": panel_id,
        "panel_label": (spec or {}).get("panel_label", panel_id),
        "display_order": 0,
        "planner_prompt_base": "",
        "copy_lines": [],
        "layout_notes": (spec or {}).get("layout_notes", ""),
        "planner_source": "rule_based",
        "product_reference_ids": [],
        "style_reference_ids": [],
    }


def _build_default_panel_plan(
    *,
    confirmed_copy: dict[str, Any],
    product_manifest: list[dict[str, Any]],
    style_manifest: list[dict[str, Any]],
    analysis_snapshot: dict[str, Any],
    planner_instruction: str | None,
) -> list[dict[str, Any]]:
    product_name = _fallback_text(confirmed_copy.get("product_name"), "产品")
    headline = _fallback_text(confirmed_copy.get("headline"), product_name)
    selling_points = _split_points(confirmed_copy.get("selling_points"))
    usage_scenes = _split_points(confirmed_copy.get("usage_scenes"))
    specs = _split_points(confirmed_copy.get("specs"))
    key_parameters = _split_key_parameters(confirmed_copy.get("key_parameters"))
    reference_summary = analysis_snapshot.get("reference_summary") if isinstance(analysis_snapshot, dict) else {}
    shape_hint = _fallback_text((reference_summary or {}).get("shape"), "keep the uploaded product structure consistent")

    def selling_point(index: int) -> str:
        if selling_points:
            return selling_points[min(index, len(selling_points) - 1)]
        return headline

    def scene_point() -> str:
        return usage_scenes[0] if usage_scenes else f"Designed for daily use"

    def spec_point() -> str:
        if specs:
            return specs[0]
        if key_parameters:
            return key_parameters[0]
        return "Key specifications"

    closing_line = selling_points[0] if selling_points else headline
    style_ids = [item["image_id"] for item in style_manifest]
    product_ids = [item["image_id"] for item in product_manifest]

    panel_copy_map = {
        "panel_01_cover": [headline, selling_point(0)],
        "panel_02_overview": [product_name, selling_point(1)],
        "panel_03_feature_a": [selling_point(0), spec_point()],
        "panel_04_feature_b": [selling_point(1), selling_point(2)],
        "panel_05_scene": [scene_point(), selling_point(0)],
        "panel_06_detail": [spec_point(), shape_hint],
        "panel_07_specs": key_parameters[:3] or specs[:3] or [spec_point()],
        "panel_08_closing": [headline, closing_line],
    }

    panel_plan: list[dict[str, Any]] = []
    for display_order, spec in enumerate(DETAIL_PANEL_SPECS, start=1):
        extra_instruction = f" Extra planner instruction: {planner_instruction}." if planner_instruction else ""
        panel_plan.append(
            {
                "panel_id": spec["panel_id"],
                "panel_label": spec["panel_label"],
                "display_order": display_order,
                "planner_prompt_base": (
                    f"Create a polished Amazon detail page panel for {product_name}. "
                    f"Focus on {panel_copy_map[spec['panel_id']][0]}. "
                    f"Maintain strong product fidelity and leave room for readable English marketing copy.{extra_instruction}"
                ),
                "copy_lines": panel_copy_map[spec["panel_id"]],
                "layout_notes": spec["layout_notes"],
                "planner_source": "rule_based",
                "product_reference_ids": product_ids,
                "style_reference_ids": style_ids,
            }
        )
    return panel_plan


def _merge_panel_plan(
    fallback_plan: list[dict[str, Any]],
    llm_plan: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    llm_by_id = {
        str(item.get("panel_id")): item
        for item in llm_plan
        if isinstance(item, dict) and str(item.get("panel_id") or "").strip()
    }
    merged: list[dict[str, Any]] = []
    for item in fallback_plan:
        llm_item = llm_by_id.get(str(item["panel_id"]))
        if not llm_item:
            merged.append(item)
            continue
        merged_item = {**item}
        for key in ("panel_label", "planner_prompt_base", "layout_notes"):
            value = str(llm_item.get(key) or "").strip()
            if value:
                merged_item[key] = value
        for key in ("copy_lines", "product_reference_ids", "style_reference_ids"):
            value = llm_item.get(key)
            if isinstance(value, list):
                cleaned = [str(entry).strip() for entry in value if str(entry).strip()]
                if cleaned:
                    merged_item[key] = cleaned
        merged_item["planner_source"] = "llm"
        merged.append(merged_item)
    return merged


def _build_reference_grid_image(
    images: list[LoadedReferenceImage],
    *,
    image_id: str,
    file_name: str,
) -> LoadedReferenceImage:
    grid = Image.new("RGB", (2048, 2048), color=(255, 255, 255))
    cell_size = 1024
    padding = 24
    for index, item in enumerate(images[:4]):
        with Image.open(io.BytesIO(item.content)) as source:
            frame = ImageOps.contain(source.convert("RGB"), (cell_size - padding * 2, cell_size - padding * 2))
            row, col = divmod(index, 2)
            x = col * cell_size + (cell_size - frame.width) // 2
            y = row * cell_size + (cell_size - frame.height) // 2
            grid.paste(frame, (x, y))

    buffer = io.BytesIO()
    grid.save(buffer, format="JPEG", quality=92)
    content = buffer.getvalue()
    return LoadedReferenceImage(
        image_id=image_id,
        slot_type="grid",
        display_order=0,
        source_url="",
        width=grid.width,
        height=grid.height,
        mime_type="image/jpeg",
        file_size=len(content),
        file_name=file_name,
        path=Path(file_name),
        content=content,
    )


def _build_text_block(copy_lines: list[str]) -> str:
    if not copy_lines:
        return "Use concise English headline and short supporting copy integrated into the panel."
    return "Suggested English copy lines: " + " | ".join(copy_lines[:3])


def _style_summary(confirmed_copy: dict[str, Any], style_loaded: list[LoadedReferenceImage]) -> str:
    if style_loaded:
        return "Follow the uploaded style and typography reference grid."
    style = " ".join(
        [
            str(value).strip()
            for value in [confirmed_copy.get("style_choice"), confirmed_copy.get("style_custom")]
            if str(value).strip()
        ]
    )
    return style or "clean premium ecommerce detail page design"


def _split_points(value: Any) -> list[str]:
    raw = str(value or "").replace("｜", "\n").replace("|", "\n").replace("、", "\n")
    return [item.strip() for item in raw.replace("/", "\n").splitlines() if item.strip()]


def _split_key_parameters(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("key") or "").strip()
            val = str(item.get("value") or "").strip()
            unit = str(item.get("unit") or "").strip()
            text = " ".join(part for part in [label, val + unit if val else ""] if part).strip()
            if text:
                result.append(text)
            continue
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _fallback_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _manifest_count(value: Any) -> int:
    if not isinstance(value, list):
        return 0
    return len([item for item in value if isinstance(item, dict) and item.get("image_id")])
