"""
identity-auth's GET /internal/v1/users/{id}/contact (DEC-AUTH-10), with this service's token
(SERVICE_TOKEN, sub barber-saas-notifications-api). Only on the internal compose network.
"""
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from uuid import UUID

from notifications.adapter.inbound.http.correlation import HEADER, correlation_id
from notifications.application.port.outbound.contact_directory import Contact

Get = Callable[[str, dict, float], tuple[int, dict]]


def _get(url: str, headers: dict, timeout: float) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, {}


class IdentityAuthContacts:
    def __init__(self, base_url: str, service_token: str, *, get: Get = _get, timeout_s: float = 3.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = service_token
        self._get = get
        self._timeout_s = timeout_s

    def contact_of(self, user_id: UUID) -> Contact | None:
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json",
                   HEADER: correlation_id.get()}
        status, answer = self._get(f"{self._base_url}/internal/v1/users/{user_id}/contact", headers,
                                   self._timeout_s)
        if status == 404:
            return None
        if status != 200:
            raise RuntimeError(f"identity-auth answered {status}")
        email, name = answer.get("email"), answer.get("fullName")
        if not isinstance(email, str) or not isinstance(name, str):
            raise RuntimeError("identity-auth answered a contact without email or fullName")
        return Contact(email=email, full_name=name)
