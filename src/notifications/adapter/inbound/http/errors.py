"""
The single error envelope {error, message, details?, traceId} (norm 5.3.5), also for unknown
routes and malformed JSON. traceId is the request's X-Correlation-Id; a driver message or a stack
trace never reaches the client, it goes to the log with the same id.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from notifications.adapter.inbound.http.correlation import correlation_id
from notifications.domain.model.errors import (DeliveryUnavailable, DomainError, IdempotencyConflict, InvalidEvent,
                                              NotificationNotFound, UnsupportedEvent)

log = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list[dict] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details

    @classmethod
    def unauthorized(cls, message: str) -> "ApiError":
        return cls(401, "UNAUTHORIZED", message)

    @classmethod
    def forbidden(cls) -> "ApiError":
        return cls(403, "FORBIDDEN", "You are not allowed to perform this action")

    @classmethod
    def not_found(cls, message: str = "The requested resource does not exist") -> "ApiError":
        return cls(404, "NOT_FOUND", message)

    @classmethod
    def validation(cls, details: list[dict], message: str = "The request has invalid fields") -> "ApiError":
        return cls(400, "VALIDATION_ERROR", message, details)


def envelope(status: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    body = {"error": code, "message": message, "traceId": correlation_id.get()}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content=body)


def _field(location: tuple) -> str:
    """('query', 'limit') → limit; ('body', 'token') → token; the header keeps its own name."""
    parts = [str(p) for p in location[1:]] if location and location[0] in ("query", "path", "header", "body") \
        else [str(p) for p in location]
    return ".".join(parts) or "body"


def _domain_error(error: DomainError) -> ApiError:
    if isinstance(error, NotificationNotFound):
        return ApiError.not_found("The notification does not exist")
    if isinstance(error, IdempotencyConflict):
        return ApiError(422, "BUSINESS_RULE_VIOLATION", "The Idempotency-Key was already used for another request")
    if isinstance(error, UnsupportedEvent):
        return ApiError(422, "BUSINESS_RULE_VIOLATION", f"This service does not handle the event {error}")
    if isinstance(error, InvalidEvent):
        return ApiError.validation([{"field": error.field, "message": error.problem}], "The event is not valid")
    if isinstance(error, DeliveryUnavailable):
        # 503: the worker retries it with backoff (ADR-016) instead of marking the event failed.
        return ApiError(503, "SERVICE_UNAVAILABLE", "The event cannot be delivered now; retry later")
    log.error("unmapped domain error %s", type(error).__name__)
    return ApiError(500, "INTERNAL_ERROR", "Internal server error")


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, error: ApiError) -> JSONResponse:
        return envelope(error.status, error.code, error.message, error.details)

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, error: DomainError) -> JSONResponse:
        mapped = _domain_error(error)
        return envelope(mapped.status, mapped.code, mapped.message, mapped.details)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
        problems = error.errors()
        if any(p.get("type") == "json_invalid" for p in problems):
            return envelope(400, "VALIDATION_ERROR", "The body is not valid JSON")
        details = [{"field": _field(tuple(p.get("loc", ()))), "message": p.get("msg", "Invalid value")}
                   for p in problems]
        return envelope(400, "VALIDATION_ERROR", "The request has invalid fields", details)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, error: HTTPException) -> JSONResponse:
        # Starlette raises 404 for an unknown route and 405 for a known one with another method:
        # for the client, both are a route that does not exist.
        if error.status_code in (404, 405):
            return envelope(404, "NOT_FOUND", "The requested route does not exist")
        return envelope(error.status_code, "VALIDATION_ERROR", str(error.detail))
