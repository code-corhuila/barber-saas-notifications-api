"""
The e-mails that carry a one-time code (DEC-NOTIF-01, DEC-NOTIF-02): the password-reset code and the
e-mail verification code. Each goes to the account's e-mail only, never to the inbox, and is never
stored. The texts are in Spanish because the user reads them.
"""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from notifications.domain.model import email_layout
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
    # The same message as HTML, with the code in a box (email_layout.py).
    html: str = ""


def _reset_text(code: str, expires: datetime) -> str:
    local = expires.astimezone(COLOMBIA)
    return (f"Tu código para cambiar la contraseña de BarberSaaS es: {code}\n\n"
            f"Vence a las {local:%H:%M} del {local:%d/%m/%Y} (hora de Colombia) y solo se puede usar una vez.\n\n"
            "Si no pediste este cambio, ignora este correo: tu contraseña sigue igual.")


def _verification_text(code: str, _: datetime) -> str:
    # identity-auth issues every verification code for 15 minutes (ADR-018).
    return (f"Tu código de verificación de BarberSaaS es {code}. Vence en 15 minutos.\n\n"
            "Si no creaste una cuenta en BarberSaaS, ignora este correo.")


def _reset_html(_: str, expires: datetime) -> tuple[str, str, str]:
    local = expires.astimezone(COLOMBIA)
    return ("Cambia tu contraseña", "Usa este código en la app para crear tu nueva contraseña:",
            f"Vence a las {local:%H:%M} del {local:%d/%m/%Y} (hora de Colombia) y solo se puede usar una vez.\n\n"
            "Si no pediste este cambio, ignora este correo: tu contraseña sigue igual.")


def _verification_html(_: str, __: datetime) -> tuple[str, str, str]:
    return ("Verifica tu correo", "Escribe este código en la app para activar tu cuenta:",
            "Vence en 15 minutos.\n\nSi no creaste una cuenta en BarberSaaS, ignora este correo.")


# event type → (subject, text after the greeting, (title, before the code, after the code) of the HTML)
_KINDS: dict[str, tuple[str, Callable[[str, datetime], str], Callable[[str, datetime], tuple[str, str, str]]]] = {
    "PasswordResetRequested": ("Código para cambiar tu contraseña", _reset_text, _reset_html),
    "EmailVerificationRequested": ("Tu código de verificación de BarberSaaS", _verification_text, _verification_html),
}
EVENT_TYPES = frozenset(_KINDS)


def _text(payload: Mapping, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InvalidEvent(f"payload.{field}", "is required")
    return value.strip()


def email_address(value: object, field: str) -> str:
    """An address safe to put in a header: no line break can smuggle another recipient in."""
    to = value.strip() if isinstance(value, str) else ""
    if "@" not in to or len(to) > EMAIL_MAX or any(c in to for c in "\r\n"):
        raise InvalidEvent(field, "must be an e-mail address")
    return to


def code_email(event_type: str, payload: Mapping) -> CodeEmail:
    """The e-mail of one code event (02-domain/domain-events.md, DEC-AUTH-08, DEC-AUTH-09)."""
    subject, text, html = _KINDS[event_type]
    try:
        user_id = UUID(_text(payload, "userId"))
    except ValueError:
        raise InvalidEvent("payload.userId", "must be a UUID") from None
    to = email_address(_text(payload, "email"), "payload.email")
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
    title, before, after = html(code, expires)
    page = email_layout.render(title, name, before, code=code, after=after)
    return CodeEmail(user_id=user_id, to=to, subject=subject, body=body, expires_at=expires, html=page)
