"""
The names the events carry since MVP 3 (planName, barbershopName, 02-domain/domain-events.md) and the
HTML version of every e-mail (email_layout.py): the plain texts stay readable without the names.
"""
from notifications.domain.model import email_layout
from notifications.domain.model.code_email import code_email
from notifications.domain.model.event_notice import notices_for
from tests.conftest import ANA

SHOP = "6f0c1d7e-3a2b-4c5d-8e9f-0a1b2c3d4e5f"


def owners() -> list[dict]:
    return [{"userId": str(ANA), "fullName": "Ana Gómez", "email": "ana@example.com"}]


def expiring(**extra) -> dict:
    return {"barbershopId": SHOP, "barbershopName": "El Clásico", "kind": "PAID", "endsAt": "2026-12-05T15:00:00Z",
            "threshold": "DAYS_1", "owners": owners(), **extra}


def reminder(window: str, **extra) -> dict:
    return {"appointmentId": SHOP, "barbershopId": SHOP, "clientId": str(ANA), "date": "2026-10-10",
            "startTime": "10:00", "window": window, **extra}


def test_the_plan_notice_names_the_plan_when_the_event_carries_it():
    [paid] = notices_for("PlanExpiringSoon", expiring(planName="Pro"))
    [trial] = notices_for("PlanExpiringSoon", expiring(planName="Pro", kind="TRIAL", threshold="DAYS_7"))
    [without] = notices_for("PlanExpiringSoon", expiring(planName=None))

    assert paid.body.startswith("Tu plan Pro de El Clásico vence mañana (el 05/12/2026).")
    assert trial.body.startswith("Tu prueba gratis de El Clásico termina en 7 días")
    assert without.body.startswith("Tu plan de El Clásico vence mañana")


def test_the_reminder_names_the_barbershop_when_the_event_carries_it():
    [hour] = notices_for("AppointmentReminderDue", reminder("HOUR_BEFORE", barbershopName="El Clásico"))
    [day] = notices_for("AppointmentReminderDue", reminder("DAY_BEFORE", barbershopName="El Clásico"))
    [unknown] = notices_for("AppointmentReminderDue", reminder("HOUR_BEFORE", barbershopName=None))

    assert hour.body == "Tu cita en El Clásico es en 1 hora (10:00)."
    assert day.body == "Recuerda tu cita en El Clásico del 10/10 a las 10:00."
    assert unknown.body == "Tu cita es en 1 hora (10:00)."


def test_a_notice_e_mail_has_an_html_version_with_its_title_and_text():
    [notice] = notices_for("PlanExpiringSoon", expiring(planName="Pro"))
    page = notice.email_html()

    assert page.startswith("<!doctype html>")
    assert "Hola Ana Gómez," in page and "Tu plan vence pronto" in page
    assert "Tu plan Pro de El Clásico vence mañana" in page


def test_a_code_e_mail_shows_the_code_in_its_box():
    mail = code_email("EmailVerificationRequested", {"userId": str(ANA), "email": "ana@example.com",
                                                     "fullName": "Ana", "code": "482913",
                                                     "expiresAt": "2026-10-06T15:15:00Z"})

    assert "482913" in mail.body
    assert "Verifica tu correo" in mail.html and ">482913</td>" in mail.html
    assert "Vence en 15 minutos." in mail.html


def test_every_text_is_escaped():
    page = email_layout.render("<b>título</b>", "<script>x</script>", "a & b\n\notra <i>línea</i>")

    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "&lt;b&gt;título&lt;/b&gt;" in page and "a &amp; b" in page and "&lt;i&gt;" in page
