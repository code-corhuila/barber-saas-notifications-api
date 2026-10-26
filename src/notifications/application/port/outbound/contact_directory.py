"""Where the service reads a user's e-mail when the event does not carry it (DEC-NOTIF-02, DEC-AUTH-10)."""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class Contact:
    email: str
    full_name: str


class ContactDirectory(Protocol):
    def contact_of(self, user_id: UUID) -> Contact | None:
        """None when no such user exists; raises when the directory cannot answer now."""
        ...
