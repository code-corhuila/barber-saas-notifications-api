"""
planName in PlanExpiringSoon and barbershopName in AppointmentReminderDue (docs #142): the notice names
them when they come, and keeps the text without them when they are null, so an event without them
still notifies.
"""
import pytest

from tests.test_events import deliver, envelope, inbox
from tests.test_plan_notices import client, expiring, mail, push  # noqa: F401 (fixtures)
from tests.test_reminders import contacts, reminder  # noqa: F401 (fixtures)


@pytest.mark.parametrize("payload, body", [
    (expiring(kind="PAID", threshold="DAYS_1", planName="Pro"),
     "Tu plan Pro de El Clásico vence mañana (el 05/12/2026). Paga tu plan en Mi plan para seguir recibiendo reservas."),
    (expiring(kind="PAID", threshold="DAYS_7", planName=None),
     "Tu plan de El Clásico vence en 7 días (el 05/12/2026). Paga tu plan en Mi plan para seguir recibiendo reservas."),
    (expiring(kind="PAID", threshold="DAYS_7", planName="  "),
     "Tu plan de El Clásico vence en 7 días (el 05/12/2026). Paga tu plan en Mi plan para seguir recibiendo reservas."),
    (expiring(kind="TRIAL", threshold="DAYS_7", planName="Pro"),
     "Tu prueba gratis de El Clásico termina en 7 días (el 05/12/2026). "
     "Elige un plan en Mi plan para seguir recibiendo reservas."),
], ids=["paid-with-plan", "paid-plan-null", "paid-plan-blank", "trial-keeps-its-text"])
def test_the_paid_notice_names_the_plan_when_it_comes(client, notifications, mail, payload, body):
    deliver(client, envelope("PlanExpiringSoon", payload))

    [created] = inbox(notifications)
    assert created.body == body and body in mail.sent[0][2]


@pytest.mark.parametrize("payload, body", [
    (reminder("HOUR_BEFORE", barbershopName="El Clásico"), "Tu cita en El Clásico es en 1 hora (10:00)."),
    (reminder("DAY_BEFORE", barbershopName="El Clásico"), "Recuerda tu cita en El Clásico del 10/10 a las 10:00."),
    (reminder("HOUR_BEFORE", barbershopName=None), "Tu cita es en 1 hora (10:00)."),
    (reminder("DAY_BEFORE"), "Recuerda tu cita del 10/10 a las 10:00."),
    (reminder("HOUR_BEFORE", barbershopName=42), "Tu cita es en 1 hora (10:00)."),
], ids=["hour-with-name", "day-with-name", "name-null", "no-name-field", "name-not-text"])
def test_the_reminder_names_the_barbershop_when_it_comes(client, notifications, payload, body):
    response = deliver(client, envelope("AppointmentReminderDue", payload))

    assert response.json()["outcome"] == "PROCESSED"
    assert inbox(notifications)[0].body == body
