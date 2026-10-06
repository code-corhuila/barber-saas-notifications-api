"""What the service offers for push delivery: register the caller's device."""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from notifications.domain.model.device_token import DeviceToken, Platform


@dataclass(frozen=True)
class Registration:
    device_token: DeviceToken
    created: bool


class DeviceTokenUseCases(Protocol):
    def register(self, user_id: UUID, token: str, platform: Platform, idempotency_key: str) -> Registration: ...
