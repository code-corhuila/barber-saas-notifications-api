"""
Which notification each domain event produces, and for whom (02-domain/domain-events.md, Event
Summary Table). The texts are in Spanish because the user reads them on screen.
"""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID

from notifications.domain.model.code_email import COLOMBIA, email_address
from notifications.domain.model.errors import InvalidEvent, UnsupportedEvent
from notifications.domain.model.notification import BODY_MAX, NotificationType


@dataclass(frozen=True)
class Notice:
    """What to tell, and to whom, before it becomes a notification of their inbox."""

    recipient: UUID
    type: NotificationType
    title: str
    body: str
    # Where the same notice is also e-mailed (DEC-NOTIF-02); None: inbox and push only.
    email: str | None = None
    name: str = ""
    # The event does not carry the address: it is read from identity-auth (DEC-AUTH-10).
    email_looked_up: bool = False

    def email_body(self) -> str:
        return f"Hola{' ' + self.name if self.name else ''},\n\n{self.body}"


def _recipient(payload: Mapping, field: str) -> UUID | None:
    """None when the field is null: a walk-in has no account to notify."""
    if field not in payload:
        raise InvalidEvent(f"payload.{field}", "is required")
    value = payload[field]
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        raise InvalidEvent(f"payload.{field}", "must be a UUID") from None


def _start(payload: Mapping) -> str:
    """'10:00' or '10:00:00' → '10:00'."""
    try:
        return f"{time.fromisoformat(str(payload.get('startTime'))):%H:%M}"
    except ValueError:
        raise InvalidEvent("payload.startTime", "must be a time as HH:mm") from None


def _when(payload: Mapping) -> str:
    """'2026-10-10' and '10:00' (or '10:00:00') → 'del 10/10 a las 10:00'."""
    try:
        day = date.fromisoformat(str(payload.get("date")))
    except ValueError:
        raise InvalidEvent("payload.date", "must be a date as YYYY-MM-DD") from None
    return f"del {day:%d/%m} a las {_start(payload)}"


def _confirmed(p: Mapping) -> tuple[NotificationType, str, str]:
    return NotificationType.APPOINTMENT_CONFIRMATION, "Cita confirmada", f"Tu cita {_when(p)} fue confirmada."


def _cancelled(p: Mapping) -> tuple[NotificationType, str, str]:
    reason = str(p.get("cancelledReason") or "").strip()
    body = f"Tu cita {_when(p)} fue cancelada." + (f" Motivo: {reason}" if reason else "")
    return NotificationType.SYSTEM, "Cita cancelada", body[:BODY_MAX]


def _completed(p: Mapping) -> tuple[NotificationType, str, str]:
    return NotificationType.SYSTEM, "Cita completada", f"Gracias por tu visita. Tu cita {_when(p)} quedó completada."


def _reminder(p: Mapping) -> tuple[NotificationType, str, str]:
    # Version 1 has no window: it was always the day-before reminder (DEC-APPT-12).
    window = p.get("window") or "DAY_BEFORE"
    if window == "DAY_BEFORE":
        return NotificationType.REMINDER, "Recordatorio de cita", f"Recuerda tu cita {_when(p)}."
    if window != "HOUR_BEFORE":
        raise InvalidEvent("payload.window", "must be one of DAY_BEFORE, HOUR_BEFORE")
    return NotificationType.REMINDER, "Recordatorio de cita", f"Tu cita es en 1 hora ({_start(p)})."


def _sticker(_: Mapping) -> tuple[NotificationType, str, str]:
    return NotificationType.SYSTEM, "Ganaste un sello", "Sumaste un sello en tu tarjeta de fidelidad."


def _reward(_: Mapping) -> tuple[NotificationType, str, str]:
    return NotificationType.SYSTEM, "Recompensa canjeada", "Canjeaste tu recompensa: el cupón se aplica en tu próxima cita."


# event type → (payload field of the recipient, text). The code events are not here: they are an
# e-mail, never an inbox notification (DEC-NOTIF-01, DEC-NOTIF-02, code_email.py).
_HANDLED: dict[str, tuple[str, Callable[[Mapping], tuple[NotificationType, str, str]]]] = {
    "AppointmentConfirmed": ("clientId", _confirmed),
    "AppointmentCancelled": ("clientId", _cancelled),
    "AppointmentCompleted": ("clientId", _completed),
    "AppointmentReminderDue": ("clientId", _reminder),
    "StickerGranted": ("clientId", _sticker),
    "RewardRedeemed": ("clientId", _reward),
}
# Client events that are also e-mailed, to the address identity-auth gives (DEC-NOTIF-02).
_E_MAILED_TO_CLIENT = frozenset({"AppointmentReminderDue"})


def _choice(payload: Mapping, field: str, allowed: Mapping[str, str]) -> str:
    value = payload.get(field)
    if value not in allowed:
        raise InvalidEvent(f"payload.{field}", f"must be one of {', '.join(allowed)}")
    return allowed[value]


def _shop(payload: Mapping) -> str:
    name = payload.get("barbershopName")
    if not isinstance(name, str) or not name.strip():
        raise InvalidEvent("payload.barbershopName", "is required")
    return name.strip()


def _ends_on(payload: Mapping) -> str:
    """'2026-12-05T15:00:00Z' → '05/12/2026', the day it ends in Colombia."""
    try:
        ends = datetime.fromisoformat(str(payload.get("endsAt")).replace("Z", "+00:00"))
    except ValueError:
        raise InvalidEvent("payload.endsAt", "must be a date-time") from None
    if ends.tzinfo is None:
        raise InvalidEvent("payload.endsAt", "must carry its offset")
    return f"{ends.astimezone(COLOMBIA):%d/%m/%Y}"


_LEFT = {"DAYS_7": "en 7 días", "DAYS_1": "mañana"}


def _expiring(p: Mapping) -> tuple[str, str]:
    kind = _choice(p, "kind", {"TRIAL": "TRIAL", "PAID": "PAID"})
    left, shop, day = _choice(p, "threshold", _LEFT), _shop(p), _ends_on(p)
    if kind == "TRIAL":
        return "Tu prueba gratis termina pronto", (f"Tu prueba gratis de {shop} termina {left} (el {day}). "
                                                   "Elige un plan en Mi plan para seguir recibiendo reservas.")
    return "Tu plan vence pronto", (f"Tu plan de {shop} vence {left} (el {day}). "
                                    "Paga tu plan en Mi plan para seguir recibiendo reservas.")


def _suspended(p: Mapping) -> tuple[str, str]:
    why = _choice(p, "reason", {"TRIAL_EXPIRED": "tu prueba gratis", "PAYMENT_EXPIRED": "tu mes pagado"})
    return "Barbería suspendida", (f"{_shop(p)} fue suspendida porque terminó {why}. "
                                   "Paga tu plan en Mi plan para reactivarla.")


# event type → its text; each owner of payload.owners gets it (DEC-NOTIF-02, DEC-PLAT-07).
_TO_OWNERS: dict[str, Callable[[Mapping], tuple[str, str]]] = {
    "PlanExpiringSoon": _expiring,
    "BarbershopSuspended": _suspended,
}


def _owner_notices(payload: Mapping, text: Callable[[Mapping], tuple[str, str]]) -> list[Notice]:
    owners = payload.get("owners")
    if not isinstance(owners, list):
        raise InvalidEvent("payload.owners", "must be a list")
    title, body = text(payload)
    notices = []
    for i, owner in enumerate(owners):
        if not isinstance(owner, Mapping):
            raise InvalidEvent(f"payload.owners[{i}]", "must be an object")
        try:
            recipient = UUID(str(owner.get("userId")))
        except ValueError:
            raise InvalidEvent(f"payload.owners[{i}].userId", "must be a UUID") from None
        notices.append(Notice(recipient=recipient, type=NotificationType.SYSTEM, title=title, body=body[:BODY_MAX],
                              email=email_address(owner.get("email"), f"payload.owners[{i}].email"),
                              name=str(owner.get("fullName") or "").strip()))
    return notices


def notices_for(event_type: str, payload: Mapping) -> list[Notice]:
    """The notices of an event; empty when it has nobody to notify. Unhandled types are refused."""
    if event_type in _TO_OWNERS:
        return _owner_notices(payload, _TO_OWNERS[event_type])
    if event_type not in _HANDLED:
        raise UnsupportedEvent(event_type)
    field, text = _HANDLED[event_type]
    recipient = _recipient(payload, field)
    if recipient is None:
        return []
    kind, title, body = text(payload)
    return [Notice(recipient=recipient, type=kind, title=title, body=body,
                   email_looked_up=event_type in _E_MAILED_TO_CLIENT)]
