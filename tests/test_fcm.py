"""The FCM HTTP v1 adapter, with the HTTP call and the access token replaced by fakes."""
import json

import pytest

from notifications.adapter.outbound.push.fcm import FcmPushSender
from tests.conftest import PRIVATE_KEY


class FakePost:
    def __init__(self, status: int, answer: dict | None = None) -> None:
        self.status, self.answer = status, answer or {}
        self.calls: list[dict] = []

    def __call__(self, url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, dict]:
        self.calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout})
        return self.status, self.answer


def sender(post: FakePost) -> FcmPushSender:
    return FcmPushSender(project_id="barbersaas-dev", access_token=lambda: "oauth-token", post=post, timeout_s=4.0)


def test_sends_one_message_to_the_v1_endpoint_with_the_bearer_token():
    post = FakePost(200, {"name": "projects/barbersaas-dev/messages/1"})

    result = sender(post).send("device-token", "Cita confirmada", "Tu cita del 10/10 a las 10:00 fue confirmada.",
                               {"notificationId": "n-1", "type": "APPOINTMENT_CONFIRMATION"})

    assert result.ok
    [call] = post.calls
    assert call["url"] == "https://fcm.googleapis.com/v1/projects/barbersaas-dev/messages:send"
    assert call["headers"]["Authorization"] == "Bearer oauth-token"
    assert call["timeout"] == 4.0
    assert call["body"] == {"message": {
        "token": "device-token",
        "notification": {"title": "Cita confirmada", "body": "Tu cita del 10/10 a las 10:00 fue confirmada."},
        "data": {"notificationId": "n-1", "type": "APPOINTMENT_CONFIRMATION"},
    }}


@pytest.mark.parametrize("status, answer, code, invalid", [
    (404, {"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}}, "UNREGISTERED", True),
    (400, {"error": {"status": "INVALID_ARGUMENT", "details": [{"errorCode": "INVALID_ARGUMENT"}]}}, "INVALID_ARGUMENT", True),
    (429, {"error": {"status": "RESOURCE_EXHAUSTED"}}, "RESOURCE_EXHAUSTED", False),
    (503, {}, "HTTP_503", False),
])
def test_maps_the_fcm_errors(status, answer, code, invalid):
    result = sender(FakePost(status, answer)).send("t", "title", "body", {})

    assert (result.ok, result.error_code, result.token_invalid) == (False, code, invalid)


def test_builds_from_a_service_account_without_calling_google_yet():
    account = {"type": "service_account", "project_id": "barbersaas-dev", "private_key_id": "k1",
               "private_key": PRIVATE_KEY, "client_email": "push@barbersaas-dev.iam.gserviceaccount.com",
               "client_id": "1", "token_uri": "https://oauth2.googleapis.com/token"}

    built = FcmPushSender.from_service_account(json.dumps(account), timeout_s=3)

    assert built._url == "https://fcm.googleapis.com/v1/projects/barbersaas-dev/messages:send"
    assert built._timeout_s == 3
