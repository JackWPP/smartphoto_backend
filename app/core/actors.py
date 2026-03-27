from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RequestActor:
    kind: Literal["user", "guest"]
    user_id: str | None = None
    guest_id: str | None = None

    @property
    def auth_mode(self) -> str:
        return self.kind

    @property
    def owner_label(self) -> str:
        return self.user_id if self.kind == "user" else f"guest:{self.guest_id}"

    @property
    def owner_kind(self) -> str:
        return self.kind

    @property
    def owner_id(self) -> str:
        return self.user_id if self.kind == "user" else str(self.guest_id)

    @property
    def prompt_owner_id(self) -> str:
        # Guests should only see system presets; passing an empty user_id keeps the existing visibility filter.
        return self.user_id or ""

    @property
    def can_download(self) -> bool:
        return self.kind == "user"

    @property
    def can_continue_editing(self) -> bool:
        return True


@dataclass(frozen=True)
class ServicePrincipal:
    app_id: str

    @property
    def owner_label(self) -> str:
        return self.app_id
