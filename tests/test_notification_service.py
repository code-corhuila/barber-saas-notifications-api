"""Core tests: the use cases with in-memory adapters, no web framework and no database."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from notifications.adapter.outbound.persistence.in_memory import InMemoryNotificationRepository
from notifications.application.port.inbound.notification_use_cases import PageRequest
from notifications.application.usecase.notification_service import NotificationService
from notifications.domain.model.errors import InvalidNotification, NotificationNotFound
from notifications.domain.model.notification import Notification, NotificationType

T0 = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
ANA = UUID("11111111-1111-1111-1111-111111111111")
LUIS = UUID("22222222-2222-2222-2222-222222222222")


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


def notification(user: UUID, minutes: int, *, read: bool = False) -> Notification:
    at = T0 + timedelta(minutes=minutes)
    return Notification(id=uuid4(), user_id=user, barbershop_id=None, title="Cita confirmada",
                        body="Tu cita del 10/10 a las 10:00 fue confirmada.",
                        type=NotificationType.APPOINTMENT_CONFIRMATION, read=read,
                        source_event_id=None, created_at=at, updated_at=at)


@pytest.fixture
def repo() -> InMemoryNotificationRepository:
    return InMemoryNotificationRepository()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(T0 + timedelta(hours=1))


@pytest.fixture
def service(repo, clock) -> NotificationService:
    return NotificationService(repo, clock)


def test_lists_only_the_callers_notifications_most_recent_first(repo, service):
    old, new = notification(ANA, 1), notification(ANA, 2)
    for n in (old, new, notification(LUIS, 3)):
        repo.add(n)

    page = service.list_mine(ANA, read=None, page=PageRequest(page=1, limit=20))

    assert [n.id for n in page.items] == [new.id, old.id]
    assert page.total == 2


def test_pages_the_inbox_and_counts_every_match(repo, service):
    for minute in range(5):
        repo.add(notification(ANA, minute))

    page = service.list_mine(ANA, read=None, page=PageRequest(page=2, limit=2))

    assert [n.created_at.minute for n in page.items] == [2, 1]
    assert (page.total, page.page, page.limit, page.total_pages) == (5, 2, 2, 3)


def test_filters_by_read(repo, service):
    unread, read = notification(ANA, 1), notification(ANA, 2, read=True)
    repo.add(unread)
    repo.add(read)

    assert [n.id for n in service.list_mine(ANA, read=False, page=PageRequest(1, 20)).items] == [unread.id]
    assert [n.id for n in service.list_mine(ANA, read=True, page=PageRequest(1, 20)).items] == [read.id]


def test_marking_as_read_keeps_the_moment(repo, service, clock):
    n = notification(ANA, 1)
    repo.add(n)

    marked = service.mark_read(ANA, n.id)

    assert marked.read and marked.updated_at == clock.now()
    assert repo.find(ANA, n.id).read


def test_marking_twice_changes_nothing(repo, service, clock):
    n = notification(ANA, 1)
    repo.add(n)
    first = service.mark_read(ANA, n.id)
    clock.current += timedelta(minutes=5)

    assert service.mark_read(ANA, n.id).updated_at == first.updated_at


def test_another_users_notification_does_not_exist_for_the_caller(repo, service):
    n = notification(LUIS, 1)
    repo.add(n)

    with pytest.raises(NotificationNotFound):
        service.mark_read(ANA, n.id)
    assert not repo.find(LUIS, n.id).read


@pytest.mark.parametrize("title, body", [("", "body"), ("t" * 151, "body"), ("title", ""), ("title", "b" * 501)])
def test_a_notification_keeps_the_limits_of_the_collection(title, body):
    with pytest.raises(InvalidNotification):
        Notification(id=uuid4(), user_id=ANA, barbershop_id=None, title=title, body=body,
                     type=NotificationType.SYSTEM, read=False, source_event_id=None,
                     created_at=T0, updated_at=T0)
