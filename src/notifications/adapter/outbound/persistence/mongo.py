"""
MongoDB adapters behind the same ports as the in-memory ones (06-data/models.md §7 and §10). The
collections, their validators and unique indexes belong to barber-saas-notifications-db; the service
connects as notifications_app and never creates or migrates anything.
"""
from datetime import datetime, timezone
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, MongoClient, WriteConcern
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from notifications.application.port.outbound.device_token_repository import IdempotencyRecord
from notifications.domain.model.device_token import DeviceToken, Platform
from notifications.domain.model.notification import (MAX_DELIVERY_ATTEMPTS, DeliveryAttempt, Notification,
                                                     NotificationType)

SOURCE_EVENT_INDEX = "uq_notification_source_event"


def connect(url: str, *, pool_max: int, timeout_ms: int, server_selection_timeout_ms: int) -> MongoClient:
    """Every limit declared (norm 5.3.10): pool size, wait for a connection, per-operation time."""
    return MongoClient(url, tz_aware=True, uuidRepresentation="standard", maxPoolSize=pool_max,
                       waitQueueTimeoutMS=timeout_ms, timeoutMS=timeout_ms,
                       serverSelectionTimeoutMS=server_selection_timeout_ms, w="majority", appname="notifications-api")


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc)


def _id(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


class MongoNotificationRepository:
    def __init__(self, database: Database) -> None:
        self._collection = database.get_collection("notification", write_concern=WriteConcern(w="majority"))

    def add(self, notification: Notification) -> None:
        self._collection.insert_one(self._document(notification))

    def add_unless_seen(self, notification: Notification) -> bool:
        # The unique index decides, not a read before the write: two deliveries at once notify once.
        try:
            self._collection.insert_one(self._document(notification))
        except DuplicateKeyError as error:
            if SOURCE_EVENT_INDEX in str(error.details or error):
                return False
            raise
        return True

    def save(self, notification: Notification) -> None:
        self._collection.update_one({"_id": str(notification.id), "userId": str(notification.user_id)},
                                    {"$set": {"read": notification.read, "updatedAt": _utc(notification.updated_at)}})

    def record_delivery(self, notification_id: UUID, attempt: DeliveryAttempt) -> None:
        entry = {"channel": attempt.channel.value, "status": attempt.status.value,
                 "attemptedAt": _utc(attempt.attempted_at)}
        if attempt.error_code:
            entry["errorCode"] = attempt.error_code
        # $slice keeps the array bounded, as the validator requires (maxItems 10).
        self._collection.update_one({"_id": str(notification_id)},
                                    {"$push": {"deliveryAttempts": {"$each": [entry], "$slice": -MAX_DELIVERY_ATTEMPTS}}})

    def find(self, user_id: UUID, notification_id: UUID) -> Notification | None:
        found = self._collection.find_one({"_id": str(notification_id), "userId": str(user_id)})
        return self._notification(found) if found else None

    def page_of(self, user_id: UUID, read: bool | None, offset: int, limit: int) -> tuple[list[Notification], int]:
        query: dict = {"userId": str(user_id)}
        if read is not None:
            query["read"] = read
        total = self._collection.count_documents(query)
        cursor = (self._collection.find(query).sort([("createdAt", DESCENDING), ("_id", DESCENDING)])
                  .skip(offset).limit(limit))
        return [self._notification(d) for d in cursor], total

    @staticmethod
    def _document(n: Notification) -> dict:
        return {"_id": str(n.id), "userId": str(n.user_id), "barbershopId": _id(n.barbershop_id), "title": n.title,
                "body": n.body, "type": n.type.value, "read": n.read, "sourceEventId": _id(n.source_event_id),
                "createdAt": _utc(n.created_at), "updatedAt": _utc(n.updated_at), "createdBy": None}

    @staticmethod
    def _notification(d: dict) -> Notification:
        return Notification(id=UUID(d["_id"]), user_id=UUID(d["userId"]),
                            barbershop_id=UUID(d["barbershopId"]) if d.get("barbershopId") else None,
                            title=d["title"], body=d["body"], type=NotificationType(d["type"]), read=d["read"],
                            source_event_id=UUID(d["sourceEventId"]) if d.get("sourceEventId") else None,
                            created_at=d["createdAt"], updated_at=d["updatedAt"])


class MongoDeviceTokenRepository:
    OPERATION_KEY = [("key", ASCENDING), ("operation", ASCENDING)]

    def __init__(self, client: MongoClient, database: Database) -> None:
        self._client = client
        majority = WriteConcern(w="majority")
        self._devices = database.get_collection("device_token", write_concern=majority)
        self._keys = database.get_collection("idempotency_key", write_concern=majority)

    def find_by_id(self, device_token_id: UUID) -> DeviceToken | None:
        found = self._devices.find_one({"_id": str(device_token_id)})
        return self._device(found) if found else None

    def find_by_token(self, token: str) -> DeviceToken | None:
        found = self._devices.find_one({"token": token})
        return self._device(found) if found else None

    def key_record(self, key: str, operation: str) -> IdempotencyRecord | None:
        found = self._keys.find_one({"key": key, "operation": operation})
        if not found:
            return None
        return IdempotencyRecord(found["key"], found["operation"], UUID(found["resourceId"]), found["requestHash"])

    def tokens_of(self, user_id: UUID) -> list[DeviceToken]:
        return [self._device(d) for d in self._devices.find({"userId": str(user_id)})]

    def remove(self, device_token_id: UUID) -> None:
        self._devices.delete_one({"_id": str(device_token_id)})

    def save(self, device_token: DeviceToken, key: IdempotencyRecord) -> None:
        """The device and its key in one transaction (norm 5.3.8): the instance is a replica set."""
        d = device_token
        document = {"userId": str(d.user_id), "token": d.token, "platform": d.platform.value,
                    "createdAt": _utc(d.created_at), "updatedAt": _utc(d.updated_at)}
        with self._client.start_session() as session:
            with session.start_transaction():
                self._devices.replace_one({"_id": str(d.id)}, document, upsert=True, session=session)
                self._keys.insert_one({"key": key.key, "operation": key.operation, "resourceId": str(key.resource_id),
                                       "requestHash": key.request_hash, "createdAt": _utc(d.updated_at)},
                                      session=session)

    @staticmethod
    def _device(d: dict) -> DeviceToken:
        return DeviceToken(id=UUID(d["_id"]), user_id=UUID(d["userId"]), token=d["token"],
                           platform=Platform(d["platform"]), created_at=d["createdAt"], updated_at=d["updatedAt"])


class MongoProcessedEventRepository:
    """processed_event of barber-saas-notifications-db: the event id is the _id, so it is unique."""

    def __init__(self, database: Database) -> None:
        self._collection = database.get_collection("processed_event", write_concern=WriteConcern(w="majority"))

    def seen(self, event_id: UUID) -> bool:
        return self._collection.find_one({"_id": str(event_id)}, projection={"_id": 1}) is not None

    def record(self, event_id: UUID, event_type: str, processed_at: datetime) -> None:
        try:
            self._collection.insert_one({"_id": str(event_id), "eventType": event_type,
                                         "processedAt": _utc(processed_at)})
        except DuplicateKeyError:
            return None  # another delivery of the same event recorded it first
