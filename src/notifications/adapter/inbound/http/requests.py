"""Request bodies, validated at the edge; field names follow the contract (camelCase)."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventEnvelopeBody(BaseModel):
    """EventEnvelope of _shared.yaml 1.2.0. Fields are only ever added, so unknown ones are accepted."""

    model_config = ConfigDict(extra="allow")

    id: UUID
    type: str = Field(min_length=1)
    version: int = Field(ge=1)
    occurredAt: datetime
    aggregateType: str = Field(min_length=1)
    aggregateId: UUID
    barbershopId: UUID | None = None
    correlationId: str
    payload: dict[str, Any]
