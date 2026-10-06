"""The real clock and id generator behind the ports."""
from datetime import datetime, timezone
from uuid import UUID, uuid4


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class RandomIds:
    def next(self) -> UUID:
        return uuid4()
