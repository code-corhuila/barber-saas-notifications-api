"""
The e-mails that carry a one-time code (DEC-NOTIF-01, DEC-NOTIF-02): the password-reset code and the
e-mail verification code. Each goes to the account's e-mail only, never to the inbox, and is never
stored. The texts are in Spanish because the user reads them.
"""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from notifications.domain.model.errors import InvalidEvent

# Colombia has no daylight saving time: a fixed offset avoids depending on a time zone database.
COLOMBIA = timezone(timedelta(hours=-5))
EMAIL_MAX = 150


@dataclass(frozen=True)
class CodeEmail:
    """What to send, and to whom. Holds the code only in memory, for the one send."""

    user_id: UUID
    to: str
    subject: str
    body: str
    expires_at: datetime


def _reset_text(code: str, expires: datetime) -> str:
    local = expires.astimezone(COLOMBIA)
    return (f"Tu código para cambiar la contraseña de BarberSaaS es: {code}\n\n"
            f"Vence a las {local:%H:%M} del {local:%d/%m/%Y} (hora de Colombia) y solo se puede usar una vez.\n\n"
            "Si no pediste este cambio, ignora este correo: tu contraseña sigue igual.")


def _verification_text(code: str, _: datetime) -> str:
    # identity-auth issues every verification code for 15 minutes (ADR-018).
    return (f"Tu código de verificación de BarberSaaS es {code}. Vence en 15 minutos.\n\n"
            "Si no creaste una cuenta en BarberSaaS, ignora este correo.")


# event type → (subject, text after the greeting)
_KINDS: dict[str, tuple[str, Callable[[str, datetime], str]]] = {
    "PasswordResetRequested": ("Código para cambiar tu contraseña", _reset_text),
    "EmailVerificationRequested": ("Tu código de verificación de BarberSaaS", _verification_text),
}
EVENT_TYPES = frozenset(_KINDS)


def _text(payload: Mapping, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InvalidEvent(f"payload.{field}", "is required")
    return value.strip()


def code_email(event_type: str, payload: Mapping) -> CodeEmail:
    """The e-mail of one code event (02-domain/domain-events.md, DEC-AUTH-08, DEC-AUTH-09)."""
    subject, text = _KINDS[event_type]
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
    body = f"Hola{' ' + name if name else ''},\n\n{text(code, expires)}"
    return CodeEmail(user_id=user_id, to=to, subject=subject, body=body, expires_at=expires)
