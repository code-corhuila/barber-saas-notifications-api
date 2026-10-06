"""Shared fixtures: a real RS256 key pair, a token factory and the app with in-memory adapters."""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from notifications.adapter.inbound.http.app import Services, create_app
from notifications.adapter.inbound.http.auth import Rs256Verifier
from notifications.adapter.outbound.persistence.in_memory import (InMemoryDeviceTokenRepository,
                                                                  InMemoryNotificationRepository)
from notifications.adapter.outbound.system import RandomIds
from notifications.application.usecase.device_token_service import DeviceTokenService
from notifications.application.usecase.event_service import EventService
from notifications.application.usecase.notification_service import NotificationService
from notifications.domain.model.notification import Notification, NotificationType

ISSUER = "barber-saas-identity-auth-api"
ANA = UUID("11111111-1111-1111-1111-111111111111")
LUIS = UUID("22222222-2222-2222-2222-222222222222")
T0 = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def _key_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    public = key.public_key().public_bytes(serialization.Encoding.PEM,
                                           serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


PRIVATE_KEY, PUBLIC_KEY = _key_pair()
OTHER_PRIVATE_KEY, _ = _key_pair()


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


def make_token(sub: str | None = str(ANA), role: str = "CLIENT", *, key: str | None = PRIVATE_KEY,
               alg: str = "RS256", expires_in: timedelta = timedelta(hours=1), **claims) -> str:
    now = datetime.now(timezone.utc)
    body = {"sub": sub, "role": role, "iss": ISSUER, "iat": now, "exp": now + expires_in, **claims}
    return jwt.encode({k: v for k, v in body.items() if v is not None}, key, algorithm=alg)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(T0 + timedelta(hours=1))


@pytest.fixture
def notifications() -> InMemoryNotificationRepository:
    return InMemoryNotificationRepository()


@pytest.fixture
def add_notification(notifications) -> Callable[..., Notification]:
    def add(user: UUID = ANA, minutes: int = 0, *, read: bool = False) -> Notification:
        at = T0 + timedelta(minutes=minutes)
        n = Notification(id=uuid4(), user_id=user, barbershop_id=None, title="Cita confirmada",
                         body="Tu cita del 10/10 a las 10:00 fue confirmada.",
                         type=NotificationType.APPOINTMENT_CONFIRMATION, read=read,
                         source_event_id=None, created_at=at, updated_at=at)
        notifications.add(n)
        return n
    return add


@pytest.fixture
def services(notifications, clock) -> Services:
    return Services(notifications=NotificationService(notifications, clock),
                    events=EventService(notifications, clock, RandomIds()),
                    device_tokens=DeviceTokenService(InMemoryDeviceTokenRepository(), clock, RandomIds()))


@pytest.fixture
def client(services) -> TestClient:
    return TestClient(create_app(services, Rs256Verifier(PUBLIC_KEY)), raise_server_exceptions=False)
