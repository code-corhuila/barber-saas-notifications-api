"""
PlanExpiringSoon and BarbershopSuspended (DEC-NOTIF-02, HU-SADMIN-004): each owner gets a SYSTEM
notification, a push and an e-mail. Only the codes answer 503: a notice whose e-mail fails is still
PROCESSED, because the inbox and the push already reached the owner.
"""
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from notifications.adapter.inbound.http.app import Services, create_app
from notifications.adapter.inbound.http.auth import Rs256Verifier
from notifications.adapter.outbound.persistence.in_memory import (InMemoryDeviceTokenRepository,
                                                                  InMemoryProcessedEventRepository)
from notifications.adapter.outbound.system import RandomIds
from notifications.application.usecase.device_token_service import DeviceTokenService
from notifications.application.usecase.event_service import EventService
from notifications.application.usecase.notification_service import NotificationService
from notifications.domain.model.notification import DeliveryChannel, DeliveryStatus
from tests.conftest import ANA, PUBLIC_KEY
from tests.test_events import SHOP, deliver, envelope, inbox
from tests.test_password_reset import FakeMail


class FakePush:
    def __init__(self) -> None:
        self.pushed: list = []

    def deliver(self, notification) -> None:
        self.pushed.append(notification)


def owners(**extra) -> list[dict]:
    return [{"userId": str(ANA), "fullName": "Ana Gómez", "email": "ana@example.com", **extra}]


def expiring(**extra) -> dict:
    return {"barbershopId": SHOP, "barbershopName": "El Clásico", "kind": "TRIAL",
            "endsAt": "2026-12-05T15:00:00Z", "threshold": "DAYS_7", "owners": owners(), **extra}


def suspended(**extra) -> dict:
    return {"barbershopId": SHOP, "barbershopName": "El Clásico", "reason": "TRIAL_EXPIRED", "owners": owners(),
            **extra}


@pytest.fixture
def mail() -> FakeMail:
    return FakeMail()


@pytest.fixture
def push() -> FakePush:
    return FakePush()


def app_with(notifications, clock, *, mail=None, push=None) -> TestClient:
    events = EventService(notifications, clock, RandomIds(), push, processed=InMemoryProcessedEventRepository(),
                          email=mail)
    services = Services(notifications=NotificationService(notifications, clock), events=events,
                        device_tokens=DeviceTokenService(InMemoryDeviceTokenRepository(), clock, RandomIds()))
    return TestClient(create_app(services, Rs256Verifier(PUBLIC_KEY)), raise_server_exceptions=False)


@pytest.fixture
def client(notifications, clock, mail, push) -> TestClient:
    return app_with(notifications, clock, mail=mail, push=push)


@pytest.mark.parametrize("event_type, payload, title, body", [
    ("PlanExpiringSoon", expiring(), "Tu prueba gratis termina pronto",
     "Tu prueba gratis de El Clásico termina en 7 días (el 05/12/2026). "
     "Elige un plan en Mi plan para seguir recibiendo reservas."),
    ("PlanExpiringSoon", expiring(threshold="DAYS_1", endsAt="2026-12-06T03:00:00Z"), "Tu prueba gratis termina pronto",
     "Tu prueba gratis de El Clásico termina mañana (el 05/12/2026). "
     "Elige un plan en Mi plan para seguir recibiendo reservas."),
    ("PlanExpiringSoon", expiring(kind="PAID", threshold="DAYS_1"), "Tu plan vence pronto",
     "Tu plan de El Clásico vence mañana (el 05/12/2026). Paga tu plan en Mi plan para seguir recibiendo reservas."),
    ("BarbershopSuspended", suspended(), "Barbería suspendida",
     "El Clásico fue suspendida porque terminó tu prueba gratis. Paga tu plan en Mi plan para reactivarla."),
    ("BarbershopSuspended", suspended(reason="PAYMENT_EXPIRED"), "Barbería suspendida",
     "El Clásico fue suspendida porque terminó tu mes pagado. Paga tu plan en Mi plan para reactivarla."),
], ids=["trial-7-days", "trial-1-day-colombia-date", "paid-1-day", "trial-expired", "payment-expired"])
def test_the_owner_gets_the_notice_in_the_inbox_by_push_and_by_e_mail(client, notifications, mail, push,
                                                                       event_type, payload, title, body):
    event = envelope(event_type, payload)

    response = deliver(client, event)

    assert response.status_code == 200 and response.json()["outcome"] == "PROCESSED"
    [created] = inbox(notifications)
    assert (created.type.value, created.title, created.body) == ("SYSTEM", title, body)
    assert str(created.source_event_id) == event["id"] and str(created.barbershop_id) == SHOP
    assert push.pushed == [created]
    [(to, subject, text)] = mail.sent
    assert to == "ana@example.com" and subject == title
    assert text.startswith("Hola Ana Gómez,\n\n") and body in text


def test_a_sent_e_mail_is_recorded_on_the_notification(client, notifications):
    deliver(client, envelope("BarbershopSuspended", suspended()))

    [attempt] = notifications.attempts_of(inbox(notifications)[0].id)
    assert (attempt.channel, attempt.status) == (DeliveryChannel.EMAIL, DeliveryStatus.SENT)


def test_a_failed_notice_e_mail_does_not_block_the_event(client, notifications, mail, push):
    mail.failing = True

    response = deliver(client, envelope("PlanExpiringSoon", expiring()))

    assert response.status_code == 200 and response.json()["outcome"] == "PROCESSED"
    [created] = inbox(notifications)
    assert push.pushed == [created]
    [attempt] = notifications.attempts_of(created.id)
    assert (attempt.channel, attempt.status, attempt.error_code) == (
        DeliveryChannel.EMAIL, DeliveryStatus.FAILED, "UNAVAILABLE")


def test_without_a_mail_server_the_notice_still_reaches_the_inbox(notifications, clock, push):
    client = app_with(notifications, clock, mail=None, push=push)

    response = deliver(client, envelope("PlanExpiringSoon", expiring()))

    assert response.json()["outcome"] == "PROCESSED" and len(inbox(notifications)) == 1 and len(push.pushed) == 1


def test_a_redelivered_notice_is_a_duplicate_and_is_not_e_mailed_again(client, notifications, mail, push):
    event = envelope("BarbershopSuspended", suspended())
    deliver(client, event)

    response = deliver(client, event)

    assert response.json()["outcome"] == "DUPLICATE"
    assert len(inbox(notifications)) == 1 and len(mail.sent) == 1 and len(push.pushed) == 1


def test_a_notice_without_owners_notifies_nobody(client, notifications, mail):
    response = deliver(client, envelope("PlanExpiringSoon", expiring(owners=[])))

    assert response.json()["outcome"] == "IGNORED" and inbox(notifications) == [] and mail.sent == []


def test_an_appointment_event_is_not_e_mailed_by_this_rule(client, notifications, mail):
    deliver(client, envelope("StickerGranted", {"clientId": str(ANA)}))

    assert len(inbox(notifications)) == 1 and mail.sent == []


@pytest.mark.parametrize("event_type, payload, field", [
    ("PlanExpiringSoon", expiring(kind="FREE"), "payload.kind"),
    ("PlanExpiringSoon", expiring(threshold="DAYS_3"), "payload.threshold"),
    ("PlanExpiringSoon", expiring(endsAt="soon"), "payload.endsAt"),
    ("PlanExpiringSoon", expiring(barbershopName=" "), "payload.barbershopName"),
    ("PlanExpiringSoon", expiring(owners="ana"), "payload.owners"),
    ("PlanExpiringSoon", expiring(owners=owners(userId="not-a-uuid")), "payload.owners[0].userId"),
    ("PlanExpiringSoon", expiring(owners=owners(email="ana@example.com\r\nBcc: x@y.z")), "payload.owners[0].email"),
    ("BarbershopSuspended", suspended(reason="LATE"), "payload.reason"),
])
def test_an_invalid_notice_answers_400_and_notifies_nobody(client, notifications, mail, event_type, payload, field):
    response = deliver(client, envelope(event_type, payload))

    assert response.status_code == 400 and response.json()["details"][0]["field"] == field
    assert inbox(notifications) == [] and mail.sent == []


def test_the_owner_is_read_as_a_uuid(client, notifications):
    deliver(client, envelope("BarbershopSuspended", suspended()))

    assert inbox(notifications)[0].user_id == UUID(str(ANA))
