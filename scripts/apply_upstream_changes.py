"""Apply safe text replacements to upstream.py."""
import pathlib

f = pathlib.Path('app/services/upstream.py')
content = f.read_text('utf-8')

changes = []

# 1. Add IMAGE_GENERATION_ALLOWED_ASPECT_RATIOS
old = "    CHAT_IMAGE_MAX_EDGE = 1024\n    CHAT_IMAGE_JPEG_QUALITY = 82\n    IMAGE_EDIT_ALLOWED_ASPECT_RATIOS = {"
new = """    CHAT_IMAGE_MAX_EDGE = 1024
    CHAT_IMAGE_JPEG_QUALITY = 82
    IMAGE_GENERATION_ALLOWED_ASPECT_RATIOS = {
        "1:1", "2:3", "3:2", "3:4", "4:3",
        "9:16", "16:9", "21:9", "9:21",
    }
    IMAGE_EDIT_ALLOWED_ASPECT_RATIOS = {"""
assert old in content, "Change 1: old string not found"
content = content.replace(old, new)
changes.append("1. IMAGE_GENERATION_ASPECT_RATIOS")

# 2. Add _build_image_generation_payload
old2 = "    def _submit_image_generation_task(self, payload: dict[str, Any], error_key: str) -> dict[str, Any]:"
new2 = """    def _build_image_generation_payload(
        self,
        prompt: str,
        size: str,
        aspect_ratio: str | None,
        reference_images: list[LoadedReferenceImage] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.whatai_image_model,
            "prompt": prompt,
        }
        normalized_ratio = str(aspect_ratio or "").strip()
        if normalized_ratio:
            payload["aspect_ratio"] = normalized_ratio
        else:
            payload["size"] = size or "1024x1024"
        if reference_images:
            payload["image"] = [
                self._optimized_data_uri(img) for img in reference_images[:8]
            ]
        return payload

    def _submit_image_generation_task(self, payload: dict[str, Any], error_key: str) -> dict[str, Any]:"""
assert old2 in content, "Change 2: old string not found"
content = content.replace(old2, new2)
changes.append("2. _build_image_generation_payload")

# 3. generate_image unified
old3 = """    def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        *,
        aspect_ratio: str | None = None,
        reference_images: list[LoadedReferenceImage] | None = None,
    ) -> bytes:
        if not self.settings.whatai_api_key:
            return self._fake_image(prompt)

        if reference_images:
            response_json = self._submit_image_edit(
                prompt,
                aspect_ratio,
                reference_images,
                "upstream_image_error",
            )
            upstream_endpoint = "/v1/images/edits"
        else:
            payload = {
                "model": self.settings.whatai_image_model,
                "prompt": prompt,
                "size": size,
            }
            response_json = self._submit_image_generation_task(payload, "upstream_image_error")
            upstream_endpoint = "/v1/images/generations"

        task_id = self._extract_image_task_id(response_json)
        data = self._poll_image_generation_task(task_id, "upstream_image_error") if task_id else self._extract_image_result(response_json)
        submission = {
            "task_id": task_id,
            "upstream_endpoint": upstream_endpoint,
            "result": None if task_id else data,
        }
        return self.download_image_bytes(submission, data, "upstream_image_error")"""
assert old3 in content, "Change 3: old string not found"
new3 = """    def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        *,
        aspect_ratio: str | None = None,
        reference_images: list[LoadedReferenceImage] | None = None,
    ) -> bytes:
        if not self.settings.whatai_api_key:
            return self._fake_image(prompt)

        payload = self._build_image_generation_payload(prompt, size, aspect_ratio, reference_images)
        response_json = self._submit_image_generation_task(payload, "upstream_image_error")
        task_id = self._extract_image_task_id(response_json)
        data = self._poll_image_generation_task(task_id, "upstream_image_error") if task_id else self._extract_image_result(response_json)
        submission = {
            "task_id": task_id,
            "upstream_endpoint": "/v1/images/generations",
            "result": None if task_id else data,
        }
        return self.download_image_bytes(submission, data, "upstream_image_error")"""
content = content.replace(old3, new3)
changes.append("3. generate_image")

# 4. submit_image_request unified
old4 = """    def submit_image_request(
        self,
        *,
        prompt: str,
        size: str = "1024x1024",
        aspect_ratio: str | None = None,
        reference_images: list[LoadedReferenceImage] | None = None,
        error_key: str = "upstream_image_error",
    ) -> dict[str, Any]:
        if not self.settings.whatai_api_key:
            return {
                "submission_id": None,
                "task_id": None,
                "prompt": prompt,
                "size": size,
                "aspect_ratio": aspect_ratio,
                "reference_images": reference_images or [],
                "upstream_endpoint": "/local/fake-image",
                "result": {"fake_bytes": self._fake_image(prompt)},
            }

        if reference_images:
            response_json = self._submit_image_edit(
                prompt,
                aspect_ratio,
                reference_images,
                error_key,
            )
            upstream_endpoint = "/v1/images/edits"
        else:
            payload = {
                "model": self.settings.whatai_image_model,
                "prompt": prompt,
                "size": size,
            }
            response_json = self._submit_image_generation_task(payload, error_key)
            upstream_endpoint = "/v1/images/generations"

        task_id = self._extract_image_task_id(response_json)
        result = self._extract_image_result(response_json) if not task_id else None
        return {
            "submission_id": None,
            "task_id": task_id,
            "prompt": prompt,
            "size": size,
            "aspect_ratio": aspect_ratio,
            "reference_images": reference_images or [],
            "upstream_endpoint": upstream_endpoint,
            "submitted_response": response_json,
            "result": result,
        }"""
assert old4 in content, "Change 4: old string not found"
new4 = """    def submit_image_request(
        self,
        *,
        prompt: str,
        size: str = "1024x1024",
        aspect_ratio: str | None = None,
        reference_images: list[LoadedReferenceImage] | None = None,
        error_key: str = "upstream_image_error",
    ) -> dict[str, Any]:
        if not self.settings.whatai_api_key:
            return {
                "submission_id": None,
                "task_id": None,
                "prompt": prompt,
                "size": size,
                "aspect_ratio": aspect_ratio,
                "reference_images": reference_images or [],
                "upstream_endpoint": "/local/fake-image",
                "result": {"fake_bytes": self._fake_image(prompt)},
            }

        payload = self._build_image_generation_payload(prompt, size, aspect_ratio, reference_images)
        response_json = self._submit_image_generation_task(payload, error_key)
        task_id = self._extract_image_task_id(response_json)
        result = self._extract_image_result(response_json) if not task_id else None
        return {
            "submission_id": None,
            "task_id": task_id,
            "prompt": prompt,
            "size": size,
            "aspect_ratio": aspect_ratio,
            "reference_images": reference_images or [],
            "upstream_endpoint": "/v1/images/generations",
            "submitted_response": response_json,
            "result": result,
        }"""
content = content.replace(old4, new4)
changes.append("4. submit_image_request")

# 5. Add import
old5 = "from app.services.copy_normalization import"
new5 = "from app.services.category_prompt_helpers import build_category_kb_section, build_completion_kb_section, build_copy_design_kb_section\nfrom app.services.copy_normalization import"
assert old5 in content, "Change 5: old string not found"
content = content.replace(old5, new5)
changes.append("5. Import")

# 6. extract_parameters - param + kb_section
old6 = "        file_attachments: list[dict[str, Any]],\n    ) -> dict[str, Any]:\n        fallback = self._fake_parameter_snapshot("
new6 = "        file_attachments: list[dict[str, Any]],\n        category_parameter_rules: dict[str, Any] | None = None,\n    ) -> dict[str, Any]:\n        fallback = self._fake_parameter_snapshot("
assert old6 in content, "Change 6a: old string not found"
content = content.replace(old6, new6)
changes.append("6a. extract_parameters param")

old6b = '"你是 SmartPhoto 的 Step3 商品信息策划 Agent。"'
new6b = '"你是 SmartPhoto 的 Step3 商品参数推理 Agent。"'
assert old6b in content, "Change 6b: old string not found"
content = content.replace(old6b, new6b)
changes.append("6b. agent title")

old6c = '"请只返回 JSON 对象，不要输出解释性段落。"'
new6c = 'f"{build_category_kb_section(analysis_snapshot, category_parameter_rules)}"\n                    "请只返回 JSON 对象。"'
assert old6c in content, "Change 6c: old string not found"
content = content.replace(old6c, new6c)
changes.append("6c. kb_section")

# 7. complete_parameters - param + kb_section
old7 = "        completion_instruction: str | None = None,\n    ) -> dict[str, Any]:\n        base_snapshot = self._normalize_completed_parameter_snapshot(parameter_snapshot)"
new7 = "        completion_instruction: str | None = None,\n        category_parameter_rules: dict[str, Any] | None = None,\n    ) -> dict[str, Any]:\n        base_snapshot = self._normalize_completed_parameter_snapshot(parameter_snapshot)"
assert old7 in content, "Change 7a: old string not found"
content = content.replace(old7, new7)
changes.append("7a. complete_parameters param")

old7b = '"你是 SmartPhoto 的 Step3 参数补全 Agent。"'
new7b = '"你是 SmartPhoto 的 Step3 参数补全 Agent。"\n                    f"{build_completion_kb_section(analysis_snapshot, category_parameter_rules)}"'
assert old7b in content, "Change 7b: old string not found"
content = content.replace(old7b, new7b)
changes.append("7b. completion kb")

old7c = '"补全必须严格基于已识别到的商品结构、analysis 与首轮 parameter_snapshot，不能凭空杜撰危险事实。"'
new7c = '"补全时请结合品类背景知识：补充那些图中不可见但消费者决策至关重要的参数维度。不要编造具体数值，用典型范围或描述性语言表达。若缺乏依据，请返回 no_change。"'
assert old7c in content, "Change 7c: old string not found"
content = content.replace(old7c, new7c)
changes.append("7c. completion requirements")

# 8. design_main_copy_blocks - param + kb_section
old8 = "        prompt_plan: list[dict[str, Any]],\n    ) -> dict[str, dict[str, Any]]:\n        if not self.llm_router.is_available(\"main_copy_design\"):"
new8 = "        prompt_plan: list[dict[str, Any]],\n        category_parameter_rules: dict[str, Any] | None = None,\n    ) -> dict[str, dict[str, Any]]:\n        if not self.llm_router.is_available(\"main_copy_design\"):"
assert old8 in content, "Change 8a: old string not found"
content = content.replace(old8, new8)
changes.append("8a. design_main_copy_blocks param")

old8b = '"你是 SmartPhoto 的主图文字设计 Agent。"'
new8b = '"你是 SmartPhoto 的主图文字设计 Agent。"\n                    f"{build_copy_design_kb_section(analysis_snapshot, category_parameter_rules)}"'
assert old8b in content, "Change 8b: old string not found"
content = content.replace(old8b, new8b)
changes.append("8b. copy_design kb")

f.write_text(content, 'utf-8')
for c in changes:
    print(c)
print("ALL DONE - %d changes applied" % len(changes))
