"""
Which notification each domain event produces, and for whom (02-domain/domain-events.md, Event
Summary Table). The texts are in Spanish because the user reads them on screen.
"""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from notifications.domain.model.errors import InvalidEvent, UnsupportedEvent
from notifications.domain.model.notification import BODY_MAX, NotificationType


@dataclass(frozen=True)
class Notice:
    """What to tell, and to whom, before it becomes a notification of their inbox."""

    recipient: UUID
    type: NotificationType
    title: str
    body: str


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


def _when(payload: Mapping) -> str:
    """'2026-10-10' and '10:00' (or '10:00:00') → 'del 10/10 a las 10:00'."""
    try:
        day = date.fromisoformat(str(payload.get("date")))
    except ValueError:
        raise InvalidEvent("payload.date", "must be a date as YYYY-MM-DD") from None
    try:
        start = time.fromisoformat(str(payload.get("startTime")))
    except ValueError:
        raise InvalidEvent("payload.startTime", "must be a time as HH:mm") from None
    return f"del {day:%d/%m} a las {start:%H:%M}"


def _confirmed(p: Mapping) -> tuple[NotificationType, str, str]:
    return NotificationType.APPOINTMENT_CONFIRMATION, "Cita confirmada", f"Tu cita {_when(p)} fue confirmada."


def _cancelled(p: Mapping) -> tuple[NotificationType, str, str]:
    reason = str(p.get("cancelledReason") or "").strip()
    body = f"Tu cita {_when(p)} fue cancelada." + (f" Motivo: {reason}" if reason else "")
    return NotificationType.SYSTEM, "Cita cancelada", body[:BODY_MAX]


def _completed(p: Mapping) -> tuple[NotificationType, str, str]:
    return NotificationType.SYSTEM, "Cita completada", f"Gracias por tu visita. Tu cita {_when(p)} quedó completada."


def _reminder(p: Mapping) -> tuple[NotificationType, str, str]:
    return NotificationType.REMINDER, "Recordatorio de cita", f"Recuerda tu cita {_when(p)}."


def _sticker(_: Mapping) -> tuple[NotificationType, str, str]:
    return NotificationType.SYSTEM, "Ganaste un sello", "Sumaste un sello en tu tarjeta de fidelidad."


def _reward(_: Mapping) -> tuple[NotificationType, str, str]:
    return NotificationType.SYSTEM, "Recompensa canjeada", "Canjeaste tu recompensa: el cupón se aplica en tu próxima cita."


# event type → (payload field of the recipient, text). PasswordResetRequested is not here: it is an
# e-mail, never an inbox notification (DEC-NOTIF-01, password_reset.py).
_HANDLED: dict[str, tuple[str, Callable[[Mapping], tuple[NotificationType, str, str]]]] = {
    "AppointmentConfirmed": ("clientId", _confirmed),
    "AppointmentCancelled": ("clientId", _cancelled),
    "AppointmentCompleted": ("clientId", _completed),
    "AppointmentReminderDue": ("clientId", _reminder),
    "StickerGranted": ("clientId", _sticker),
    "RewardRedeemed": ("clientId", _reward),
}


def notice_for(event_type: str, payload: Mapping) -> Notice | None:
    """The notice of an event; None when it has nobody to notify. Unhandled types are refused."""
    if event_type not in _HANDLED:
        raise UnsupportedEvent(event_type)
    field, text = _HANDLED[event_type]
    recipient = _recipient(payload, field)
    if recipient is None:
        return None
    kind, title, body = text(payload)
    return Notice(recipient=recipient, type=kind, title=title, body=body)
