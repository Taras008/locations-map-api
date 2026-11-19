from unittest import mock

import pytest
import redis
from django.db.utils import OperationalError

URL = "/api/v1/health/"

pytestmark = pytest.mark.django_db


def test_health_ok(api_client):
    response = api_client.get(URL)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


def test_health_redis_down_returns_503(api_client):
    with mock.patch.object(redis.Redis, "ping", side_effect=redis.ConnectionError("down")):
        response = api_client.get(URL)

    assert response.status_code == 503
    assert response.json() == {"status": "error", "checks": {"database": "ok", "redis": "error"}}


def test_health_database_down_returns_503(api_client):
    with mock.patch("common.views.connection.cursor", side_effect=OperationalError("down")):
        response = api_client.get(URL)

    assert response.status_code == 503
    assert response.json() == {"status": "error", "checks": {"database": "error", "redis": "ok"}}


def test_health_is_not_throttled(api_client, throttle_rates):
    throttle_rates(anon="1/min")

    statuses = [api_client.get(URL).status_code for _ in range(3)]

    assert statuses == [200, 200, 200]
