"""What the service offers to the worker: receive one domain event (ADR-016)."""
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class IncomingEvent:
    """The fields of the EventEnvelope this service uses (_shared.yaml 1.2.0)."""

    id: UUID
    type: str
    barbershop_id: UUID | None
    payload: Mapping[str, Any]


class EventOutcome(StrEnum):
    PROCESSED = "PROCESSED"
    DUPLICATE = "DUPLICATE"
    IGNORED = "IGNORED"


class EventUseCases(Protocol):
    def receive(self, event: IncomingEvent) -> EventOutcome: ...
