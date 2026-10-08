"""In-memory adapters: the service runs and is tested without MongoDB until infra-mongo exists."""
from datetime import datetime
from threading import Lock
from uuid import UUID

from notifications.application.port.outbound.device_token_repository import IdempotencyRecord
from notifications.domain.model.device_token import DeviceToken
from notifications.domain.model.notification import MAX_DELIVERY_ATTEMPTS, DeliveryAttempt, Notification


class InMemoryNotificationRepository:
    def __init__(self) -> None:
        self._by_id: dict[UUID, Notification] = {}
        self._attempts: dict[UUID, list[DeliveryAttempt]] = {}
        self._lock = Lock()

    def record_delivery(self, notification_id: UUID, attempt: DeliveryAttempt) -> None:
        with self._lock:
            attempts = [*self._attempts.get(notification_id, []), attempt]
            self._attempts[notification_id] = attempts[-MAX_DELIVERY_ATTEMPTS:]

    def attempts_of(self, notification_id: UUID) -> list[DeliveryAttempt]:
        return list(self._attempts.get(notification_id, []))

    def add(self, notification: Notification) -> None:
        with self._lock:
            self._by_id[notification.id] = notification

    def add_unless_seen(self, notification: Notification) -> bool:
        with self._lock:
            if any(n.source_event_id == notification.source_event_id for n in self._by_id.values()):
                return False
            self._by_id[notification.id] = notification
            return True

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


class InMemoryDeviceTokenRepository:
    def __init__(self) -> None:
        self._by_id: dict[UUID, DeviceToken] = {}
        self._keys: dict[tuple[str, str], IdempotencyRecord] = {}
        self._lock = Lock()

    def find_by_id(self, device_token_id: UUID) -> DeviceToken | None:
        return self._by_id.get(device_token_id)

    def find_by_token(self, token: str) -> DeviceToken | None:
        return next((d for d in self._by_id.values() if d.token == token), None)

    def key_record(self, key: str, operation: str) -> IdempotencyRecord | None:
        return self._keys.get((key, operation))

    def tokens_of(self, user_id: UUID) -> list[DeviceToken]:
        return [d for d in self._by_id.values() if d.user_id == user_id]

    def remove(self, device_token_id: UUID) -> None:
        with self._lock:
            self._by_id.pop(device_token_id, None)

    def save(self, device_token: DeviceToken, key: IdempotencyRecord) -> None:
        with self._lock:
            self._by_id[device_token.id] = device_token
            self._keys[(key.key, key.operation)] = key


class InMemoryProcessedEventRepository:
    def __init__(self) -> None:
        self._seen: dict[UUID, tuple[str, datetime]] = {}
        self._lock = Lock()

    def seen(self, event_id: UUID) -> bool:
        return event_id in self._seen

    def record(self, event_id: UUID, event_type: str, processed_at: datetime) -> None:
        with self._lock:
            self._seen.setdefault(event_id, (event_type, processed_at))
