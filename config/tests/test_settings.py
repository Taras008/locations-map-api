import os
import subprocess
import sys

import pytest
from django.conf import settings

from config.celery import app as celery_app

GOOD_KEY = "k" * 50


def import_prod_settings(**env) -> subprocess.CompletedProcess:
    """prod.py перевіряє env під час імпорту — імпортуємо його в окремому процесі."""
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
    return subprocess.run(
        [sys.executable, "-c", "import config.settings.prod"],
        cwd=settings.BASE_DIR,
        env={**clean_env, **env},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_prod_settings_load_with_secure_values():
    result = import_prod_settings(
        DJANGO_SECRET_KEY=GOOD_KEY, DJANGO_ALLOWED_HOSTS="api.example.com"
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "secret_key",
    ["change-me-in-production", "insecure-dev-key-change-me", "too-short"],
)
def test_prod_settings_reject_insecure_secret_key(secret_key):
    result = import_prod_settings(DJANGO_SECRET_KEY=secret_key, DJANGO_ALLOWED_HOSTS="example.com")

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_prod_settings_require_secret_key():
    result = import_prod_settings(DJANGO_ALLOWED_HOSTS="example.com")

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_prod_settings_require_allowed_hosts():
    result = import_prod_settings(DJANGO_SECRET_KEY=GOOD_KEY)

    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr


def test_celery_does_not_hijack_root_logger():
    assert celery_app.conf.worker_hijack_root_logger is False


def test_celery_worker_uses_django_logging(monkeypatch):
    from celery.signals import setup_logging

    applied = []
    monkeypatch.setattr("logging.config.dictConfig", applied.append)

    setup_logging.send(sender=None)

    assert applied == [settings.LOGGING]
