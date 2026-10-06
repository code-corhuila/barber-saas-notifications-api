"""A device that receives push notifications (06-data/models.md §7, collection device_token)."""
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class Platform(StrEnum):
    ANDROID = "ANDROID"
    IOS = "IOS"


@dataclass(frozen=True)
class DeviceToken:
    id: UUID
    user_id: UUID
    token: str
    platform: Platform
    created_at: datetime
    updated_at: datetime

    def assign(self, user_id: UUID, platform: Platform, now: datetime) -> "DeviceToken":
        """The token is unique: the device now belongs to whoever registered it last."""
        if (self.user_id, self.platform) == (user_id, platform):
            return self
        return replace(self, user_id=user_id, platform=platform, updated_at=now)
