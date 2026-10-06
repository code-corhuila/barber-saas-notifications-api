"""In-memory adapters: the service runs and is tested without MongoDB until infra-mongo exists."""
from threading import Lock
from uuid import UUID

from notifications.domain.model.notification import Notification


class InMemoryNotificationRepository:
    def __init__(self) -> None:
        self._by_id: dict[UUID, Notification] = {}
        self._lock = Lock()

    def add(self, notification: Notification) -> None:
        with self._lock:
            self._by_id[notification.id] = notification

    def save(self, notification: Notification) -> None:
        with self._lock:
            self._by_id[notification.id] = notification

    def find(self, user_id: UUID, notification_id: UUID) -> Notification | None:
        found = self._by_id.get(notification_id)
        return found if found is not None and found.user_id == user_id else None

    def page_of(self, user_id: UUID, read: bool | None, offset: int, limit: int) -> tuple[list[Notification], int]:
        with self._lock:
            mine = [n for n in self._by_id.values()
                    if n.user_id == user_id and (read is None or n.read == read)]
        # Stable order: most recent first, the id breaks ties (norm 5.3.6).
        mine.sort(key=lambda n: (n.created_at, str(n.id)), reverse=True)
        return mine[offset:offset + limit], len(mine)
