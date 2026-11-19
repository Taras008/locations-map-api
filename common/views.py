import logging

import redis
from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


def check_database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        logger.exception("Health check: database unavailable")
        return False
    return True


def check_redis() -> bool:
    # Напряму, а не через cache: кеш налаштований з IGNORE_EXCEPTIONS і ковтає помилки.
    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_timeout=settings.REDIS_HEALTHCHECK_TIMEOUT,
            socket_connect_timeout=settings.REDIS_HEALTHCHECK_TIMEOUT,
        )
        try:
            client.ping()
        finally:
            client.close()
    except Exception:
        logger.exception("Health check: redis unavailable")
        return False
    return True


_STATUS_CHOICES = ["ok", "error"]

HealthResponseSerializer = inline_serializer(
    name="HealthResponse",
    fields={
        "status": serializers.ChoiceField(choices=_STATUS_CHOICES),
        "checks": inline_serializer(
            name="HealthChecks",
            fields={
                "database": serializers.ChoiceField(choices=_STATUS_CHOICES),
                "redis": serializers.ChoiceField(choices=_STATUS_CHOICES),
            },
        ),
    },
)


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        summary="Стан сервісу",
        description="Перевіряє доступність PostgreSQL і Redis. 200 — усе працює, 503 — є збій.",
        responses={200: HealthResponseSerializer, 503: HealthResponseSerializer},
        tags=["health"],
    )
    def get(self, request):
        checks = {"database": check_database(), "redis": check_redis()}
        healthy = all(checks.values())
        return Response(
            {
                "status": "ok" if healthy else "error",
                "checks": {name: "ok" if ok else "error" for name, ok in checks.items()},
            },
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
