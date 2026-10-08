"""
PasswordResetRequested (DEC-NOTIF-01): the code goes by e-mail only, never to the inbox, is sent
once per event and is never stored; without a working mail server the worker retries (503).
"""
from uuid import UUID, uuid4

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
from tests.conftest import ANA, PUBLIC_KEY
from tests.test_events import deliver, envelope, inbox

CODE = "482913"


class FakeMail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.failing = False

    def send(self, to: str, subject: str, body: str) -> None:
        if self.failing:
            raise ConnectionRefusedError("mail server down")
        self.sent.append((to, subject, body))


def reset(**extra) -> dict:
    return {"userId": str(ANA), "email": "ana@example.com", "fullName": "Ana Gómez", "code": CODE,
            "expiresAt": "2026-10-06T15:15:00Z", **extra}


@pytest.fixture
def mail() -> FakeMail:
    return FakeMail()


@pytest.fixture
def processed() -> InMemoryProcessedEventRepository:
    return InMemoryProcessedEventRepository()


def app_with(notifications, clock, *, mail=None, processed=None) -> TestClient:
    events = EventService(notifications, clock, RandomIds(), processed=processed, email=mail)
    services = Services(notifications=NotificationService(notifications, clock), events=events,
                        device_tokens=DeviceTokenService(InMemoryDeviceTokenRepository(), clock, RandomIds()))
    return TestClient(create_app(services, Rs256Verifier(PUBLIC_KEY)), raise_server_exceptions=False)


@pytest.fixture
def client(notifications, clock, mail, processed) -> TestClient:
    return app_with(notifications, clock, mail=mail, processed=processed)


def test_the_code_is_e_mailed_to_the_account_and_never_reaches_the_inbox(client, notifications, mail):
    event = envelope("PasswordResetRequested", reset(), barbershop=None)

    response = deliver(client, event)

    assert response.status_code == 200 and response.json() == {"eventId": event["id"], "outcome": "PROCESSED"}
    [(to, subject, body)] = mail.sent
    assert to == "ana@example.com" and subject == "Código para cambiar tu contraseña"
    assert CODE in body and "Hola Ana Gómez" in body
    assert "10:15 del 06/10/2026 (hora de Colombia)" in body
    assert inbox(notifications) == []


def test_a_redelivered_reset_is_a_duplicate_and_is_not_e_mailed_again(client, mail):
    event = envelope("PasswordResetRequested", reset(), barbershop=None)
    deliver(client, event)

    response = deliver(client, event)

    assert response.status_code == 200 and response.json()["outcome"] == "DUPLICATE"
    assert len(mail.sent) == 1


def test_only_the_event_id_is_kept_never_the_code(client, processed):
    event = envelope("PasswordResetRequested", reset(), barbershop=None)

    deliver(client, event)

    assert processed.seen(UUID(event["id"]))
    assert CODE not in repr(processed._seen)


def test_a_mail_server_failure_answers_503_and_the_retry_sends_it(client, mail):
    event = envelope("PasswordResetRequested", reset(), barbershop=None)
    mail.failing = True

    failed = deliver(client, event)
    mail.failing = False
    retried = deliver(client, event)

    assert failed.status_code == 503 and failed.json()["error"] == "SERVICE_UNAVAILABLE"
    assert CODE not in failed.text
    assert retried.status_code == 200 and retried.json()["outcome"] == "PROCESSED"
    assert len(mail.sent) == 1


def test_without_a_mail_server_the_event_waits_for_a_retry(notifications, clock, processed):
    client = app_with(notifications, clock, mail=None, processed=processed)

    response = deliver(client, envelope("PasswordResetRequested", reset(), barbershop=None))

    assert response.status_code == 503
    assert inbox(notifications) == []


@pytest.mark.parametrize("payload, field", [
    (reset(email="not-an-address"), "payload.email"),
    (reset(email="ana@example.com\r\nBcc: x@y.z"), "payload.email"),
    (reset(code="12345"), "payload.code"),
    (reset(code="abcdef"), "payload.code"),
    (reset(expiresAt="tomorrow"), "payload.expiresAt"),
    (reset(expiresAt="2026-10-06T15:15:00"), "payload.expiresAt"),
    (reset(userId="not-a-uuid"), "payload.userId"),
    ({k: v for k, v in reset().items() if k != "email"}, "payload.email"),
])
def test_an_invalid_reset_payload_answers_400_and_sends_nothing(client, mail, payload, field):
    response = deliver(client, envelope("PasswordResetRequested", payload, barbershop=None))

    assert response.status_code == 400
    assert response.json()["details"][0]["field"] == field
    assert mail.sent == []


def test_a_reset_without_a_name_still_greets(client, mail):
    deliver(client, envelope("PasswordResetRequested", reset(fullName=None), barbershop=None))

    assert mail.sent[0][2].startswith("Hola,\n")


def test_another_event_still_notifies_the_inbox(client, notifications, mail):
    deliver(client, envelope("StickerGranted", {"clientId": str(ANA)}))

    assert len(inbox(notifications)) == 1 and mail.sent == []


def test_ids_are_independent_per_event(client, mail):
    for _ in range(2):
        deliver(client, envelope("PasswordResetRequested", reset(), event_id=str(uuid4()), barbershop=None))

    assert len(mail.sent) == 2


class UnrecordableEvents(InMemoryProcessedEventRepository):
    def record(self, event_id, event_type, processed_at) -> None:
        raise TimeoutError("write concern timed out")


def test_a_sent_code_whose_record_fails_is_not_retried_so_it_is_not_resent(notifications, clock, mail):
    # Answering 503 here would make the worker resend the code on every retry while the store is
    # down; the e-mail is out, so the event is done and only a redelivery by the worker repeats it.
    client = app_with(notifications, clock, mail=mail, processed=UnrecordableEvents())
    event = envelope("PasswordResetRequested", reset(), barbershop=None)

    response = deliver(client, event)

    assert response.status_code == 200 and response.json()["outcome"] == "PROCESSED"
    assert len(mail.sent) == 1
