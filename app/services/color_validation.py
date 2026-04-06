"""Color fidelity validation using PIL + numpy.

Extracts dominant colors from generated images and compares against
the expected color palette from the truth_contract. Uses CIE76 Delta-E
in CIELAB color space for perceptual color distance.

All checks run < 200ms per image. No external API calls.
"""
from __future__ import annotations

import io
import logging
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_DELTA_E_TOLERANCE = 25.0
DEFAULT_N_CLUSTERS = 5
MAX_PIXELS_FOR_CLUSTERING = 50000


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' or 'RRGGBB' to (R, G, B)."""
    h = hex_color.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_lab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Convert sRGB (0-255) to CIELAB via XYZ. D65 illuminant."""
    # sRGB → linear
    def linearize(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    rl, gl, bl = linearize(r), linearize(g), linearize(b)

    # linear RGB → XYZ (D65)
    x = rl * 0.4124564 + gl * 0.3575761 + bl * 0.1804375
    y = rl * 0.2126729 + gl * 0.7151522 + bl * 0.0721750
    z = rl * 0.0193339 + gl * 0.1191920 + bl * 0.9503041

    # XYZ → Lab
    xn, yn, zn = 0.95047, 1.0, 1.08883

    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b_val = 200.0 * (fy - fz)
    return L, a, b_val


def delta_e_cie76(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """CIE76 color distance between two CIELAB colors."""
    return float(np.sqrt(sum((a - b) ** 2 for a, b in zip(lab1, lab2))))


def extract_dominant_colors(
    image_bytes: bytes,
    n_clusters: int = DEFAULT_N_CLUSTERS,
) -> list[tuple[int, int, int]]:
    """Extract dominant colors using simplified k-means clustering.

    Returns list of (R, G, B) tuples sorted by cluster size (largest first).
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return []

    # Downsample for performance
    pixels = np.array(img).reshape(-1, 3).astype(np.float64)
    if len(pixels) > MAX_PIXELS_FOR_CLUSTERING:
        indices = np.random.default_rng(42).choice(len(pixels), MAX_PIXELS_FOR_CLUSTERING, replace=False)
        pixels = pixels[indices]

    if len(pixels) == 0:
        return []

    # Simple k-means (no sklearn dependency)
    n_clusters = min(n_clusters, len(pixels))
    rng = np.random.default_rng(42)
    centers = pixels[rng.choice(len(pixels), n_clusters, replace=False)].copy()

    for _ in range(15):
        # Assign pixels to nearest center
        dists = np.linalg.norm(pixels[:, np.newaxis, :] - centers[np.newaxis, :, :], axis=2)
        labels = np.argmin(dists, axis=1)
        # Update centers
        new_centers = np.zeros_like(centers)
        for k in range(n_clusters):
            mask = labels == k
            if mask.any():
                new_centers[k] = pixels[mask].mean(axis=0)
            else:
                new_centers[k] = centers[k]
        if np.allclose(centers, new_centers, atol=1.0):
            break
        centers = new_centers

    # Sort by cluster size
    labels = np.argmin(
        np.linalg.norm(pixels[:, np.newaxis, :] - centers[np.newaxis, :, :], axis=2),
        axis=1,
    )
    counts = np.bincount(labels, minlength=n_clusters)
    order = np.argsort(-counts)

    return [
        (int(round(centers[i][0])), int(round(centers[i][1])), int(round(centers[i][2])))
        for i in order
        if counts[i] > 0
    ]


def validate_color_fidelity(
    image_bytes: bytes,
    expected_hex_palette: list[str],
    *,
    tolerance: float = DEFAULT_DELTA_E_TOLERANCE,
    n_clusters: int = DEFAULT_N_CLUSTERS,
) -> dict[str, Any]:
    """Validate that generated image colors match the expected palette.

    For each expected color, finds the closest dominant color in the image
    and reports whether the distance exceeds the tolerance.

    Returns:
        {
            "passed": bool,
            "dominant_colors_rgb": list[tuple[int,int,int]],
            "max_delta_e": float,
            "mean_delta_e": float,
            "violations": [{"expected_hex": str, "closest_rgb": tuple, "delta_e": float}, ...],
        }
    """
    if not expected_hex_palette:
        return {"passed": True, "dominant_colors_rgb": [], "max_delta_e": 0.0, "mean_delta_e": 0.0, "violations": [], "skipped": "no_expected_palette"}

    # Parse expected colors
    expected_labs: list[tuple[str, tuple[float, float, float]]] = []
    for hex_color in expected_hex_palette:
        try:
            r, g, b = _hex_to_rgb(hex_color)
            expected_labs.append((hex_color, _rgb_to_lab(r, g, b)))
        except (ValueError, TypeError):
            continue

    if not expected_labs:
        return {"passed": True, "dominant_colors_rgb": [], "max_delta_e": 0.0, "mean_delta_e": 0.0, "violations": [], "skipped": "invalid_hex_palette"}

    dominant = extract_dominant_colors(image_bytes, n_clusters=n_clusters)
    if not dominant:
        return {"passed": False, "dominant_colors_rgb": [], "max_delta_e": 999.0, "mean_delta_e": 999.0, "violations": [], "error": "failed_to_extract_colors"}

    dominant_labs = [_rgb_to_lab(r, g, b) for r, g, b in dominant]

    violations: list[dict[str, Any]] = []
    delta_es: list[float] = []

    for hex_color, expected_lab in expected_labs:
        # Find closest dominant color
        min_de = float("inf")
        closest_rgb = dominant[0]
        for i, dom_lab in enumerate(dominant_labs):
            de = delta_e_cie76(expected_lab, dom_lab)
            if de < min_de:
                min_de = de
                closest_rgb = dominant[i]
        delta_es.append(min_de)
        if min_de > tolerance:
            violations.append({
                "expected_hex": hex_color,
                "closest_rgb": closest_rgb,
                "delta_e": round(min_de, 2),
            })

    max_de = max(delta_es) if delta_es else 0.0
    mean_de = float(np.mean(delta_es)) if delta_es else 0.0

    return {
        "passed": len(violations) == 0,
        "dominant_colors_rgb": dominant[:n_clusters],
        "max_delta_e": round(max_de, 2),
        "mean_delta_e": round(mean_de, 2),
        "violations": violations,
    }


def build_color_escalation_instruction(violations: list[dict[str, Any]]) -> str:
    """Build a constraint escalation instruction from color violations.

    Used when async quality retry detects color drift — produces a targeted
    instruction to feed back into the generation prompt.
    """
    if not violations:
        return ""
    parts = ["产品主体颜色偏差严重，必须精确还原以下颜色："]
    for v in violations[:3]:
        hex_color = v.get("expected_hex", "")
        de = v.get("delta_e", 0)
        parts.append(f"  - {hex_color}（当前偏差 Delta-E={de}，需要纠正）")
    parts.append("请严格参照参考图中的产品颜色，不要自行调色、美化或偏暖偏冷。")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Image similarity metrics (observation only, not pass/fail)
# ---------------------------------------------------------------------------

SSIM_RESIZE_EDGE = 256


def compute_ssim(image_bytes_a: bytes, image_bytes_b: bytes) -> float:
    """Compute simplified SSIM between two images.

    Returns a value in [0, 1] where 1 = identical.
    Both images are resized to SSIM_RESIZE_EDGE for performance.
    """
    try:
        img_a = Image.open(io.BytesIO(image_bytes_a)).convert("L").resize((SSIM_RESIZE_EDGE, SSIM_RESIZE_EDGE))
        img_b = Image.open(io.BytesIO(image_bytes_b)).convert("L").resize((SSIM_RESIZE_EDGE, SSIM_RESIZE_EDGE))
    except Exception:
        return 0.0

    a = np.array(img_a, dtype=np.float64)
    b = np.array(img_b, dtype=np.float64)

    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    mu_a = a.mean()
    mu_b = b.mean()
    sigma_a_sq = a.var()
    sigma_b_sq = b.var()
    sigma_ab = ((a - mu_a) * (b - mu_b)).mean()

    numerator = (2 * mu_a * mu_b + C1) * (2 * sigma_ab + C2)
    denominator = (mu_a ** 2 + mu_b ** 2 + C1) * (sigma_a_sq + sigma_b_sq + C2)

    return float(numerator / denominator) if denominator > 0 else 0.0


def compute_histogram_correlation(image_bytes_a: bytes, image_bytes_b: bytes) -> float:
    """Compute histogram correlation between two images.

    Returns a value in [-1, 1] where 1 = identical histogram distribution.
    """
    try:
        img_a = Image.open(io.BytesIO(image_bytes_a)).convert("RGB").resize((SSIM_RESIZE_EDGE, SSIM_RESIZE_EDGE))
        img_b = Image.open(io.BytesIO(image_bytes_b)).convert("RGB").resize((SSIM_RESIZE_EDGE, SSIM_RESIZE_EDGE))
    except Exception:
        return 0.0

    hist_a = np.array(img_a.histogram(), dtype=np.float64)
    hist_b = np.array(img_b.histogram(), dtype=np.float64)

    # Normalize
    ha = hist_a - hist_a.mean()
    hb = hist_b - hist_b.mean()

    denom = np.sqrt((ha ** 2).sum() * (hb ** 2).sum())
    if denom < 1e-10:
        return 0.0
    return float((ha * hb).sum() / denom)


def compute_image_similarity(
    generated_bytes: bytes,
    reference_bytes: bytes,
) -> dict[str, Any]:
    """Compute similarity metrics between generated and reference images.

    Returns observation-only metrics (no pass/fail judgment).
    """
    ssim = compute_ssim(generated_bytes, reference_bytes)
    hist_corr = compute_histogram_correlation(generated_bytes, reference_bytes)
    return {
        "ssim": round(ssim, 4),
        "histogram_correlation": round(hist_corr, 4),
    }
