"""Receive one domain event: at most one notification per event id (ADR-016, at-least-once)."""
import logging

from notifications.application.port.inbound.event_use_cases import EventOutcome, IncomingEvent
from notifications.application.port.outbound.clock import Clock
from notifications.application.port.outbound.email_sender import EmailSender
from notifications.application.port.outbound.ids import IdGenerator
from notifications.application.port.outbound.notification_repository import NotificationRepository
from notifications.application.port.outbound.processed_event_repository import ProcessedEventRepository
from notifications.application.usecase.push_delivery import NoPush, PushDelivery
from notifications.domain.model import password_reset
from notifications.domain.model.errors import DeliveryUnavailable
from notifications.domain.model.event_notice import notice_for
from notifications.domain.model.notification import Notification

log = logging.getLogger(__name__)


class EventService:
    def __init__(self, notifications: NotificationRepository, clock: Clock, ids: IdGenerator,
                 push: PushDelivery | NoPush | None = None, *, processed: ProcessedEventRepository | None = None,
                 email: EmailSender | None = None) -> None:
        self._notifications = notifications
        self._clock = clock
        self._ids = ids
        self._push = push or NoPush()
        self._processed = processed
        self._email = email

    def receive(self, event: IncomingEvent) -> EventOutcome:
        if event.type == password_reset.EVENT_TYPE:
            return self._send_reset_code(event)
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

    def _send_reset_code(self, event: IncomingEvent) -> EventOutcome:
        """DEC-NOTIF-01: e-mail only, no inbox notification, and only the event id is kept.

        Sent first and recorded after: a failed send is not recorded, so the worker's retry sends it
        (a lost code locks the user out). Once sent, the event is done even if recording it fails:
        answering 503 then would resend the code on every retry. So a code is sent twice only when
        the worker redelivers an event it already got an answer for, never in a loop.
        """
        mail = password_reset.reset_email(event.payload)
        if self._email is None or self._processed is None:
            raise DeliveryUnavailable("no mail server is configured")
        if self._processed.seen(event.id):
            return EventOutcome.DUPLICATE
        try:
            self._email.send(mail.to, mail.subject, mail.body)
        except Exception as error:  # the mail server is down or refused it: the worker retries
            log.warning("password-reset e-mail not sent: %s", type(error).__name__)
            raise DeliveryUnavailable("the mail server did not accept the message") from None
        try:
            self._processed.record(event.id, event.type, self._clock.now())
        except Exception as error:  # the e-mail is out: a retry would only resend it
            log.warning("password-reset e-mail sent but not recorded: %s", type(error).__name__)
        return EventOutcome.PROCESSED
