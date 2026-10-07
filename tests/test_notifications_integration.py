"""
The MongoDB adapters against a real instance migrated by barber-saas-notifications-db (its strict
validators and unique indexes). Skipped unless TEST_MONGO_URL is set, e.g.
    TEST_MONGO_URL="mongodb://localhost:27017/?directConnection=true" pytest
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from notifications.adapter.outbound.persistence.mongo import (MongoDeviceTokenRepository,
                                                              MongoNotificationRepository, connect)
from notifications.application.port.outbound.device_token_repository import IdempotencyRecord
from notifications.domain.model.device_token import DeviceToken, Platform
from notifications.domain.model.notification import Notification, NotificationType

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
