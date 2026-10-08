"""
Events handled without a notification of their own (06-data/models.md §10, processed_event): the
event id, its type and when — never its payload, so a reset code is never stored.
"""
from datetime import datetime
from typing import Protocol
from uuid import UUID


class ProcessedEventRepository(Protocol):
    def seen(self, event_id: UUID) -> bool: ...

    def record(self, event_id: UUID, event_type: str, processed_at: datetime) -> None:
        """Recording an event already recorded is not an error: two deliveries may race."""
        ...
