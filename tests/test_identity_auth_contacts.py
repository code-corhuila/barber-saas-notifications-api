"""identity-auth's GET /internal/v1/users/{id}/contact (DEC-AUTH-10), read with the service token."""
from uuid import UUID

import pytest

from notifications.adapter.outbound.identity.http import IdentityAuthContacts
from notifications.application.port.outbound.contact_directory import Contact

ANA = UUID("11111111-1111-1111-1111-111111111111")
BASE = "http://identity-auth-api:8080"


class FakeGet:
    def __init__(self, status: int, answer: dict | None = None) -> None:
        self.status, self.answer = status, answer or {}
        self.calls: list[tuple[str, dict, float]] = []

    def __call__(self, url: str, headers: dict, timeout: float) -> tuple[int, dict]:
        self.calls.append((url, headers, timeout))
        return self.status, self.answer


def contacts(get: FakeGet) -> IdentityAuthContacts:
    return IdentityAuthContacts(BASE + "/", "service-token", get=get, timeout_s=3)


def test_reads_the_contact_with_the_service_token():
    get = FakeGet(200, {"userId": str(ANA), "fullName": "Ana Gómez", "email": "ana@example.com"})

    found = contacts(get).contact_of(ANA)

    assert found == Contact(email="ana@example.com", full_name="Ana Gómez")
    [(url, headers, timeout)] = get.calls
    assert url == f"{BASE}/internal/v1/users/{ANA}/contact"
    assert headers["Authorization"] == "Bearer service-token" and timeout == 3


def test_an_unknown_user_has_no_contact():
    assert contacts(FakeGet(404)).contact_of(ANA) is None


@pytest.mark.parametrize("get", [
    FakeGet(503), FakeGet(403), FakeGet(200, {"fullName": "Ana"}), FakeGet(200, {"email": 5}),
], ids=["unavailable", "forbidden", "no-email", "not-text"])
def test_any_other_answer_is_a_failure_the_caller_decides_on(get):
    with pytest.raises(RuntimeError):
        contacts(get).contact_of(ANA)
