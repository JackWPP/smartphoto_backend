from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from app.contracts.common import ContractModel

logger = logging.getLogger(__name__)


def validate_contract_warn(
    contract_cls: type[ContractModel],
    payload: dict[str, Any] | None,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_payload = payload or {}
    try:
        return contract_cls.from_dict(raw_payload).to_dict()
    except ValidationError as exc:
        logger.warning(
            "contract_validation_failed: contract=%s context=%s errors=%s",
            contract_cls.__name__,
            context or {},
            exc.errors(),
        )
        return raw_payload
