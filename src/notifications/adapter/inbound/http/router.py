"""Routes of notification-service.yaml: HTTP to use case and back, nothing else."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse

from notifications.adapter.inbound.http import views
from notifications.adapter.inbound.http.auth import current_user, service
from notifications.adapter.inbound.http.requests import EventEnvelopeBody, RegisterDeviceTokenBody
from notifications.application.port.inbound.event_use_cases import IncomingEvent
from notifications.application.port.inbound.notification_use_cases import NotificationUseCases, PageRequest
from notifications.domain.model.device_token import Platform

router = APIRouter()
User = Annotated[UUID, Depends(current_user)]
WORKER = "barber-saas-worker"


def _notifications(request: Request) -> NotificationUseCases:
    return request.app.state.services.notifications


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": views.timestamp(datetime.now(timezone.utc))}


@router.get("/api/v1/notifications")
def list_notifications(request: Request, user: User,
                       page: Annotated[int, Query(ge=1)] = 1,
                       limit: Annotated[int, Query(ge=1, le=100)] = 20,
                       read: bool | None = None) -> dict:
    return views.page(_notifications(request).list_mine(user, read, PageRequest(page=page, limit=limit)))


@router.post("/api/v1/notifications/{id}/read")
def mark_notification_read(request: Request, user: User, id: UUID) -> dict:
    return views.notification(_notifications(request).mark_read(user, id))


@router.post("/api/v1/device-tokens")
def register_device_token(request: Request, user: User, body: RegisterDeviceTokenBody,
                          idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8,
                                                                 max_length=128)]) -> JSONResponse:
    result = request.app.state.services.device_tokens.register(user, body.token, Platform(body.platform),
                                                               idempotency_key)
    view = views.device_token(result.device_token)
    if result.created:
        return JSONResponse(status_code=201, content=view, headers={"Location": f"/api/v1/device-tokens/{view['id']}"})
    return JSONResponse(status_code=200, content=view)


@router.post("/internal/v1/events", dependencies=[Depends(service(WORKER))])
def receive_event(request: Request, event: EventEnvelopeBody) -> dict:
    outcome = request.app.state.services.events.receive(
        IncomingEvent(id=event.id, type=event.type, barbershop_id=event.barbershopId, payload=event.payload))
    return {"eventId": str(event.id), "outcome": outcome.value}
