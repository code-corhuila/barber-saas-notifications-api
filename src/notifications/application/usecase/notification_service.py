"""The inbox use cases. The user always comes from the validated token, never from the request."""
from uuid import UUID

from notifications.application.port.inbound.notification_use_cases import Page, PageRequest
from notifications.application.port.outbound.clock import Clock
from notifications.application.port.outbound.notification_repository import NotificationRepository
from notifications.domain.model.errors import NotificationNotFound
from notifications.domain.model.notification import Notification


class NotificationService:
    def __init__(self, notifications: NotificationRepository, clock: Clock) -> None:
        self._notifications = notifications
        self._clock = clock

    def list_mine(self, user_id: UUID, read: bool | None, page: PageRequest) -> Page[Notification]:
        items, total = self._notifications.page_of(user_id, read, page.offset, page.limit)
        return Page(items=items, total=total, page=page.page, limit=page.limit)

    def mark_read(self, user_id: UUID, notification_id: UUID) -> Notification:
        current = self._notifications.find(user_id, notification_id)
        if current is None:
            raise NotificationNotFound(str(notification_id))
        marked = current.mark_read(self._clock.now())
        if marked is not current:
            self._notifications.save(marked)
        return marked
