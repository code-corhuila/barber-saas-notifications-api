"""What the service needs to send an e-mail (DEC-NOTIF-01, DEC-NOTIF-02)."""
from typing import Protocol


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None:
        """Raises when the message was not accepted by the mail server; the caller decides what follows."""
        ...
