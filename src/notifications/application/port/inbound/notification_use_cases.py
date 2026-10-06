"""What the service offers: the inbox of the caller (notification-service.yaml)."""
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar
from uuid import UUID

from notifications.domain.model.notification import Notification

T = TypeVar("T")


@dataclass(frozen=True)
class PageRequest:
    page: int
    limit: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int

    @property
    def total_pages(self) -> int:
        return -(-self.total // self.limit)


class NotificationUseCases(Protocol):
    def list_mine(self, user_id: UUID, read: bool | None, page: PageRequest) -> Page[Notification]: ...

    def mark_read(self, user_id: UUID, notification_id: UUID) -> Notification: ...
