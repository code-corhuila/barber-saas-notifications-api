"""The composition root: settings from the environment, with every limit declared (norm 5.3.10)."""
import pytest
from fastapi.testclient import TestClient

from apps.api.__main__ import Settings, build_app, email, push
from tests.conftest import PUBLIC_KEY


def test_the_service_starts_from_the_environment():
    settings = Settings.from_env({"JWT_PUBLIC_KEY": PUBLIC_KEY.replace("\n", "\n")})

    response = TestClient(build_app(settings)).get("/health")

    assert response.status_code == 200 and response.json()["status"] == "ok"


def test_every_limit_has_a_declared_default():
    settings = Settings.from_env({"JWT_PUBLIC_KEY": PUBLIC_KEY})

    assert (settings.port, settings.keep_alive_timeout_s, settings.graceful_shutdown_s,
            settings.max_concurrency) == (8080, 5, 10, 200)


def test_mongodb_is_optional_and_its_limits_are_declared():
    settings = Settings.from_env({"JWT_PUBLIC_KEY": PUBLIC_KEY})

    assert settings.mongo_url == ""
    assert (settings.mongo_database, settings.mongo_pool_max, settings.mongo_timeout_ms,
            settings.mongo_server_selection_timeout_ms) == ("notifications", 10, 5000, 3000)


def test_push_is_off_without_credentials_and_its_timeout_is_declared():
    settings = Settings.from_env({"JWT_PUBLIC_KEY": PUBLIC_KEY})

    assert (settings.fcm_service_account_json, settings.fcm_timeout_s) == ("", 5)
    assert type(push(settings, None, None, None)).__name__ == "NoPush"


def test_limits_come_from_the_environment():
    settings = Settings.from_env({"JWT_PUBLIC_KEY": PUBLIC_KEY, "PORT": "9000", "HTTP_MAX_CONCURRENCY": "50"})

    assert (settings.port, settings.max_concurrency) == (9000, 50)


@pytest.mark.parametrize("env", [{}, {"JWT_PUBLIC_KEY": "not-a-key"}], ids=["missing", "not-a-pem"])
def test_the_service_refuses_to_start_without_the_public_key(env):
    with pytest.raises(ValueError):
        build_app(Settings.from_env(env))


def test_without_smtp_host_the_service_starts_and_sends_no_e_mail(caplog):
    # The reset event then answers 503 and waits in the outbox (test_password_reset).
    settings = Settings.from_env({"JWT_PUBLIC_KEY": PUBLIC_KEY})

    assert email(settings) is None and "SMTP_HOST is not set" in caplog.text
    assert TestClient(build_app(settings)).get("/health").status_code == 200


def test_the_service_refuses_to_start_with_credentials_over_an_unencrypted_connection():
    env = {"JWT_PUBLIC_KEY": PUBLIC_KEY, "SMTP_HOST": "smtp.example.com", "SMTP_SECURITY": "none",
           "SMTP_USERNAME": "mailer", "SMTP_PASSWORD": "secret"}

    with pytest.raises(ValueError):
        build_app(Settings.from_env(env))
