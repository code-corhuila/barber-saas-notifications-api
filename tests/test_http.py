"""The HTTP checks of annex C (norm 5.3.12) against the server with in-memory adapters."""
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from tests.conftest import ANA, LUIS, OTHER_PRIVATE_KEY, bearer, make_token

INBOX = "/api/v1/notifications"


def assert_envelope(response, status: int, code: str) -> dict:
    assert response.status_code == status
    body = response.json()
    assert body["error"] == code and body["message"] and body["traceId"]
    return body


# ─── Authentication (norm 5.3.7) ─────────────────────────────────────────────

def test_health_answers_without_a_token(client):
    response = client.get("/health")
    assert response.status_code == 200 and response.json()["status"] == "ok"


def test_without_a_token_answers_401(client):
    assert_envelope(client.get(INBOX), 401, "UNAUTHORIZED")


@pytest.mark.parametrize("token", [
    make_token(alg="HS256", key="a-shared-secret-that-nobody-should-hold-anywhere"),
    make_token(alg="none", key=None),
    make_token(expires_in=timedelta(minutes=-5)),
    make_token(key=OTHER_PRIVATE_KEY),
    make_token(iss="someone-else"),
    make_token(sub=None),
    "not.a.token",
], ids=["hs256", "none", "expired", "other-key", "other-issuer", "no-sub", "malformed"])
def test_an_invalid_token_answers_401(client, token):
    assert_envelope(client.get(INBOX, headers=bearer(token)), 401, "UNAUTHORIZED")


def test_a_service_token_has_no_inbox(client):
    service = make_token(sub="barber-saas-worker", role="SERVICE")
    assert_envelope(client.get(INBOX, headers=bearer(service)), 403, "FORBIDDEN")


# ─── Error envelope and correlation (norms 5.3.5, 5.3.9) ─────────────────────

def test_the_error_repeats_the_correlation_id_received(client):
    response = client.get(INBOX, headers={"X-Correlation-Id": "trace-123"})
    assert assert_envelope(response, 401, "UNAUTHORIZED")["traceId"] == "trace-123"
    assert response.headers["X-Correlation-Id"] == "trace-123"


def test_a_correlation_id_is_generated_when_missing(client):
    response = client.get("/health")
    UUID(response.headers["X-Correlation-Id"])


def test_an_unknown_route_answers_404_with_the_envelope(client):
    response = client.get("/api/v1/nothing-here", headers={"X-Correlation-Id": "trace-404"})
    assert assert_envelope(response, 404, "NOT_FOUND")["traceId"] == "trace-404"


def test_a_malformed_id_answers_400(client):
    response = client.post(f"{INBOX}/not-a-uuid/read", headers=bearer(make_token()))
    body = assert_envelope(response, 400, "VALIDATION_ERROR")
    assert body["details"][0]["field"] == "id"


def test_an_unknown_notification_answers_404(client):
    assert_envelope(client.post(f"{INBOX}/{uuid4()}/read", headers=bearer(make_token())), 404, "NOT_FOUND")


# ─── List (norm 5.3.6) ───────────────────────────────────────────────────────

def test_the_list_is_data_and_meta_most_recent_first(client, add_notification):
    old, new = add_notification(ANA, 1), add_notification(ANA, 2)

    body = client.get(INBOX, headers=bearer(make_token())).json()

    assert [n["id"] for n in body["data"]] == [str(new.id), str(old.id)]
    assert body["meta"] == {"page": 1, "limit": 20, "total": 2, "totalPages": 1}


def test_the_list_holds_at_most_limit_items_and_repeats_page_and_limit(client, add_notification):
    for minute in range(3):
        add_notification(ANA, minute)

    body = client.get(INBOX, params={"page": 2, "limit": 2}, headers=bearer(make_token())).json()

    assert len(body["data"]) == 1
    assert body["meta"] == {"page": 2, "limit": 2, "total": 3, "totalPages": 2}


@pytest.mark.parametrize("params", [{"limit": 101}, {"limit": 0}, {"page": 0}, {"read": "maybe"}])
def test_an_out_of_range_query_answers_400(client, params):
    response = client.get(INBOX, params=params, headers=bearer(make_token()))
    assert assert_envelope(response, 400, "VALIDATION_ERROR")["details"][0]["field"] == next(iter(params))


def test_the_read_filter_works(client, add_notification):
    add_notification(ANA, 1)
    read = add_notification(ANA, 2, read=True)

    body = client.get(INBOX, params={"read": "true"}, headers=bearer(make_token())).json()

    assert [n["id"] for n in body["data"]] == [str(read.id)]


def test_a_notification_is_camel_case_with_rfc_3339_dates(client, add_notification):
    n = add_notification(ANA, 1)

    item = client.get(INBOX, headers=bearer(make_token())).json()["data"][0]

    assert item == {"id": str(n.id), "userId": str(ANA), "barbershopId": None, "title": n.title,
                    "body": n.body, "type": "APPOINTMENT_CONFIRMATION", "read": False,
                    "createdAt": "2026-10-06T12:01:00Z", "updatedAt": "2026-10-06T12:01:00Z"}


# ─── Isolation between users (HU-TENANT-001) ─────────────────────────────────

def test_a_user_does_not_see_another_users_notifications(client, add_notification):
    add_notification(LUIS, 1)

    body = client.get(INBOX, headers=bearer(make_token(sub=str(ANA)))).json()

    assert body["data"] == [] and body["meta"]["total"] == 0


def test_a_user_cannot_mark_another_users_notification(client, add_notification, notifications):
    theirs = add_notification(LUIS, 1)

    response = client.post(f"{INBOX}/{theirs.id}/read", headers=bearer(make_token(sub=str(ANA))))

    assert_envelope(response, 404, "NOT_FOUND")
    assert not notifications.find(LUIS, theirs.id).read


# ─── Mark as read ────────────────────────────────────────────────────────────

def test_marking_as_read_answers_the_notification_twice(client, add_notification):
    n = add_notification(ANA, 1)

    first = client.post(f"{INBOX}/{n.id}/read", headers=bearer(make_token()))
    second = client.post(f"{INBOX}/{n.id}/read", headers=bearer(make_token()))

    assert first.status_code == second.status_code == 200
    assert first.json()["read"] is True and first.json() == second.json()
