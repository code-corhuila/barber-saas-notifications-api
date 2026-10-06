"""The current moment, as a port, so the use cases can be tested at a fixed time."""
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Always timezone-aware, in UTC."""
        ...
