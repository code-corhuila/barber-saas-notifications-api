"""The composition root: settings from the environment, with every limit declared (norm 5.3.10)."""
import pytest
from fastapi.testclient import TestClient

from apps.api.__main__ import Settings, build_app
from tests.conftest import PUBLIC_KEY


def test_the_service_starts_from_the_environment():
    settings = Settings.from_env({"JWT_PUBLIC_KEY": PUBLIC_KEY.replace("\n", "\n")})

    response = TestClient(build_app(settings)).get("/health")

    assert response.status_code == 200 and response.json()["status"] == "ok"


def test_every_limit_has_a_declared_default():
    settings = Settings.from_env({"JWT_PUBLIC_KEY": PUBLIC_KEY})

    assert (settings.port, settings.keep_alive_timeout_s, settings.graceful_shutdown_s,
            settings.max_concurrency) == (8080, 5, 10, 200)


def test_limits_come_from_the_environment():
    settings = Settings.from_env({"JWT_PUBLIC_KEY": PUBLIC_KEY, "PORT": "9000", "HTTP_MAX_CONCURRENCY": "50"})

    assert (settings.port, settings.max_concurrency) == (9000, 50)


@pytest.mark.parametrize("env", [{}, {"JWT_PUBLIC_KEY": "not-a-key"}], ids=["missing", "not-a-pem"])
def test_the_service_refuses_to_start_without_the_public_key(env):
    with pytest.raises(ValueError):
        build_app(Settings.from_env(env))
