"""Typed domain errors. The domain does not know HTTP: the adapter decides each status code."""


class DomainError(Exception):
    """Base of every error the domain raises on purpose."""


class InvalidNotification(DomainError):
    """A notification outside the limits of the collection (06-data/models.md §7)."""


class NotificationNotFound(DomainError):
    """No notification with that id for this user — another user's one does not exist for them."""


class UnsupportedEvent(DomainError):
    """An event type this service does not handle; the worker marks it failed instead of retrying."""


class InvalidEvent(DomainError):
    """An event whose payload lacks what its notification needs."""

    def __init__(self, field: str, problem: str) -> None:
        super().__init__(f"{field} {problem}")
        self.field = field
        self.problem = problem
