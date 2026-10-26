"""
EmailVerificationRequested (DEC-NOTIF-02, ADR-018): the same rules as the password-reset code — e-mail
only, never the inbox, never stored, and 503 while the mail server cannot take it.
"""
from uuid import UUID

import pytest

from tests.conftest import ANA
from tests.test_events import deliver, envelope, inbox
from tests.test_password_reset import app_with, client, mail, processed  # noqa: F401 (fixtures)

CODE = "123456"


def verification(**extra) -> dict:
    return {"userId": str(ANA), "email": "ana@example.com", "fullName": "Ana Gómez", "code": CODE,
            "expiresAt": "2026-10-06T13:15:00Z", **extra}


def test_the_verification_code_is_e_mailed_and_never_reaches_the_inbox(client, notifications, mail):
    event = envelope("EmailVerificationRequested", verification(), barbershop=None)

    response = deliver(client, event)

    assert response.status_code == 200 and response.json() == {"eventId": event["id"], "outcome": "PROCESSED"}
    [(to, subject, body)] = mail.sent
    assert to == "ana@example.com" and subject == "Tu código de verificación de BarberSaaS"
    assert "Hola Ana Gómez" in body
    assert "Tu código de verificación de BarberSaaS es 123456. Vence en 15 minutos." in body
    assert inbox(notifications) == []


def test_a_redelivered_verification_is_a_duplicate_and_is_not_e_mailed_again(client, mail):
    event = envelope("EmailVerificationRequested", verification(), barbershop=None)
    deliver(client, event)

    response = deliver(client, event)

    assert response.json()["outcome"] == "DUPLICATE" and len(mail.sent) == 1


def test_only_the_verification_event_id_is_kept_never_the_code(client, processed):
    event = envelope("EmailVerificationRequested", verification(), barbershop=None)

    deliver(client, event)

    assert processed.seen(UUID(event["id"])) and CODE not in repr(processed._seen)


def test_a_mail_server_failure_answers_503_so_the_worker_retries_the_code(client, mail):
    event = envelope("EmailVerificationRequested", verification(), barbershop=None)
    mail.failing = True

    failed = deliver(client, event)
    mail.failing = False
    retried = deliver(client, event)

    assert failed.status_code == 503 and CODE not in failed.text
    assert retried.json()["outcome"] == "PROCESSED" and len(mail.sent) == 1


def test_without_a_mail_server_the_verification_waits_for_a_retry(notifications, clock, processed):
    client = app_with(notifications, clock, mail=None, processed=processed)

    response = deliver(client, envelope("EmailVerificationRequested", verification(), barbershop=None))

    assert response.status_code == 503


def test_an_expired_verification_code_is_ignored(client, mail):
    response = deliver(client, envelope("EmailVerificationRequested",
                                        verification(expiresAt="2026-10-06T12:59:59Z"), barbershop=None))

    assert response.json()["outcome"] == "IGNORED" and mail.sent == []


@pytest.mark.parametrize("payload, field", [
    (verification(email="not-an-address"), "payload.email"),
    (verification(code="12345"), "payload.code"),
    (verification(expiresAt="2026-10-06T13:15:00"), "payload.expiresAt"),
])
def test_an_invalid_verification_payload_answers_400(client, mail, payload, field):
    response = deliver(client, envelope("EmailVerificationRequested", payload, barbershop=None))

    assert response.status_code == 400 and response.json()["details"][0]["field"] == field
    assert mail.sent == []
