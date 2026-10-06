"""POST /api/v1/device-tokens: idempotent creation (norm 5.3.8) and validation (annex C)."""
from uuid import UUID

import pytest

from tests.conftest import ANA, LUIS, bearer, make_token

TOKENS = "/api/v1/device-tokens"
BODY = {"token": "fcm-device-token-example", "platform": "ANDROID"}


def register(client, body=BODY, key: str | None = "key-00000001", user: UUID = ANA):
    headers = bearer(make_token(sub=str(user)))
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post(TOKENS, json=body, headers=headers)


def test_the_first_registration_answers_201_with_its_location(client):
    response = register(client)

    assert response.status_code == 201
    created = response.json()
    UUID(created["id"])
    assert response.headers["Location"] == f"{TOKENS}/{created['id']}"
    assert {k: created[k] for k in ("userId", "token", "platform")} == {"userId": str(ANA), **BODY}
    assert created["createdAt"].endswith("Z") and created["updatedAt"].endswith("Z")


def test_a_retry_with_the_same_key_answers_200_and_the_same_id(client):
    first = register(client).json()

    retry = register(client)

    assert retry.status_code == 200 and retry.json()["id"] == first["id"]


def test_the_same_key_with_another_body_answers_422(client):
    register(client)

    response = register(client, {"token": "another-device", "platform": "IOS"})

    assert response.status_code == 422 and response.json()["error"] == "BUSINESS_RULE_VIOLATION"


def test_a_token_already_registered_moves_to_the_caller(client):
    theirs = register(client, user=LUIS, key="key-luis-0001").json()

    response = register(client, {**BODY, "platform": "IOS"}, key="key-ana-00001", user=ANA)

    assert response.status_code == 200
    assert response.json()["id"] == theirs["id"]
    assert (response.json()["userId"], response.json()["platform"]) == (str(ANA), "IOS")


def test_another_users_key_does_not_return_their_token(client):
    register(client, user=LUIS, key="shared-key-01")

    response = register(client, {"token": "ana-device", "platform": "ANDROID"}, key="shared-key-01", user=ANA)

    assert response.status_code == 422


@pytest.mark.parametrize("key", [None, "short"], ids=["missing", "too-short"])
def test_the_idempotency_key_is_required_with_8_to_128_characters(client, key):
    response = register(client, key=key)

    assert response.status_code == 400 and response.json()["error"] == "VALIDATION_ERROR"
    assert [d["field"] for d in response.json()["details"]] == ["Idempotency-Key"]


def test_details_name_every_invalid_field_including_the_key(client):
    response = register(client, {"token": "", "platform": "WEB", "extra": 1}, key=None)

    assert response.status_code == 400
    assert {d["field"] for d in response.json()["details"]} == {"Idempotency-Key", "token", "platform", "extra"}


def test_malformed_json_answers_400(client):
    headers = {**bearer(make_token()), "Idempotency-Key": "key-00000001", "Content-Type": "application/json"}

    response = client.post(TOKENS, content=b'{"token": ', headers=headers)

    assert response.status_code == 400 and response.json()["error"] == "VALIDATION_ERROR"


def test_a_service_token_registers_no_device(client):
    headers = {**bearer(make_token(sub="barber-saas-worker", role="SERVICE")), "Idempotency-Key": "key-00000001"}

    assert client.post(TOKENS, json=BODY, headers=headers).status_code == 403


def test_without_a_token_registration_answers_401(client):
    assert client.post(TOKENS, json=BODY, headers={"Idempotency-Key": "key-00000001"}).status_code == 401
