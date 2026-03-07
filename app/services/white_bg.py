import io
from collections import deque
from typing import Any

from PIL import Image


def validate_white_background(image_bytes: bytes) -> tuple[bool, dict[str, Any]]:
    with Image.open(io.BytesIO(image_bytes)) as image:
        rgb = image.convert("RGB")
        rgb.thumbnail((256, 256))
        width, height = rgb.size
        pixels = [rgb.getpixel((x, y)) for y in range(height) for x in range(width)]

    white_threshold = 242
    non_white = [
        0
        if (pixel[0] >= white_threshold and pixel[1] >= white_threshold and pixel[2] >= white_threshold)
        else 1
        for pixel in pixels
    ]
    edge_indexes = _edge_indexes(width, height, margin=max(4, min(width, height) // 20))
    outer_band_indexes = _outer_band_indexes(width, height, margin=max(8, min(width, height) // 12))

    edge_white_ratio = 1.0 - (sum(non_white[index] for index in edge_indexes) / max(len(edge_indexes), 1))
    outer_band_white_ratio = 1.0 - (
        sum(non_white[index] for index in outer_band_indexes) / max(len(outer_band_indexes), 1)
    )
    major_components = _count_major_components(non_white, width, height, min_pixels=max(120, (width * height) // 120))

    diagnostics = {
        "edge_white_ratio": round(edge_white_ratio, 4),
        "outer_band_white_ratio": round(outer_band_white_ratio, 4),
        "major_components": major_components,
        "passed": False,
    }

    passed = edge_white_ratio >= 0.97 and outer_band_white_ratio >= 0.94 and major_components <= 1
    diagnostics["passed"] = passed
    return passed, diagnostics


def strengthen_white_bg_instruction() -> str:
    return (
        "严格输出单产品标准电商白底图：纯白无缝背景，主体完整居中，边缘干净，"
        "不要任何人物、手模、道具、场景、文字、水印、边框或阴影脏污。"
    )


def _edge_indexes(width: int, height: int, margin: int) -> list[int]:
    indexes: list[int] = []
    for y in range(height):
        for x in range(width):
            if x < margin or x >= width - margin or y < margin or y >= height - margin:
                indexes.append((y * width) + x)
    return indexes


def _outer_band_indexes(width: int, height: int, margin: int) -> list[int]:
    indexes: list[int] = []
    inner_left = margin
    inner_right = width - margin
    inner_top = margin
    inner_bottom = height - margin
    for y in range(height):
        for x in range(width):
            if inner_left <= x < inner_right and inner_top <= y < inner_bottom:
                continue
            indexes.append((y * width) + x)
    return indexes


def _count_major_components(mask: list[int], width: int, height: int, min_pixels: int) -> int:
    visited = [False] * len(mask)
    component_count = 0
    for idx, value in enumerate(mask):
        if value == 0 or visited[idx]:
            continue
        component_size = _flood_fill(mask, visited, width, height, idx)
        if component_size >= min_pixels:
            component_count += 1
    return component_count


def _flood_fill(mask: list[int], visited: list[bool], width: int, height: int, start: int) -> int:
    queue: deque[int] = deque([start])
    visited[start] = True
    size = 0

    while queue:
        current = queue.popleft()
        size += 1
        x = current % width
        y = current // width
        neighbors = (
            (x - 1, y),
            (x + 1, y),
            (x, y - 1),
            (x, y + 1),
        )
        for nx, ny in neighbors:
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            neighbor_idx = (ny * width) + nx
            if visited[neighbor_idx] or mask[neighbor_idx] == 0:
                continue
            visited[neighbor_idx] = True
            queue.append(neighbor_idx)

    return size
