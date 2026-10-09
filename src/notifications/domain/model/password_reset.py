"""
The password-reset e-mail of PasswordResetRequested (DEC-NOTIF-01): the code goes to the account's
e-mail only, never to the inbox, and is never stored. The texts are in Spanish because the user
reads them.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from notifications.domain.model.errors import InvalidEvent

EVENT_TYPE = "PasswordResetRequested"
# Colombia has no daylight saving time: a fixed offset avoids depending on a time zone database.
COLOMBIA = timezone(timedelta(hours=-5))
EMAIL_MAX = 150


@dataclass(frozen=True)
class ResetEmail:
    """What to send, and to whom. Holds the code only in memory, for the one send."""

    user_id: UUID
    to: str
    subject: str
    body: str
    expires_at: datetime


def _text(payload: Mapping, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InvalidEvent(f"payload.{field}", "is required")
    return value.strip()


def reset_email(payload: Mapping) -> ResetEmail:
    """The e-mail of one PasswordResetRequested payload (02-domain/domain-events.md, DEC-AUTH-08)."""
    try:
        user_id = UUID(_text(payload, "userId"))
    except ValueError:
        raise InvalidEvent("payload.userId", "must be a UUID") from None
    to = _text(payload, "email")
    if "@" not in to or len(to) > EMAIL_MAX or any(c in to for c in "\r\n"):
        raise InvalidEvent("payload.email", "must be an e-mail address")
    code = _text(payload, "code")
    if not (len(code) == 6 and code.isdigit()):
        raise InvalidEvent("payload.code", "must be 6 digits")
    try:
        expires = datetime.fromisoformat(_text(payload, "expiresAt").replace("Z", "+00:00"))
    except ValueError:
        raise InvalidEvent("payload.expiresAt", "must be a date-time") from None
    if expires.tzinfo is None:
        raise InvalidEvent("payload.expiresAt", "must carry its offset")
    name = str(payload.get("fullName") or "").strip()
    local = expires.astimezone(COLOMBIA)
    body = (f"Hola{' ' + name if name else ''},\n\n"
            f"Tu código para cambiar la contraseña de BarberSaaS es: {code}\n\n"
            f"Vence a las {local:%H:%M} del {local:%d/%m/%Y} (hora de Colombia) y solo se puede usar una vez.\n\n"
            "Si no pediste este cambio, ignora este correo: tu contraseña sigue igual.")
    return ResetEmail(user_id=user_id, to=to, subject="Código para cambiar tu contraseña", body=body,
                      expires_at=expires)
