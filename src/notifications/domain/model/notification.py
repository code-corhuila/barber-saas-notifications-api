"""The notification aggregate: one message of a user's inbox (06-data/models.md §7)."""
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from notifications.domain.model.errors import InvalidNotification

TITLE_MAX = 150
BODY_MAX = 500


class NotificationType(StrEnum):
    """Same values as the validator of the collection; PROMOTION is reserved."""

    APPOINTMENT_CONFIRMATION = "APPOINTMENT_CONFIRMATION"
    REMINDER = "REMINDER"
    PROMOTION = "PROMOTION"
    SYSTEM = "SYSTEM"


class DeliveryChannel(StrEnum):
    PUSH = "PUSH"
    EMAIL = "EMAIL"


class DeliveryStatus(StrEnum):
    SENT = "SENT"
    FAILED = "FAILED"


# The collection keeps the last ones only (deliveryAttempts maxItems 10, models.md §7).
MAX_DELIVERY_ATTEMPTS = 10


@dataclass(frozen=True)
class DeliveryAttempt:
    """One try to reach the user outside the app, embedded in its notification."""

    channel: DeliveryChannel
    status: DeliveryStatus
    attempted_at: datetime
    error_code: str | None = None


@dataclass(frozen=True)
class Notification:
    id: UUID
    user_id: UUID
    barbershop_id: UUID | None
    title: str
    body: str
    type: NotificationType
    read: bool
    source_event_id: UUID | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not 0 < len(self.title) <= TITLE_MAX:
            raise InvalidNotification(f"title must have 1 to {TITLE_MAX} characters")
        if not 0 < len(self.body) <= BODY_MAX:
            raise InvalidNotification(f"body must have 1 to {BODY_MAX} characters")

    def mark_read(self, now: datetime) -> "Notification":
        """Idempotent: an already read notification keeps the moment it was read."""
        if self.read:
            return self
        return replace(self, read=True, updated_at=now)
