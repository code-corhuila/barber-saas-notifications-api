"""
SMTP with the standard library (DEC-NOTIF-01). Host, port, user and password come from the
environment only (SMTP_*), never versioned. One connection per message: the only e-mail today is a
password-reset code, so there is no traffic to justify a pool.
"""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

SECURITY_MODES = ("starttls", "ssl", "none")


class SmtpEmailSender:
    def __init__(self, host: str, port: int, sender: str, *, username: str = "", password: str = "",
                 security: str = "starttls", timeout_s: float = 10.0) -> None:
        if security not in SECURITY_MODES:
            raise ValueError(f"SMTP_SECURITY must be one of {', '.join(SECURITY_MODES)}")
        if security == "none" and username:
            raise ValueError("SMTP_SECURITY=none would send SMTP_USERNAME and SMTP_PASSWORD in cleartext")
        self._host, self._port, self._sender = host, port, sender
        self._username, self._password = username, password
        self._security, self._timeout_s = security, timeout_s

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=False)
        message["Message-ID"] = make_msgid()
        message.set_content(body)
        context = ssl.create_default_context()
        if self._security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(self._host, self._port, timeout=self._timeout_s, context=context)
        else:
            server = smtplib.SMTP(self._host, self._port, timeout=self._timeout_s)
        with server:
            if self._security == "starttls":
                server.starttls(context=context)
            if self._username:
                server.login(self._username, self._password)
            server.send_message(message)
