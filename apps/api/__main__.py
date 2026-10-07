"""
Composition root: the only place that knows every concrete type and every explicit limit
(norm 5.3.10). Run with `python -m apps.api`.
"""
import logging
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI

from notifications.adapter.inbound.http.app import Services, create_app
from notifications.adapter.inbound.http.auth import Rs256Verifier
from notifications.adapter.inbound.http.correlation import JsonFormatter
from notifications.adapter.outbound.persistence.in_memory import (InMemoryDeviceTokenRepository,
                                                                  InMemoryNotificationRepository)
from notifications.adapter.outbound.persistence.mongo import (MongoDeviceTokenRepository,
                                                              MongoNotificationRepository, connect)
from notifications.adapter.outbound.system import RandomIds, UtcClock
from notifications.application.usecase.device_token_service import DeviceTokenService
from notifications.application.usecase.event_service import EventService
from notifications.application.usecase.notification_service import NotificationService

log = logging.getLogger("notifications")


@dataclass(frozen=True)
class Settings:
    jwt_public_key: str
    port: int = 8080
    # Idle keep-alive connection is closed after this many seconds.
    keep_alive_timeout_s: int = 5
    # On SIGTERM, requests in flight get this long to finish before the process exits.
    graceful_shutdown_s: int = 10
    # Above this many concurrent connections the server answers 503 instead of queueing.
    max_concurrency: int = 200
    # Empty: in-memory repositories (nothing survives a restart). Set: MongoDB as notifications_app.
    mongo_url: str = ""
    mongo_database: str = "notifications"
    mongo_pool_max: int = 10
    # Each operation, and the wait for a pooled connection, ends after this many milliseconds.
    mongo_timeout_ms: int = 5000
    mongo_server_selection_timeout_ms: int = 3000

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        def number(name: str, default: int) -> int:
            return int(env.get(name) or default)
        return cls(jwt_public_key=env.get("JWT_PUBLIC_KEY", ""),
                   port=number("PORT", cls.port),
                   keep_alive_timeout_s=number("HTTP_KEEP_ALIVE_TIMEOUT_S", cls.keep_alive_timeout_s),
                   graceful_shutdown_s=number("HTTP_GRACEFUL_SHUTDOWN_S", cls.graceful_shutdown_s),
                   max_concurrency=number("HTTP_MAX_CONCURRENCY", cls.max_concurrency),
                   mongo_url=env.get("MONGO_URL", ""),
                   mongo_database=env.get("MONGO_DATABASE") or cls.mongo_database,
                   mongo_pool_max=number("MONGO_POOL_MAX", cls.mongo_pool_max),
                   mongo_timeout_ms=number("MONGO_TIMEOUT_MS", cls.mongo_timeout_ms),
                   mongo_server_selection_timeout_ms=number("MONGO_SERVER_SELECTION_TIMEOUT_MS",
                                                            cls.mongo_server_selection_timeout_ms))


def build_app(settings: Settings) -> FastAPI:
    clock, ids = UtcClock(), RandomIds()
    if settings.mongo_url:
        client = connect(settings.mongo_url, pool_max=settings.mongo_pool_max, timeout_ms=settings.mongo_timeout_ms,
                         server_selection_timeout_ms=settings.mongo_server_selection_timeout_ms)
        database = client[settings.mongo_database]
        notifications = MongoNotificationRepository(database)
        devices = MongoDeviceTokenRepository(client, database)
    else:
        notifications = InMemoryNotificationRepository()
        devices = InMemoryDeviceTokenRepository()
    services = Services(notifications=NotificationService(notifications, clock),
                        events=EventService(notifications, clock, ids),
                        device_tokens=DeviceTokenService(devices, clock, ids))
    return create_app(services, Rs256Verifier(settings.jwt_public_key))


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def main() -> None:
    configure_logging()
    settings = Settings.from_env(os.environ)
    app = build_app(settings)
    log.info("notifications-api listening on port %s", settings.port)
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_config=None, access_log=False,
                timeout_keep_alive=settings.keep_alive_timeout_s,
                timeout_graceful_shutdown=settings.graceful_shutdown_s,
                limit_concurrency=settings.max_concurrency)


if __name__ == "__main__":
    main()
