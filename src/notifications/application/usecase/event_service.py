"""Receive one domain event: at most one notification per event id (ADR-016, at-least-once)."""
import logging
from dataclasses import replace

from notifications.application.port.inbound.event_use_cases import EventOutcome, IncomingEvent
from notifications.application.port.outbound.clock import Clock
from notifications.application.port.outbound.contact_directory import ContactDirectory
from notifications.application.port.outbound.email_sender import EmailSender
from notifications.application.port.outbound.ids import IdGenerator
from notifications.application.port.outbound.notification_repository import NotificationRepository
from notifications.application.port.outbound.processed_event_repository import ProcessedEventRepository
from notifications.application.usecase.push_delivery import NoPush, PushDelivery
from notifications.domain.model import code_email
from notifications.domain.model.errors import DeliveryUnavailable, InvalidEvent
from notifications.domain.model.event_notice import Notice, notices_for
from notifications.domain.model.notification import DeliveryAttempt, DeliveryChannel, DeliveryStatus, Notification

log = logging.getLogger(__name__)


class EventService:
    def __init__(self, notifications: NotificationRepository, clock: Clock, ids: IdGenerator,
                 push: PushDelivery | NoPush | None = None, *, processed: ProcessedEventRepository | None = None,
                 email: EmailSender | None = None, contacts: ContactDirectory | None = None) -> None:
        self._notifications = notifications
        self._clock = clock
        self._ids = ids
        self._push = push or NoPush()
        self._processed = processed
        self._email = email
        self._contacts = contacts

    def receive(self, event: IncomingEvent) -> EventOutcome:
        outcome = self._handle(event)
        # The id, type and outcome only: never the payload, an address or a code. The JSON line carries
        # the worker's X-Correlation-Id, so one event can be followed across both services.
        log.info("event %s of type %s: %s", event.id, event.type, outcome.value)
        return outcome

    def _handle(self, event: IncomingEvent) -> EventOutcome:
        if event.type in code_email.EVENT_TYPES:
            return self._send_code(event)
        notices = notices_for(event.type, event.payload)
        if not notices:
            return EventOutcome.IGNORED
        outcome = EventOutcome.DUPLICATE
        for notice in notices:
            now = self._clock.now()
            notification = Notification(id=self._ids.next(), user_id=notice.recipient,
                                        barbershop_id=event.barbershop_id, title=notice.title, body=notice.body,
                                        type=notice.type, read=False, source_event_id=event.id, created_at=now,
                                        updated_at=now)
            if not self._notifications.add_unless_seen(notification):
                if outcome is EventOutcome.PROCESSED:
                    # sourceEventId is unique: today a barbershop has one owner (DEC-NOTIF-02).
                    log.warning("event %s already notified one recipient, the next one is skipped", event.id)
                continue
            outcome = EventOutcome.PROCESSED
            # Only a new notification is pushed or e-mailed: a redelivered event never repeats them.
            self._push.deliver(notification)
            addressed = self._addressed(notice)
            if addressed is not None:
                self._mail_notice(notification, addressed.email, addressed.email_body(), addressed.email_html())
        return outcome

    def _addressed(self, notice: Notice) -> Notice | None:
        """The notice with the address to e-mail it to, or None when it is not e-mailed (DEC-NOTIF-02).

        A reminder's address is read from identity-auth (DEC-AUTH-10). If it cannot answer, the client
        still has the inbox and the push, so the reminder is not held back for the e-mail.
        """
        if notice.email:
            return notice
        if not notice.email_looked_up or self._contacts is None or self._email is None:
            return None
        try:
            contact = self._contacts.contact_of(notice.recipient)
        except Exception as error:  # identity-auth is down or slow
            log.warning("recipient's e-mail not read: %s", type(error).__name__)
            return None
        if contact is None:
            log.warning("identity-auth does not know the recipient: the reminder is not e-mailed")
            return None
        try:
            to = code_email.email_address(contact.email, "contact.email")
        except InvalidEvent:
            log.warning("identity-auth gave an address that cannot be e-mailed")
            return None
        return replace(notice, email=to, name=contact.full_name.strip())

    def _mail_notice(self, notification: Notification, to: str, body: str, html: str) -> None:
        """DEC-NOTIF-02: best effort, like the push. The inbox already has it, so a failure only logs."""
        if self._email is None:
            return
        try:
            self._email.send(to, notification.title, body, html=html)
            attempt = DeliveryAttempt(channel=DeliveryChannel.EMAIL, status=DeliveryStatus.SENT,
                                      attempted_at=self._clock.now())
        except Exception as error:  # the mail server is down or refused it
            log.warning("notice e-mail not sent: %s", type(error).__name__)
            attempt = DeliveryAttempt(channel=DeliveryChannel.EMAIL, status=DeliveryStatus.FAILED,
                                      attempted_at=self._clock.now(), error_code="UNAVAILABLE")
        self._notifications.record_delivery(notification.id, attempt)

    def _send_code(self, event: IncomingEvent) -> EventOutcome:
        """DEC-NOTIF-01, DEC-NOTIF-02: e-mail only, no inbox notification, and only the event id is kept.

        Sent first and recorded after: a failed send is not recorded, so the worker's retry sends it
        (a lost code locks the user out). Once sent, the event is done even if recording it fails:
        answering 503 then would resend the code on every retry. So a code is sent twice only when
        the worker redelivers an event it already got an answer for, never in a loop.
        """
        mail = code_email.code_email(event.type, event.payload)
        if mail.expires_at <= self._clock.now():  # the code no longer works: nothing to send, nothing to retry
            return EventOutcome.IGNORED
        if self._email is None or self._processed is None:
            raise DeliveryUnavailable("no mail server is configured")
        if self._processed.seen(event.id):
            return EventOutcome.DUPLICATE
        try:
            self._email.send(mail.to, mail.subject, mail.body, html=mail.html)
        except Exception as error:  # the mail server is down or refused it: the worker retries
            log.warning("code e-mail not sent: %s", type(error).__name__)
            raise DeliveryUnavailable("the mail server did not accept the message") from None
        try:
            self._processed.record(event.id, event.type, self._clock.now())
        except Exception as error:  # the e-mail is out: a retry would only resend it
            log.warning("code e-mail sent but not recorded: %s", type(error).__name__)
        return EventOutcome.PROCESSED
