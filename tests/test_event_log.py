"""
Every handled event leaves one INFO line with its id, type and outcome, so the correlation id the
worker sends (X-Correlation-Id) shows up in the logs. Never the payload, the e-mail or the code.
"""
import logging

import pytest

from apps.api.__main__ import configure_logging
from tests.conftest import ANA
from tests.test_events import appointment, deliver, envelope
from tests.test_password_reset import CODE, client, mail, processed, reset  # noqa: F401 (fixtures)

LOGGER = "notifications.application.usecase.event_service"


def handled(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.INFO]


def test_a_processed_code_event_logs_its_id_type_and_outcome_but_never_the_code(client, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    event = envelope("PasswordResetRequested", reset(), barbershop=None)

    deliver(client, event)

    [line] = handled(caplog)
    message = line.getMessage()
    assert event["id"] in message and "PasswordResetRequested" in message and "PROCESSED" in message
    assert CODE not in message and "ana@example.com" not in message and "Ana" not in message


@pytest.mark.parametrize("event_type, payload, outcome", [
    ("StickerGranted", {"clientId": str(ANA)}, "PROCESSED"),
    ("AppointmentConfirmed", appointment(client_id=None), "IGNORED"),
], ids=["inbox-event", "walk-in"])
def test_every_outcome_is_logged(client, caplog, event_type, payload, outcome):
    caplog.set_level(logging.INFO, logger=LOGGER)

    deliver(client, envelope(event_type, payload))

    [line] = handled(caplog)
    assert f"{event_type}: {outcome}" in line.getMessage()


def test_a_redelivery_logs_duplicate(client, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    event = envelope("StickerGranted", {"clientId": str(ANA)})

    deliver(client, event)
    deliver(client, event)

    assert [r.getMessage().rsplit(" ", 1)[-1] for r in handled(caplog)] == ["PROCESSED", "DUPLICATE"]


def test_the_composed_service_lets_the_info_line_through():
    root = logging.getLogger()
    saved = (root.level, list(root.handlers))
    try:
        configure_logging()
        assert logging.getLogger(LOGGER).isEnabledFor(logging.INFO)
    finally:
        root.handlers[:] = saved[1]
        root.setLevel(saved[0])
