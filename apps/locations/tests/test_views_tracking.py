from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from freezegun import freeze_time
from redis.exceptions import ConnectionError as RedisConnectionError
from rest_framework.test import APIClient

from apps.locations.models import Location, LocationView
from apps.locations.tests.factories import LocationFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

CACHE_ADD = "apps.locations.services.cache.add"


def detail_url(location: Location) -> str:
    return f"/api/v1/locations/{location.pk}/"


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def location():
    return LocationFactory()


class TestDeduplication:
    def test_first_anonymous_view_is_counted(self, api_client, location):
        response = api_client.get(detail_url(location))

        assert response.status_code == 200
        assert response.data["views_total"] == 1
        assert response.data["views_7d"] == 1
        view = LocationView.objects.get(location=location)
        assert view.visitor_key == "anon:127.0.0.1"
        assert view.user is None

    def test_repeated_view_within_ttl_is_not_counted(self, api_client, location):
        api_client.get(detail_url(location))
        response = api_client.get(detail_url(location))

        assert response.status_code == 200
        assert response.data["views_total"] == 1
        assert LocationView.objects.filter(location=location).count() == 1

    def test_other_user_is_counted(self, auth_client, user, location):
        auth_client.get(detail_url(location))
        auth_client.get(detail_url(location))
        response = client_for(UserFactory()).get(detail_url(location))

        assert response.data["views_total"] == 2
        assert LocationView.objects.filter(user=user, visitor_key=f"user:{user.pk}").count() == 1

    def test_different_anonymous_ips_are_counted(self, api_client, location):
        api_client.get(detail_url(location), REMOTE_ADDR="10.0.0.1")
        response = api_client.get(detail_url(location), REMOTE_ADDR="10.0.0.2")

        assert response.data["views_total"] == 2

    def test_dedup_ttl_comes_from_settings(self, settings, api_client, location):
        settings.LOCATION_VIEW_DEDUP_TTL = 42
        with mock.patch(CACHE_ADD, return_value=True) as cache_add:
            api_client.get(detail_url(location))

        cache_add.assert_called_once_with(f"location-view:{location.pk}:anon:127.0.0.1", 1, 42)


class TestAuthor:
    def test_author_view_is_not_counted(self, location):
        response = client_for(location.author).get(detail_url(location))

        assert response.status_code == 200
        assert response.data["views_total"] == 0
        assert not LocationView.objects.exists()


class TestClientIp:
    def test_forwarded_for_is_ignored_without_trusted_proxies(self, settings, api_client, location):
        settings.NUM_PROXIES = 0
        api_client.get(detail_url(location), HTTP_X_FORWARDED_FOR="1.1.1.1")
        api_client.get(detail_url(location), HTTP_X_FORWARDED_FOR="2.2.2.2")

        assert LocationView.objects.get().visitor_key == "anon:127.0.0.1"

    def test_forwarded_for_is_used_behind_trusted_proxy(self, settings, api_client, location):
        settings.NUM_PROXIES = 1
        api_client.get(detail_url(location), HTTP_X_FORWARDED_FOR="1.1.1.1")
        api_client.get(detail_url(location), HTTP_X_FORWARDED_FOR="spoofed, 2.2.2.2")

        keys = set(LocationView.objects.values_list("visitor_key", flat=True))
        assert keys == {"anon:1.1.1.1", "anon:2.2.2.2"}


class TestWindow:
    def test_view_older_than_7_days_is_not_in_views_7d(self, location):
        # Ключі дедуплікації живуть у реальному Redis, freezegun їх не старить —
        # тому другий перегляд робить інший користувач.
        with freeze_time(timezone.now() - timedelta(days=8)):
            client_for(UserFactory()).get(detail_url(location))
        response = client_for(UserFactory()).get(detail_url(location))

        assert response.data["views_7d"] == 1
        assert response.data["views_total"] == 2


class TestRedisUnavailable:
    def test_cache_error_does_not_break_detail(self, api_client, location):
        with mock.patch(CACHE_ADD, side_effect=RedisConnectionError):
            response = api_client.get(detail_url(location))

        assert response.status_code == 200
        assert response.data["views_total"] == 0
        assert not LocationView.objects.exists()

    def test_ignored_cache_error_does_not_count_view(self, api_client, location):
        # Так поводиться django-redis з IGNORE_EXCEPTIONS=True, коли Redis лежить.
        with mock.patch(CACHE_ADD, return_value=None):
            response = api_client.get(detail_url(location))

        assert response.status_code == 200
        assert not LocationView.objects.exists()


def test_soft_deleted_location_is_not_viewed(api_client, location):
    location.delete()

    response = api_client.get(detail_url(location))

    assert response.status_code == 404
    assert not LocationView.objects.exists()
