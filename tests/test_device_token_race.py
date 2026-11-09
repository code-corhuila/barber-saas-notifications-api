"""Two registrations of one device at once (a sign-in sends its token twice): both answer, none fails."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from notifications.adapter.outbound.persistence.in_memory import InMemoryDeviceTokenRepository
from notifications.adapter.outbound.system import RandomIds
from notifications.application.port.outbound.device_token_repository import IdempotencyRecord, TokenTaken
from notifications.application.usecase.device_token_service import OPERATION, DeviceTokenService
from notifications.domain.model.device_token import DeviceToken, Platform
from tests.conftest import ANA, FixedClock

TOKEN = "fcm-device-token-example"
NOW = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)


class LateReader(InMemoryDeviceTokenRepository):
    """The race: lookups miss the token another request stored just before this one saves."""

    def __init__(self, misses: int) -> None:
        super().__init__()
        self.misses = misses

    def find_by_token(self, token: str):
        if self.misses:
            self.misses -= 1
            return None
        return super().find_by_token(token)


def stored_first(devices: InMemoryDeviceTokenRepository) -> DeviceToken:
    """The other request of the same sign-in commits its device first."""
    winner = DeviceToken(id=uuid4(), user_id=ANA, token=TOKEN, platform=Platform.ANDROID, created_at=NOW, updated_at=NOW)
    devices.save(winner, IdempotencyRecord("key-first-001", OPERATION, winner.id, "hash"))
    return winner


def test_the_request_that_loses_the_race_answers_with_the_stored_device():
    devices = LateReader(misses=1)
    winner = stored_first(devices)

    registration = DeviceTokenService(devices, FixedClock(NOW), RandomIds()).register(
        ANA, TOKEN, Platform.ANDROID, "key-second-01")

    assert registration.created is False and registration.device_token.id == winner.id
    assert [d.id for d in devices.tokens_of(ANA)] == [winner.id]


def test_a_race_that_never_settles_is_not_hidden():
    devices = LateReader(misses=99)
    stored_first(devices)

    with pytest.raises(TokenTaken):
        DeviceTokenService(devices, FixedClock(NOW), RandomIds()).register(ANA, TOKEN, Platform.ANDROID, "key-second-01")
