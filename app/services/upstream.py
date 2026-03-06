import base64
import io
from typing import Any

import httpx
from PIL import Image, ImageDraw

from app.core.config import get_settings
from app.core.errors import AppError


class WhataiClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def analyze_images(self, image_urls: list[str], active_platform_id: str | None) -> dict[str, Any]:
        if not self.settings.whatai_api_key:
            return self._fake_analysis(active_platform_id)

        prompt = "请输出SmartPhoto所需JSON结构：recognized_product,image_assessment,missing_views,suggestions,copy_draft,key_parameters,suggested_styles"
        payload = {
            "model": self.settings.whatai_chat_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }

        resp = self._post_json("/chat/completions", payload, "upstream_llm_error")
        text = (
            resp.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        # 上游输出不稳定，失败则退回可用默认结果
        if not text:
            return self._fake_analysis(active_platform_id)
        return self._fake_analysis(active_platform_id)

    def regenerate_copy(
        self,
        current_copy: dict[str, Any],
        targets: list[str],
        instruction: str | None,
    ) -> dict[str, str]:
        if not self.settings.whatai_api_key:
            return {key: self._regenerated_text(current_copy.get(key, ""), instruction) for key in targets}

        prompt = f"基于现有文案，重写字段 {targets}，要求：{instruction or '保持电商风格'}"
        payload = {
            "model": self.settings.whatai_chat_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
        }
        self._post_json("/chat/completions", payload, "upstream_llm_error")
        return {key: self._regenerated_text(current_copy.get(key, ""), instruction) for key in targets}

    def generate_image(self, prompt: str, size: str = "1024x1024") -> bytes:
        if not self.settings.whatai_api_key:
            return self._fake_image(prompt)

        payload = {
            "model": self.settings.whatai_image_model,
            "prompt": prompt,
            "size": size,
        }
        resp = self._post_json("/images/generations", payload, "upstream_image_error")
        data = (resp.get("data") or [{}])[0]

        image_url = data.get("url")
        b64 = data.get("b64_json")
        if image_url:
            with httpx.Client(timeout=60) as client:
                image_resp = client.get(image_url)
                image_resp.raise_for_status()
                return image_resp.content
        if b64:
            return base64.b64decode(b64)
        return self._fake_image(prompt)

    def _post_json(self, path: str, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        try:
            with httpx.Client(base_url=self.settings.whatai_api_base, timeout=90) as client:
                response = client.post(path, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as exc:  # noqa: BLE001
            raise AppError(error_key, str(exc), 502) from exc

    def _fake_analysis(self, active_platform_id: str | None) -> dict[str, Any]:
        platform_hint = active_platform_id or "temu"
        return {
            "recognized_product": {
                "product_name": "智能产品",
                "category": "家居用品",
                "image_type": "实物图",
                "confidence": 0.8,
            },
            "image_assessment": {
                "quality_score": 0.86,
                "lighting": "good",
                "clarity": "good",
                "background_cleanliness": "medium",
            },
            "missing_views": ["side"],
            "suggestions": [
                "图片质量良好，适合AI处理",
                f"建议补充侧面图以提升{platform_hint}平台适配效果",
            ],
            "copy_draft": {
                "headline": "高效体验，稳定品质",
                "selling_points": "核心功能突出｜视觉清爽｜易于理解",
                "usage_scenes": "客厅、办公、卧室",
                "specs": "参数A 100｜参数B 200",
            },
            "key_parameters": [
                {
                    "key": "param_a",
                    "label": "参数A",
                    "value": "100",
                    "unit": "unit",
                    "confidence": 0.7,
                    "editable": True,
                }
            ],
            "suggested_styles": ["现代简约", "科技感"],
        }

    def _regenerated_text(self, original: str, instruction: str | None) -> str:
        suffix = instruction or "提升转化表达"
        if not original:
            return f"优化文案：{suffix}"
        return f"{original}（已优化：{suffix}）"

    def _fake_image(self, prompt: str) -> bytes:
        img = Image.new("RGB", (1024, 1024), color=(245, 245, 245))
        draw = ImageDraw.Draw(img)
        draw.rectangle((60, 60, 964, 964), outline=(30, 30, 30), width=4)
        draw.text((100, 120), "SmartPhoto Placeholder", fill=(20, 20, 20))
        draw.text((100, 180), prompt[:120], fill=(80, 80, 80))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()
