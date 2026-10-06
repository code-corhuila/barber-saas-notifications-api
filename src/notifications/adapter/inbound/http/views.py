"""Response objects: the entity is never serialized as it is (norm 5.3.4). JSON in camelCase."""
from datetime import datetime, timezone

from notifications.application.port.inbound.notification_use_cases import Page
from notifications.domain.model.device_token import DeviceToken
from notifications.domain.model.notification import Notification


def timestamp(moment: datetime) -> str:
    """RFC 3339, always in UTC (norm 5.3.5)."""
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def notification(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "userId": str(n.user_id),
        "barbershopId": str(n.barbershop_id) if n.barbershop_id else None,
        "title": n.title,
        "body": n.body,
        "type": n.type.value,
        "read": n.read,
        "createdAt": timestamp(n.created_at),
        "updatedAt": timestamp(n.updated_at),
    }


def page(result: Page[Notification]) -> dict:
    return {
        "data": [notification(n) for n in result.items],
        "meta": {"page": result.page, "limit": result.limit, "total": result.total,
                 "totalPages": result.total_pages},
    }


def device_token(d: DeviceToken) -> dict:
    return {
        "id": str(d.id),
        "userId": str(d.user_id),
        "token": d.token,
        "platform": d.platform.value,
        "createdAt": timestamp(d.created_at),
        "updatedAt": timestamp(d.updated_at),
    }
