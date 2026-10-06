"""The FastAPI application, built from the use cases the composition root hands over."""
from dataclasses import dataclass

from fastapi import FastAPI

from notifications.adapter.inbound.http import errors
from notifications.adapter.inbound.http.auth import Rs256Verifier
from notifications.adapter.inbound.http.correlation import CorrelationMiddleware
from notifications.adapter.inbound.http.router import router
from notifications.application.port.inbound.device_token_use_cases import DeviceTokenUseCases
from notifications.application.port.inbound.event_use_cases import EventUseCases
from notifications.application.port.inbound.notification_use_cases import NotificationUseCases


@dataclass(frozen=True)
class Services:
    notifications: NotificationUseCases
    events: EventUseCases
    device_tokens: DeviceTokenUseCases


def create_app(services: Services, verifier: Rs256Verifier) -> FastAPI:
    # No interactive docs: the contract is notification-service.yaml in barber-saas-docs.
    app = FastAPI(title="barber-saas-notifications-api", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.services = services
    app.state.verifier = verifier
    errors.install(app)
    app.include_router(router)
    app.add_middleware(CorrelationMiddleware)
    return app
