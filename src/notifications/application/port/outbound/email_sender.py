"""What the service needs to send an e-mail (DEC-NOTIF-01, DEC-NOTIF-02)."""
from typing import Protocol


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str, *, html: str = "") -> None:
        """Plain text, and the same message as HTML when given. Raises when the mail server did not
        accept it; the caller decides what follows."""
        ...
