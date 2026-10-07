"""
The MongoDB adapters against a real instance migrated by barber-saas-notifications-db (its strict
validators and unique indexes). Skipped unless TEST_MONGO_URL is set, e.g.
    TEST_MONGO_URL="mongodb://localhost:27017/?directConnection=true" pytest
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.__main__ import Settings, build_app
from tests.conftest import PUBLIC_KEY, bearer, make_token

from notifications.adapter.outbound.persistence.mongo import (MongoDeviceTokenRepository,
                                                              MongoNotificationRepository, connect)
from notifications.application.port.outbound.device_token_repository import IdempotencyRecord
from notifications.domain.model.device_token import DeviceToken, Platform
from notifications.domain.model.notification import (DeliveryAttempt, DeliveryChannel, DeliveryStatus, Notification,
                                                     NotificationType)

URL = os.environ.get("TEST_MONGO_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_MONGO_URL is not set")

T0 = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def database():
    client = connect(URL, pool_max=5, timeout_ms=5000, server_selection_timeout_ms=3000)
    yield client, client[os.environ.get("TEST_MONGO_DATABASE", "notifications")]
    client.close()


@pytest.fixture
def notifications(database) -> MongoNotificationRepository:
    return MongoNotificationRepository(database[1])


@pytest.fixture
def devices(database) -> MongoDeviceTokenRepository:
    return MongoDeviceTokenRepository(*database)


def notification(user: UUID, minutes: int, *, read: bool = False, source: UUID | None = None) -> Notification:
    at = T0 + timedelta(minutes=minutes)
    return Notification(id=uuid4(), user_id=user, barbershop_id=uuid4(), title="Cita confirmada",
                        body="Tu cita del 10/10 a las 10:00 fue confirmada.",
                        type=NotificationType.APPOINTMENT_CONFIRMATION, read=read,
                        source_event_id=source, created_at=at, updated_at=at)


def test_a_notification_round_trips_with_every_field(notifications):
    user = uuid4()
    n = notification(user, 1, source=uuid4())

    assert notifications.add_unless_seen(n)

    assert notifications.find(user, n.id) == n


def test_the_inbox_is_the_users_own_most_recent_first_and_paged(notifications):
    user, other = uuid4(), uuid4()
    mine = [notification(user, minute, read=minute == 2) for minute in range(3)]
    for n in [*mine, notification(other, 9)]:
        notifications.add(n)

    page, total = notifications.page_of(user, None, 0, 2)
    unread, unread_total = notifications.page_of(user, False, 0, 10)

    assert [n.id for n in page] == [mine[2].id, mine[1].id] and total == 3
    assert [n.id for n in unread] == [mine[1].id, mine[0].id] and unread_total == 2
    assert notifications.find(other, mine[0].id) is None


def test_the_unique_index_refuses_a_second_notification_of_the_same_event(notifications):
    user, event = uuid4(), uuid4()

    assert notifications.add_unless_seen(notification(user, 1, source=event))
    assert not notifications.add_unless_seen(notification(user, 2, source=event))
    assert notifications.page_of(user, None, 0, 10)[1] == 1


def test_marking_as_read_is_saved(notifications):
    user = uuid4()
    n = notification(user, 1)
    notifications.add(n)

    notifications.save(n.mark_read(T0 + timedelta(hours=1)))

    assert notifications.find(user, n.id).read


def test_a_device_token_is_saved_with_its_key_and_found_again(devices):
    device = DeviceToken(id=uuid4(), user_id=uuid4(), token=f"fcm-{uuid4()}", platform=Platform.ANDROID,
                         created_at=T0, updated_at=T0)
    key = IdempotencyRecord(f"key-{uuid4()}", "POST /api/v1/device-tokens", device.id, "hash")

    devices.save(device, key)

    assert devices.find_by_id(device.id) == device
    assert devices.find_by_token(device.token) == device
    assert devices.key_record(key.key, key.operation) == key


def test_moving_a_device_to_another_user_keeps_one_document(devices):
    device = DeviceToken(id=uuid4(), user_id=uuid4(), token=f"fcm-{uuid4()}", platform=Platform.ANDROID,
                         created_at=T0, updated_at=T0)
    devices.save(device, IdempotencyRecord(f"key-{uuid4()}", "POST /api/v1/device-tokens", device.id, "a"))
    moved = device.assign(uuid4(), Platform.IOS, T0 + timedelta(hours=1))

    devices.save(moved, IdempotencyRecord(f"key-{uuid4()}", "POST /api/v1/device-tokens", device.id, "b"))

    assert devices.find_by_token(device.token) == moved


def test_the_service_on_mongodb_notifies_once_per_event_end_to_end():
    app = build_app(Settings.from_env({"JWT_PUBLIC_KEY": PUBLIC_KEY, "MONGO_URL": URL,
                                       "MONGO_DATABASE": os.environ.get("TEST_MONGO_DATABASE", "notifications")}))
    client, user = TestClient(app), uuid4()
    event = {"id": str(uuid4()), "type": "AppointmentConfirmed", "version": 1, "occurredAt": "2026-10-06T15:00:00Z",
             "aggregateType": "appointment", "aggregateId": str(uuid4()), "correlationId": "it",
             "payload": {"clientId": str(user), "date": "2026-10-10", "startTime": "10:00"}}
    worker = bearer(make_token(sub="barber-saas-worker", role="SERVICE"))

    first = client.post("/internal/v1/events", json=event, headers=worker).json()["outcome"]
    again = client.post("/internal/v1/events", json=event, headers=worker).json()["outcome"]
    inbox = client.get("/api/v1/notifications", headers=bearer(make_token(sub=str(user)))).json()

    assert (first, again) == ("PROCESSED", "DUPLICATE")
    assert inbox["meta"]["total"] == 1
    assert inbox["data"][0]["body"] == "Tu cita del 10/10 a las 10:00 fue confirmada."


def test_delivery_attempts_fit_the_validator_and_stay_bounded(notifications, database):
    n = notification(uuid4(), 1)
    notifications.add(n)

    for i in range(12):
        notifications.record_delivery(n.id, DeliveryAttempt(DeliveryChannel.PUSH, DeliveryStatus.FAILED,
                                                             T0 + timedelta(seconds=i), error_code=f"E{i}"))
    notifications.record_delivery(n.id, DeliveryAttempt(DeliveryChannel.PUSH, DeliveryStatus.SENT, T0))

    stored = database[1]["notification"].find_one({"_id": str(n.id)})["deliveryAttempts"]
    assert len(stored) == 10
    assert stored[-1] == {"channel": "PUSH", "status": "SENT", "attemptedAt": T0}
    assert stored[0]["errorCode"] == "E3"


def test_the_devices_of_a_user_are_found_and_one_is_removed(devices):
    user = uuid4()
    mine = [DeviceToken(id=uuid4(), user_id=user, token=f"fcm-{uuid4()}", platform=Platform.ANDROID,
                        created_at=T0, updated_at=T0) for _ in range(2)]
    for d in mine:
        devices.save(d, IdempotencyRecord(f"key-{uuid4()}", "POST /api/v1/device-tokens", d.id, "h"))

    assert sorted(d.id for d in devices.tokens_of(user)) == sorted(d.id for d in mine)
    devices.remove(mine[0].id)
    assert [d.id for d in devices.tokens_of(user)] == [mine[1].id]
