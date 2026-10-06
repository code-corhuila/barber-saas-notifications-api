"""What the service needs to keep device tokens and the idempotency keys that created them."""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from notifications.domain.model.device_token import DeviceToken


@dataclass(frozen=True)
class IdempotencyRecord:
    """06-data/models.md §10: the key, the operation, the resource it produced and the request hash."""

    key: str
    operation: str
    resource_id: UUID
    request_hash: str


class DeviceTokenRepository(Protocol):
    def find_by_id(self, device_token_id: UUID) -> DeviceToken | None: ...

    def find_by_token(self, token: str) -> DeviceToken | None: ...

    def key_record(self, key: str, operation: str) -> IdempotencyRecord | None: ...

    def save(self, device_token: DeviceToken, key: IdempotencyRecord) -> None:
        """The device token and its key in one transaction (norm 5.3.8)."""
        ...
