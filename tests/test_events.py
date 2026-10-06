"""POST /internal/v1/events (ADR-016): at most one notification per event, only from the worker."""
from uuid import UUID, uuid4

import pytest

from tests.conftest import ANA, bearer, make_token

EVENTS = "/internal/v1/events"
SHOP = "33333333-3333-3333-3333-333333333333"
WORKER = make_token(sub="barber-saas-worker", role="SERVICE")


def envelope(event_type: str, payload: dict, *, event_id: str | None = None, barbershop: str | None = SHOP) -> dict:
    body = {"id": event_id or str(uuid4()), "type": event_type, "version": 1,
            "occurredAt": "2026-10-06T15:00:00Z", "aggregateType": "appointment",
            "aggregateId": str(uuid4()), "correlationId": "trace-event", "payload": payload}
    if barbershop:
        body["barbershopId"] = barbershop
    return body


def appointment(client_id: str | None = str(ANA), **extra) -> dict:
    return {"appointmentId": str(uuid4()), "barbershopId": SHOP, "clientId": client_id,
            "barberId": str(uuid4()), "serviceId": str(uuid4()), "date": "2026-10-10",
            "startTime": "10:00", "endTime": "10:30", "status": "CONFIRMED", "priceAtBookingCents": 25000,
            **extra}


def deliver(client, body: dict, token: str = WORKER):
    return client.post(EVENTS, json=body, headers=bearer(token))


def inbox(notifications, user: UUID = ANA) -> list:
    return notifications.page_of(user, None, 0, 100)[0]


@pytest.mark.parametrize("event_type, payload, kind, title, body", [
    ("AppointmentConfirmed", appointment(), "APPOINTMENT_CONFIRMATION", "Cita confirmada",
     "Tu cita del 10/10 a las 10:00 fue confirmada."),
    ("AppointmentCancelled", appointment(status="CANCELLED", cancelledReason="Imprevisto del barbero"),
     "SYSTEM", "Cita cancelada", "Tu cita del 10/10 a las 10:00 fue cancelada. Motivo: Imprevisto del barbero"),
    ("AppointmentCompleted", appointment(status="COMPLETED", startTime="10:00:00"), "SYSTEM", "Cita completada",
     "Gracias por tu visita. Tu cita del 10/10 a las 10:00 quedó completada."),
    ("AppointmentReminderDue", appointment(), "REMINDER", "Recordatorio de cita",
     "Recuerda tu cita del 10/10 a las 10:00."),
    ("StickerGranted", {"clientId": str(ANA)}, "SYSTEM", "Ganaste un sello",
     "Sumaste un sello en tu tarjeta de fidelidad."),
    ("RewardRedeemed", {"clientId": str(ANA)}, "SYSTEM", "Recompensa canjeada",
     "Canjeaste tu recompensa: el cupón se aplica en tu próxima cita."),
    ("PasswordResetRequested", {"userId": str(ANA)}, "SYSTEM", "Cambio de contraseña",
     "Recibimos una solicitud para cambiar tu contraseña. Si no fuiste tú, ignora este mensaje."),
])
def test_each_event_notifies_its_recipient_once(client, notifications, event_type, payload, kind, title, body):
    event = envelope(event_type, payload)

    response = deliver(client, event)

    assert response.status_code == 200
    assert response.json() == {"eventId": event["id"], "outcome": "PROCESSED"}
    [created] = inbox(notifications)
    assert (created.type.value, created.title, created.body) == (kind, title, body)
    assert str(created.source_event_id) == event["id"] and str(created.barbershop_id) == SHOP
    assert not created.read


def test_a_redelivered_event_is_a_duplicate_and_notifies_nobody(client, notifications):
    event = envelope("AppointmentConfirmed", appointment())
    deliver(client, event)

    response = deliver(client, event)

    assert response.status_code == 200 and response.json()["outcome"] == "DUPLICATE"
    assert len(inbox(notifications)) == 1


def test_a_walk_in_has_nobody_to_notify(client, notifications):
    response = deliver(client, envelope("AppointmentConfirmed", appointment(client_id=None)))

    assert response.status_code == 200 and response.json()["outcome"] == "IGNORED"
    assert inbox(notifications) == []


def test_an_event_without_a_barbershop_is_kept_without_one(client, notifications):
    deliver(client, envelope("PasswordResetRequested", {"userId": str(ANA)}, barbershop=None))

    assert inbox(notifications)[0].barbershop_id is None


def test_an_event_this_service_does_not_handle_answers_422(client, notifications):
    response = deliver(client, envelope("AppointmentCreated", appointment()))

    assert response.status_code == 422 and response.json()["error"] == "BUSINESS_RULE_VIOLATION"
    assert inbox(notifications) == []


@pytest.mark.parametrize("payload, field", [
    ({"date": "2026-10-10", "startTime": "10:00"}, "payload.clientId"),
    (appointment(client_id="not-a-uuid"), "payload.clientId"),
    (appointment(date="10/10/2026"), "payload.date"),
])
def test_a_payload_without_what_the_notification_needs_answers_400(client, payload, field):
    response = deliver(client, envelope("AppointmentConfirmed", payload))

    assert response.status_code == 400 and response.json()["details"][0]["field"] == field


def test_an_incomplete_envelope_answers_400(client):
    event = envelope("AppointmentConfirmed", appointment())
    del event["id"]

    response = deliver(client, event)

    assert response.status_code == 400 and response.json()["details"][0]["field"] == "id"


@pytest.mark.parametrize("token", [
    make_token(),
    make_token(sub="barber-saas-workflow", role="SERVICE"),
], ids=["user", "another-service"])
def test_only_the_worker_delivers_events(client, notifications, token):
    response = deliver(client, envelope("AppointmentConfirmed", appointment()), token)

    assert response.status_code == 403 and response.json()["error"] == "FORBIDDEN"
    assert inbox(notifications) == []


def test_without_a_token_an_event_answers_401(client):
    assert client.post(EVENTS, json=envelope("AppointmentConfirmed", appointment())).status_code == 401
