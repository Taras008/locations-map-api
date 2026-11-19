import pytest

URL = "/api/v1/"  # корінь API — використовує глобальні anon/user throttles

pytestmark = pytest.mark.django_db


def test_anon_throttle_returns_429_in_unified_format(api_client, throttle_rates):
    throttle_rates(anon="2/min")

    statuses = [api_client.get(URL).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]
    error = api_client.get(URL).json()["error"]
    assert error["code"] == "throttled"
    assert error["details"]["retry_after"] > 0


def test_spoofed_forwarded_for_does_not_bypass_anon_throttle(api_client, throttle_rates):
    throttle_rates(anon="2/min")

    statuses = [
        api_client.get(URL, HTTP_X_FORWARDED_FOR=f"6.6.6.{i}").status_code for i in range(3)
    ]

    assert statuses == [200, 200, 429]


def test_user_throttle(auth_client, throttle_rates):
    throttle_rates(user="1/min")

    statuses = [auth_client.get(URL).status_code for _ in range(2)]

    assert statuses == [200, 429]
