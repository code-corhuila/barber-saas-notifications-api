"""What the service needs to send an e-mail (DEC-NOTIF-01): only the password-reset code uses it."""
from typing import Protocol


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None:
        """Raises when the message was not accepted by the mail server; the caller decides what follows."""
        ...
