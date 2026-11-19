import os

from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def use_django_logging(**kwargs):
    """Worker не налаштовує логування сам — працює settings.LOGGING (JSON у stdout)."""
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)
