"""
AppointmentReminderDue version 2 (DEC-NOTIF-02, DEC-APPT-12, HU-NOTIF-005): the window decides the
text, and both windows are also e-mailed to the client, whose address identity-auth gives
(DEC-AUTH-10). The e-mail is best effort: without it the reminder is still PROCESSED.
"""
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from notifications.adapter.inbound.http.app import Services, create_app
from notifications.adapter.inbound.http.auth import Rs256Verifier
from notifications.adapter.outbound.persistence.in_memory import (InMemoryDeviceTokenRepository,
                                                                  InMemoryProcessedEventRepository)
from notifications.adapter.outbound.system import RandomIds
from notifications.application.port.outbound.contact_directory import Contact
from notifications.application.usecase.device_token_service import DeviceTokenService
from notifications.application.usecase.event_service import EventService
from notifications.application.usecase.notification_service import NotificationService
from notifications.domain.model.notification import DeliveryChannel, DeliveryStatus
from tests.conftest import ANA, PUBLIC_KEY
from tests.test_events import appointment, deliver, envelope, inbox
from tests.test_password_reset import FakeMail
from tests.test_plan_notices import FakePush


class FakeContacts:
    def __init__(self) -> None:
        self.known = {ANA: Contact(email="ana@example.com", full_name="Ana Gómez")}
        self.failing = False
        self.asked: list[UUID] = []

    def contact_of(self, user_id: UUID) -> Contact | None:
        self.asked.append(user_id)
        if self.failing:
            raise TimeoutError("identity-auth did not answer")
        return self.known.get(user_id)


def reminder(window: str | None = "DAY_BEFORE", **extra) -> dict:
    payload = appointment(**extra)
    if window:
        payload["window"] = window
    return payload


@pytest.fixture
def mail() -> FakeMail:
    return FakeMail()


@pytest.fixture
def push() -> FakePush:
    return FakePush()


@pytest.fixture
def contacts() -> FakeContacts:
    return FakeContacts()


def app_with(notifications, clock, *, mail=None, push=None, contacts=None) -> TestClient:
    events = EventService(notifications, clock, RandomIds(), push, processed=InMemoryProcessedEventRepository(),
                          email=mail, contacts=contacts)
    services = Services(notifications=NotificationService(notifications, clock), events=events,
                        device_tokens=DeviceTokenService(InMemoryDeviceTokenRepository(), clock, RandomIds()))
    return TestClient(create_app(services, Rs256Verifier(PUBLIC_KEY)), raise_server_exceptions=False)


@pytest.fixture
def client(notifications, clock, mail, push, contacts) -> TestClient:
    return app_with(notifications, clock, mail=mail, push=push, contacts=contacts)


@pytest.mark.parametrize("payload, version, body", [
    (reminder("DAY_BEFORE"), 2, "Recuerda tu cita del 10/10 a las 10:00."),
    (reminder("HOUR_BEFORE", startTime="10:00:00"), 2, "Tu cita es en 1 hora (10:00)."),
    (reminder(None), 1, "Recuerda tu cita del 10/10 a las 10:00."),
], ids=["day-before", "hour-before", "version-1-is-day-before"])
def test_each_window_reaches_the_inbox_the_phone_and_the_e_mail(client, notifications, mail, push,
                                                                 payload, version, body):
    event = envelope("AppointmentReminderDue", payload) | {"version": version}

    response = deliver(client, event)

    assert response.status_code == 200 and response.json()["outcome"] == "PROCESSED"
    [created] = inbox(notifications)
    assert (created.type.value, created.title, created.body) == ("REMINDER", "Recordatorio de cita", body)
    assert push.pushed == [created]
    [(to, subject, text)] = mail.sent
    assert (to, subject) == ("ana@example.com", "Recordatorio de cita")
    assert text == f"Hola Ana Gómez,\n\n{body}"
    [attempt] = notifications.attempts_of(created.id)
    assert (attempt.channel, attempt.status) == (DeliveryChannel.EMAIL, DeliveryStatus.SENT)


def test_identity_auth_down_does_not_block_the_reminder(client, notifications, mail, push, contacts):
    contacts.failing = True

    response = deliver(client, envelope("AppointmentReminderDue", reminder("HOUR_BEFORE")))

    assert response.status_code == 200 and response.json()["outcome"] == "PROCESSED"
    assert len(inbox(notifications)) == 1 and len(push.pushed) == 1 and mail.sent == []


def test_a_failed_reminder_e_mail_does_not_block_the_reminder(client, notifications, mail):
    mail.failing = True

    response = deliver(client, envelope("AppointmentReminderDue", reminder("DAY_BEFORE")))

    assert response.json()["outcome"] == "PROCESSED"
    [attempt] = notifications.attempts_of(inbox(notifications)[0].id)
    assert (attempt.channel, attempt.status) == (DeliveryChannel.EMAIL, DeliveryStatus.FAILED)


def test_a_client_identity_auth_does_not_know_gets_no_e_mail(client, notifications, mail, contacts):
    contacts.known.clear()

    response = deliver(client, envelope("AppointmentReminderDue", reminder("DAY_BEFORE")))

    assert response.json()["outcome"] == "PROCESSED" and len(inbox(notifications)) == 1 and mail.sent == []


def test_a_redelivered_reminder_is_neither_looked_up_nor_e_mailed_again(client, mail, contacts):
    event = envelope("AppointmentReminderDue", reminder("HOUR_BEFORE"))
    deliver(client, event)

    response = deliver(client, event)

    assert response.json()["outcome"] == "DUPLICATE"
    assert len(mail.sent) == 1 and contacts.asked == [ANA]


def test_a_walk_in_reminder_asks_identity_auth_nothing(client, mail, contacts):
    response = deliver(client, envelope("AppointmentReminderDue", reminder("HOUR_BEFORE", client_id=None)))

    assert response.json()["outcome"] == "IGNORED" and contacts.asked == [] and mail.sent == []


def test_without_identity_auth_configured_the_reminder_is_not_e_mailed(notifications, clock, mail, push):
    client = app_with(notifications, clock, mail=mail, push=push, contacts=None)

    response = deliver(client, envelope("AppointmentReminderDue", reminder("DAY_BEFORE")))

    assert response.json()["outcome"] == "PROCESSED" and len(push.pushed) == 1 and mail.sent == []


def test_an_unknown_window_answers_400(client, notifications):
    response = deliver(client, envelope("AppointmentReminderDue", reminder("WEEK_BEFORE")))

    assert response.status_code == 400 and response.json()["details"][0]["field"] == "payload.window"
    assert inbox(notifications) == []


def test_other_client_events_are_not_e_mailed(client, mail, contacts):
    deliver(client, envelope("AppointmentConfirmed", appointment()))

    assert mail.sent == [] and contacts.asked == []
