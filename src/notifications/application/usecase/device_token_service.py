"""Register a device token, idempotently by key (norm 5.3.8) and unique by token."""
from hashlib import sha256
from uuid import UUID

from notifications.application.port.inbound.device_token_use_cases import Registration
from notifications.application.port.outbound.clock import Clock
from notifications.application.port.outbound.device_token_repository import DeviceTokenRepository, IdempotencyRecord
from notifications.application.port.outbound.ids import IdGenerator
from notifications.domain.model.device_token import DeviceToken, Platform
from notifications.domain.model.errors import IdempotencyConflict

OPERATION = "POST /api/v1/device-tokens"


class DeviceTokenService:
    def __init__(self, device_tokens: DeviceTokenRepository, clock: Clock, ids: IdGenerator) -> None:
        self._device_tokens = device_tokens
        self._clock = clock
        self._ids = ids

    def register(self, user_id: UUID, token: str, platform: Platform, idempotency_key: str) -> Registration:
        # The caller is part of the request: another user's key never returns their device.
        request_hash = sha256(f"{user_id}|{token}|{platform}".encode()).hexdigest()
        seen = self._device_tokens.key_record(idempotency_key, OPERATION)
        if seen is not None:
            if seen.request_hash != request_hash:
                raise IdempotencyConflict(idempotency_key)
            return Registration(self._device_tokens.find_by_id(seen.resource_id), created=False)

        now = self._clock.now()
        existing = self._device_tokens.find_by_token(token)
        if existing is not None:
            device = existing.assign(user_id, platform, now)
        else:
            device = DeviceToken(id=self._ids.next(), user_id=user_id, token=token, platform=platform,
                                 created_at=now, updated_at=now)
        self._device_tokens.save(device, IdempotencyRecord(idempotency_key, OPERATION, device.id, request_hash))
        return Registration(device, created=existing is None)
