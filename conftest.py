import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def auth_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def staff_user(db):
    return UserFactory(is_staff=True)


@pytest.fixture
def staff_client(staff_user) -> APIClient:
    client = APIClient()
    client.force_authenticate(staff_user)
    return client


@pytest.fixture
def throttle_rates(monkeypatch):
    """
    Перевизначає ліміти throttling у тесті: throttle_rates(anon="2/min").
    settings-фікстура тут не допомагає — DRF копіює DEFAULT_THROTTLE_RATES
    в атрибут класу SimpleRateThrottle.THROTTLE_RATES під час імпорту.
    """

    def apply(**rates: str) -> None:
        monkeypatch.setattr(
            SimpleRateThrottle, "THROTTLE_RATES", {**SimpleRateThrottle.THROTTLE_RATES, **rates}
        )

    return apply
