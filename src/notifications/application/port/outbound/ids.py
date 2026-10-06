"""New identifiers, as a port, so the use cases do not decide how ids are made."""
from typing import Protocol
from uuid import UUID


class IdGenerator(Protocol):
    def next(self) -> UUID: ...
