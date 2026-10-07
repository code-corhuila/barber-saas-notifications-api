"""
Firebase Cloud Messaging, HTTP v1 API. The service account comes from the environment only
(FCM_SERVICE_ACCOUNT_JSON, never versioned); its OAuth token is refreshed by google-auth.
"""
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping

from notifications.application.port.outbound.push_sender import PushResult

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
# Errors that mean the token itself is no longer valid, so it is forgotten.
INVALID_TOKEN = frozenset({"UNREGISTERED", "INVALID_ARGUMENT"})

Post = Callable[[str, dict, bytes, float], tuple[int, dict]]


def _post(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, dict]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read() or b"{}")
        except ValueError:
            return error.code, {}


class FcmPushSender:
    def __init__(self, project_id: str, access_token: Callable[[], str], *, post: Post = _post,
                 timeout_s: float = 5.0) -> None:
        self._url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        self._access_token = access_token
        self._post = post
        self._timeout_s = timeout_s

    def send(self, token: str, title: str, body: str, data: Mapping[str, str]) -> PushResult:
        message = {"message": {"token": token, "notification": {"title": title, "body": body}, "data": dict(data)}}
        headers = {"Authorization": f"Bearer {self._access_token()}", "Content-Type": "application/json"}
        status, answer = self._post(self._url, headers, json.dumps(message).encode(), self._timeout_s)
        if 200 <= status < 300:
            return PushResult(ok=True)
        error = answer.get("error", {}) if isinstance(answer, dict) else {}
        details = [d.get("errorCode") for d in error.get("details", []) if isinstance(d, dict) and d.get("errorCode")]
        code = details[0] if details else error.get("status") or f"HTTP_{status}"
        return PushResult(ok=False, error_code=code, token_invalid=code in INVALID_TOKEN)

    @classmethod
    def from_service_account(cls, service_account_json: str, *, timeout_s: float) -> "FcmPushSender":
        # Imported here: without push credentials the service never needs google-auth.
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        info = json.loads(service_account_json)
        credentials = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])

        def access_token() -> str:
            if not credentials.valid:
                credentials.refresh(Request())
            return credentials.token

        return cls(info["project_id"], access_token, timeout_s=timeout_s)
