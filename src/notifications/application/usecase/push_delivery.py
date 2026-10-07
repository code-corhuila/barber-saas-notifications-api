"""Push a new notification to the devices of its user (N-6). Best effort: the inbox already has it."""
import logging

from notifications.application.port.outbound.clock import Clock
from notifications.application.port.outbound.device_token_repository import DeviceTokenRepository
from notifications.application.port.outbound.notification_repository import NotificationRepository
from notifications.application.port.outbound.push_sender import PushResult, PushSender
from notifications.domain.model.notification import DeliveryAttempt, DeliveryChannel, DeliveryStatus, Notification

log = logging.getLogger(__name__)


class PushDelivery:
    def __init__(self, devices: DeviceTokenRepository, notifications: NotificationRepository, sender: PushSender,
                 clock: Clock) -> None:
        self._devices = devices
        self._notifications = notifications
        self._sender = sender
        self._clock = clock

    def deliver(self, notification: Notification) -> None:
        """One push per device; each try is recorded, and a failure never reaches the event's outcome."""
        data = {"notificationId": str(notification.id), "type": notification.type.value}
        for device in self._devices.tokens_of(notification.user_id):
            try:
                result = self._sender.send(device.token, notification.title, notification.body, data)
            except Exception as error:  # the push service is down or slow: the inbox still has it
                log.warning("push not delivered: %s", type(error).__name__)
                result = PushResult(ok=False, error_code="UNAVAILABLE")
            self._notifications.record_delivery(notification.id, DeliveryAttempt(
                channel=DeliveryChannel.PUSH, status=DeliveryStatus.SENT if result.ok else DeliveryStatus.FAILED,
                attempted_at=self._clock.now(), error_code=None if result.ok else result.error_code))
            if result.token_invalid:
                self._devices.remove(device.id)


class NoPush:
    """No push credentials configured: notifications stay in the inbox only."""

    def deliver(self, notification: Notification) -> None:
        return None
