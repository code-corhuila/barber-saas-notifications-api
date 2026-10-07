"""What the service needs to reach a device outside the app (FCM, N-6)."""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PushResult:
    ok: bool
    error_code: str | None = None
    # The push service no longer knows this token (app uninstalled, token rotated): forget it.
    token_invalid: bool = False


class PushSender(Protocol):
    def send(self, token: str, title: str, body: str, data: Mapping[str, str]) -> PushResult:
        """May raise when the push service does not answer in time; the caller records it as failed."""
        ...
