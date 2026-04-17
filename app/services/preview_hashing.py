from __future__ import annotations

import hashlib
import json
from typing import Any

PREVIEW_HASH_POLICY_VERSION = "preview_hash_layers_v1"


def stable_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def sort_dicts(items: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    def _sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(item.get(key) for key in keys)

    return sorted(items, key=_sort_key)


def normalize_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return sorted(dict.fromkeys(normalized))


def normalize_manifest_item(
    item: dict[str, Any],
    *,
    include_slot_type: bool = True,
) -> dict[str, Any]:
    normalized = {
        "image_id": str(item.get("image_id") or ""),
        "display_order": int(item.get("display_order") or 0),
    }
    if include_slot_type:
        normalized["slot_type"] = str(item.get("slot_type") or "")
    return normalized


def build_hash_layers(
    *,
    stage: str,
    config_payload: dict[str, Any],
    content_payload: dict[str, Any],
    reference_payload: dict[str, Any],
) -> dict[str, Any]:
    versioned_config = {
        "hash_policy_version": PREVIEW_HASH_POLICY_VERSION,
        "stage": stage,
        **config_payload,
    }
    versioned_content = {
        "hash_policy_version": PREVIEW_HASH_POLICY_VERSION,
        "stage": stage,
        **content_payload,
    }
    versioned_reference = {
        "hash_policy_version": PREVIEW_HASH_POLICY_VERSION,
        "stage": stage,
        **reference_payload,
    }
    config_hash = stable_hash(versioned_config)
    content_hash = stable_hash(versioned_content)
    reference_hash = stable_hash(versioned_reference)
    aggregate_hash = stable_hash(
        {
            "hash_policy_version": PREVIEW_HASH_POLICY_VERSION,
            "stage": stage,
            "config_hash": config_hash,
            "content_hash": content_hash,
            "reference_hash": reference_hash,
        }
    )
    return {
        "hash_policy_version": PREVIEW_HASH_POLICY_VERSION,
        "hash_layers": {
            "config_hash": config_hash,
            "content_hash": content_hash,
            "reference_hash": reference_hash,
        },
        "input_hash": aggregate_hash,
    }
