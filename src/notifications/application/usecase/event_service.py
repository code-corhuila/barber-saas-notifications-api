"""Receive one domain event: at most one notification per event id (ADR-016, at-least-once)."""
from notifications.application.port.inbound.event_use_cases import EventOutcome, IncomingEvent
from notifications.application.port.outbound.clock import Clock
from notifications.application.port.outbound.ids import IdGenerator
from notifications.application.port.outbound.notification_repository import NotificationRepository
from notifications.application.usecase.push_delivery import NoPush, PushDelivery
from notifications.domain.model.event_notice import notice_for
from notifications.domain.model.notification import Notification


class EventService:
    def __init__(self, notifications: NotificationRepository, clock: Clock, ids: IdGenerator,
                 push: PushDelivery | NoPush | None = None) -> None:
        self._notifications = notifications
        self._clock = clock
        self._ids = ids
        self._push = push or NoPush()

    def receive(self, event: IncomingEvent) -> EventOutcome:
        notice = notice_for(event.type, event.payload)
        if notice is None:
            return EventOutcome.IGNORED
        now = self._clock.now()
        notification = Notification(id=self._ids.next(), user_id=notice.recipient, barbershop_id=event.barbershop_id,
                                    title=notice.title, body=notice.body, type=notice.type, read=False,
                                    source_event_id=event.id, created_at=now, updated_at=now)
        if not self._notifications.add_unless_seen(notification):
            return EventOutcome.DUPLICATE
        # Only a new notification is pushed: a redelivered event never buzzes the phone twice.
        self._push.deliver(notification)
        return EventOutcome.PROCESSED
