"""Lightweight synchronous quality gate checks using PIL only.

Each check runs < 50ms per image. No external API calls.
"""
from __future__ import annotations

import io
import logging
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

MIN_IMAGE_EDGE = 1024
WHITE_BG_MEAN_THRESHOLD = 248
WHITE_BG_STD_THRESHOLD = 5
BLANK_STD_THRESHOLD = 3
ENTROPY_FLOOR = 2.5


def sync_quality_check(
    image_bytes: bytes,
    *,
    requires_white_bg: bool = False,
    min_edge: int = MIN_IMAGE_EDGE,
) -> dict[str, Any]:
    """Run fast PIL-based quality checks on a generated image.

    Returns:
        {"passed": bool, "checks": {name: bool, ...}, "failure_reason": str | None}
    """
    checks: dict[str, bool] = {}
    failure_reasons: list[str] = []

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img_array = np.array(img.convert("RGB"))
    except Exception as exc:
        logger.warning("quality_gate: failed to decode image: %s", exc)
        return {
            "passed": False,
            "checks": {"decodable": False},
            "failure_reason": "图片文件损坏，无法解码",
        }

    checks["decodable"] = True

    # --- Size check ---
    width, height = img.size
    checks["size_ok"] = bool(width >= min_edge and height >= min_edge)
    if not checks["size_ok"]:
        failure_reasons.append(f"图片尺寸不足 ({width}×{height}，要求 ≥ {min_edge}×{min_edge})")

    # --- Blank / all-black / all-white detection ---
    pixel_std = float(np.std(img_array))
    checks["not_blank"] = bool(pixel_std > BLANK_STD_THRESHOLD)
    if not checks["not_blank"]:
        pixel_mean = float(np.mean(img_array))
        if pixel_mean > 240:
            failure_reasons.append("图片几乎全白，疑似空白输出")
        elif pixel_mean < 15:
            failure_reasons.append("图片几乎全黑，疑似渲染失败")
        else:
            failure_reasons.append("图片信息量极低，疑似异常输出")

    # --- Entropy check (low information) ---
    gray = img.convert("L")
    histogram = gray.histogram()
    total_pixels = sum(histogram)
    if total_pixels > 0:
        probabilities = [count / total_pixels for count in histogram if count > 0]
        entropy = -sum(p * np.log2(p) for p in probabilities)
    else:
        entropy = 0.0
    checks["sufficient_entropy"] = bool(entropy > ENTROPY_FLOOR)
    if not checks["sufficient_entropy"] and checks["not_blank"]:
        failure_reasons.append("图片细节极少，可能为纯色块或渐变填充")

    # --- White background purity (only for white_bg slots) ---
    if requires_white_bg:
        checks["white_bg_pure"] = bool(_check_white_bg_purity(img_array))
        if not checks["white_bg_pure"]:
            failure_reasons.append("白底图背景不够纯白，边缘区域存在杂色")

    passed = bool(all(checks.values()))
    return {
        "passed": passed,
        "checks": checks,
        "failure_reason": failure_reasons[0] if failure_reasons else None,
        "entropy": round(entropy, 2),
        "pixel_std": round(pixel_std, 2),
        "width": width,
        "height": height,
    }


def _check_white_bg_purity(img_array: np.ndarray) -> bool:
    """Check that the image edges are close to pure white."""
    h, w = img_array.shape[:2]
    edge_width = max(int(min(h, w) * 0.05), 4)

    # Sample edges: top, bottom, left, right strips
    edges = np.concatenate([
        img_array[:edge_width, :, :].reshape(-1, 3),       # top
        img_array[-edge_width:, :, :].reshape(-1, 3),      # bottom
        img_array[:, :edge_width, :].reshape(-1, 3),       # left
        img_array[:, -edge_width:, :].reshape(-1, 3),      # right
    ], axis=0)

    edge_mean = float(np.mean(edges))
    edge_std = float(np.std(edges))

    return bool(edge_mean >= WHITE_BG_MEAN_THRESHOLD and edge_std <= WHITE_BG_STD_THRESHOLD)
