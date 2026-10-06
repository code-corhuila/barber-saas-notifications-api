"""
X-Correlation-Id (norm 5.3.9): reused if received, generated otherwise, returned in the response,
written on every JSON log line and used as the error traceId. A pure ASGI middleware, outermost,
so it also answers the envelope when something fails unexpectedly.
"""
import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Correlation-Id"
MAX_LENGTH = 128

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
log = logging.getLogger(__name__)


class CorrelationMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        received = Headers(scope=scope).get(HEADER, "").strip()
        value = received if 0 < len(received) <= MAX_LENGTH and received.isprintable() else str(uuid4())
        token = correlation_id.set(value)
        started = False

        async def send_with_id(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                MutableHeaders(scope=message)[HEADER] = value
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            # The detail stays in the log with the traceId; the client never sees it (norm 5.3.5).
            log.exception("unhandled error")
            if not started:
                body = {"error": "INTERNAL_ERROR", "message": "Internal server error", "traceId": value}
                await JSONResponse(status_code=500, content=body)(scope, receive, send_with_id)
        finally:
            correlation_id.reset(token)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the correlation id of the request being served."""

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlationId": correlation_id.get(),
        }
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False)
