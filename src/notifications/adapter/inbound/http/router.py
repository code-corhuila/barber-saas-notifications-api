"""Routes of notification-service.yaml: HTTP to use case and back, nothing else."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from notifications.adapter.inbound.http import views
from notifications.adapter.inbound.http.auth import current_user
from notifications.application.port.inbound.notification_use_cases import NotificationUseCases, PageRequest

router = APIRouter()
User = Annotated[UUID, Depends(current_user)]


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
