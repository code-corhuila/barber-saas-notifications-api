"""The SMTP adapter against a minimal local SMTP server: what it sends is what a real server receives."""
import socket
import threading
from email import message_from_bytes, policy

import pytest

from notifications.adapter.outbound.email.smtp import SmtpEmailSender


class LocalSmtpServer:
    """Speaks just enough SMTP (no TLS, no auth) to accept one message per connection."""

    def __init__(self, reject_data: bool = False) -> None:
        self._socket = socket.create_server(("127.0.0.1", 0))
        self.port = self._socket.getsockname()[1]
        self.reject_data = reject_data
        self.messages: list[tuple[str, list[str], bytes]] = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                connection, _ = self._socket.accept()
            except OSError:
                return
            with connection, connection.makefile("rb") as reader:
                self._session(connection, reader)

    def _session(self, connection: socket.socket, reader) -> None:
        def reply(line: str) -> None:
            connection.sendall((line + "\r\n").encode())
        reply("220 localhost ESMTP test")
        sender, recipients = "", []
        while line := reader.readline():
            command = line.decode().strip()
            verb = command.split(" ", 1)[0].upper()
            if verb in ("EHLO", "HELO"):
                reply("250 localhost")
            elif verb == "MAIL":
                sender = command.split(":", 1)[1].strip(" <>")
                reply("250 OK")
            elif verb == "RCPT":
                recipients.append(command.split(":", 1)[1].strip(" <>"))
                reply("250 OK")
            elif verb == "DATA":
                if self.reject_data:
                    reply("554 rejected")
                    continue
                reply("354 go ahead")
                data = b""
                while (chunk := reader.readline()) not in (b".\r\n", b""):
                    data += chunk
                self.messages.append((sender, recipients, data))
                reply("250 OK queued")
            elif verb == "QUIT":
                reply("221 bye")
                return
            else:
                reply("250 OK")

    def close(self) -> None:
        self._socket.close()


@pytest.fixture
def server():
    s = LocalSmtpServer()
    yield s
    s.close()


def test_the_message_reaches_the_server_with_its_headers_and_text(server):
    sender = SmtpEmailSender("127.0.0.1", server.port, "BarberSaaS <no-reply@example.com>", security="none",
                             timeout_s=3)

    sender.send("ana@example.com", "Código para cambiar tu contraseña", "Tu código es: 482913")

    [(envelope_from, recipients, data)] = server.messages
    assert envelope_from == "no-reply@example.com" and recipients == ["ana@example.com"]
    message = message_from_bytes(data, policy=policy.default)
    assert message["To"] == "ana@example.com"
    assert message["Subject"] == "Código para cambiar tu contraseña"
    assert "482913" in message.get_content()


def test_a_refused_message_raises_so_the_event_is_retried():
    server = LocalSmtpServer(reject_data=True)
    sender = SmtpEmailSender("127.0.0.1", server.port, "no-reply@example.com", security="none", timeout_s=3)
    try:
        with pytest.raises(Exception):
            sender.send("ana@example.com", "s", "b")
    finally:
        server.close()


def test_an_unreachable_server_raises():
    closed = socket.create_server(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    sender = SmtpEmailSender("127.0.0.1", port, "no-reply@example.com", security="none", timeout_s=2)

    with pytest.raises(OSError):
        sender.send("ana@example.com", "s", "b")


def test_an_unknown_security_mode_is_refused_at_startup():
    with pytest.raises(ValueError):
        SmtpEmailSender("smtp.example.com", 587, "no-reply@example.com", security="tls")
