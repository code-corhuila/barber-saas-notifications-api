"""What the service needs to keep notifications. Every read is filtered by the user."""
from typing import Protocol
from uuid import UUID

from notifications.domain.model.notification import Notification


class NotificationRepository(Protocol):
    def add(self, notification: Notification) -> None: ...

    def save(self, notification: Notification) -> None: ...

    def find(self, user_id: UUID, notification_id: UUID) -> Notification | None: ...

    def page_of(self, user_id: UUID, read: bool | None, offset: int, limit: int) -> tuple[list[Notification], int]:
        """The user's notifications, most recent first, and how many match in total."""
        ...
