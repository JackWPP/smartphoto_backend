from __future__ import annotations

from typing import Any

from app.services.copy_resolution import (
    apply_parameter_snapshot_with_attribution,
    parameter_snapshot_to_copy_attribution as resolve_parameter_snapshot_to_copy_attribution,
    parameter_snapshot_to_copy_fields as resolve_parameter_snapshot_to_copy_fields,
    resolve_session_copy,
)


def merge_parameter_snapshot_into_copy(
    confirmed_copy: dict[str, Any],
    parameter_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    return resolve_session_copy(confirmed_copy, parameter_snapshot=parameter_snapshot)["copy"]


def parameter_snapshot_to_copy_fields(parameter_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return resolve_parameter_snapshot_to_copy_fields(parameter_snapshot)


def parameter_snapshot_to_copy_attribution(parameter_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return resolve_parameter_snapshot_to_copy_attribution(parameter_snapshot)


def apply_parameter_snapshot_to_copy(
    confirmed_copy: dict[str, Any] | None,
    parameter_snapshot: dict[str, Any] | None,
    *,
    overwrite: bool,
    protect_explicit_input: bool = True,
) -> dict[str, Any]:
    return apply_parameter_snapshot_with_attribution(
        confirmed_copy,
        parameter_snapshot,
        overwrite=overwrite,
        protect_explicit_input=protect_explicit_input,
    )
