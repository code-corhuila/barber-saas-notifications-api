"""N-6: a new notification is pushed to the devices of its user; the push never decides the event."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from notifications.adapter.outbound.persistence.in_memory import (InMemoryDeviceTokenRepository,
                                                                  InMemoryNotificationRepository)
from notifications.adapter.outbound.system import RandomIds
from notifications.application.port.inbound.event_use_cases import EventOutcome, IncomingEvent
from notifications.application.port.outbound.device_token_repository import IdempotencyRecord
from notifications.application.port.outbound.push_sender import PushResult
from notifications.application.usecase.event_service import EventService
from notifications.application.usecase.push_delivery import PushDelivery
from notifications.domain.model.device_token import DeviceToken, Platform
from notifications.domain.model.notification import DeliveryStatus

NOW = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
ANA = UUID("11111111-1111-1111-1111-111111111111")


class Clock:
    def now(self) -> datetime:
        return NOW


class FakeSender:
    def __init__(self, answer: PushResult | Exception = PushResult(ok=True)) -> None:
        self.answer = answer
        self.sent: list[tuple[str, str, str, dict]] = []

    def send(self, token: str, title: str, body: str, data: dict) -> PushResult:
        self.sent.append((token, title, body, data))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def notifications() -> InMemoryNotificationRepository:
    return InMemoryNotificationRepository()


@pytest.fixture
def devices() -> InMemoryDeviceTokenRepository:
    return InMemoryDeviceTokenRepository()


def device(user: UUID, token: str, devices) -> DeviceToken:
    d = DeviceToken(id=uuid4(), user_id=user, token=token, platform=Platform.ANDROID, created_at=NOW, updated_at=NOW)
    devices.save(d, IdempotencyRecord(f"key-{uuid4()}", "POST /api/v1/device-tokens", d.id, "h"))
    return d


def confirmed(client: str | None = str(ANA), event_id: UUID | None = None) -> IncomingEvent:
    return IncomingEvent(id=event_id or uuid4(), type="AppointmentConfirmed", barbershop_id=None,
                         payload={"clientId": client, "date": "2026-10-10", "startTime": "10:00"})


def service(notifications, devices, sender) -> EventService:
    return EventService(notifications, Clock(), RandomIds(), PushDelivery(devices, notifications, sender, Clock()))


def only(notifications, user: UUID = ANA):
    [n] = notifications.page_of(user, None, 0, 10)[0]
    return n


def test_a_new_notification_is_pushed_to_every_device_of_its_user(notifications, devices):
    device(ANA, "phone", devices)
    device(ANA, "tablet", devices)
    device(uuid4(), "someone-else", devices)
    sender = FakeSender()

    assert service(notifications, devices, sender).receive(confirmed()) == EventOutcome.PROCESSED

    n = only(notifications)
    assert sorted(token for token, *_ in sender.sent) == ["phone", "tablet"]
    assert sender.sent[0][1:] == (n.title, n.body, {"notificationId": str(n.id), "type": "APPOINTMENT_CONFIRMATION"})
    assert [a.status for a in notifications.attempts_of(n.id)] == [DeliveryStatus.SENT, DeliveryStatus.SENT]


def test_without_devices_nothing_is_pushed(notifications, devices):
    sender = FakeSender()

    service(notifications, devices, sender).receive(confirmed())

    assert sender.sent == [] and notifications.attempts_of(only(notifications).id) == []


def test_a_duplicate_or_an_ignored_event_pushes_nothing(notifications, devices):
    device(ANA, "phone", devices)
    sender = FakeSender()
    events = service(notifications, devices, sender)
    event = confirmed()
    events.receive(event)
    sender.sent.clear()

    assert events.receive(event) == EventOutcome.DUPLICATE
    assert events.receive(confirmed(client=None)) == EventOutcome.IGNORED
    assert sender.sent == []


@pytest.mark.parametrize("answer, code", [
    (PushResult(ok=False, error_code="QUOTA_EXCEEDED"), "QUOTA_EXCEEDED"),
    (TimeoutError("fcm did not answer"), "UNAVAILABLE"),
])
def test_a_failed_push_is_recorded_and_the_event_is_still_processed(notifications, devices, answer, code):
    device(ANA, "phone", devices)

    outcome = service(notifications, devices, FakeSender(answer)).receive(confirmed())

    assert outcome == EventOutcome.PROCESSED
    [attempt] = notifications.attempts_of(only(notifications).id)
    assert (attempt.status, attempt.error_code, attempt.attempted_at) == (DeliveryStatus.FAILED, code, NOW)


def test_a_token_fcm_no_longer_knows_is_removed(notifications, devices):
    gone = device(ANA, "uninstalled", devices)

    service(notifications, devices, FakeSender(PushResult(ok=False, error_code="UNREGISTERED", token_invalid=True))) \
        .receive(confirmed())

    assert devices.find_by_id(gone.id) is None


def test_at_most_ten_attempts_are_kept_per_notification(notifications, devices):
    for i in range(12):
        device(ANA, f"device-{i}", devices)

    service(notifications, devices, FakeSender()).receive(confirmed())

    assert len(notifications.attempts_of(only(notifications).id)) == 10
