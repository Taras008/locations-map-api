import pytest
from django.test import Client

from apps.locations.models import Location
from apps.locations.tests.factories import LocationFactory
from apps.notifications.models import LocationSubscription
from apps.notifications.tests.factories import LocationSubscriptionFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

MY_SUBSCRIPTIONS_URL = "/api/v1/me/subscriptions/"


def subscription_url(location_id: int) -> str:
    return f"/api/v1/locations/{location_id}/subscription/"


@pytest.fixture
def location():
    return LocationFactory()


class TestSubscribe:
    def test_subscribes(self, auth_client, user, location):
        response = auth_client.post(subscription_url(location.pk))

        assert response.status_code == 201
        assert response.data["location"] == {"id": location.pk, "name": location.name}
        assert "created_at" in response.data
        assert LocationSubscription.objects.filter(user=user, location=location).exists()

    def test_repeated_subscription_conflicts(self, auth_client, user, location):
        LocationSubscriptionFactory(user=user, location=location)

        response = auth_client.post(subscription_url(location.pk))

        assert response.status_code == 409
        assert response.data["error"]["code"] == "conflict"
        assert LocationSubscription.objects.filter(user=user, location=location).count() == 1

    def test_author_can_subscribe_to_own_location(self, auth_client, user):
        location = LocationFactory(author=user)

        assert auth_client.post(subscription_url(location.pk)).status_code == 201

    def test_anonymous_is_rejected(self, api_client, location):
        response = api_client.post(subscription_url(location.pk))

        assert response.status_code == 401
        assert not LocationSubscription.objects.exists()

    def test_deleted_location_returns_404(self, auth_client, location):
        location.delete()

        assert auth_client.post(subscription_url(location.pk)).status_code == 404
        assert Location.all_objects.filter(pk=location.pk).exists()
        assert not LocationSubscription.objects.exists()

    def test_unknown_location_returns_404(self, auth_client):
        assert auth_client.post(subscription_url(999_999)).status_code == 404


class TestUnsubscribe:
    def test_unsubscribes(self, auth_client, user, location):
        LocationSubscriptionFactory(user=user, location=location)
        other = LocationSubscriptionFactory(location=location)

        response = auth_client.delete(subscription_url(location.pk))

        assert response.status_code == 204
        assert list(LocationSubscription.objects.all()) == [other]

    def test_not_subscribed_returns_404(self, auth_client, location):
        response = auth_client.delete(subscription_url(location.pk))

        assert response.status_code == 404
        assert response.data["error"]["code"] == "not_found"

    def test_anonymous_is_rejected(self, api_client, location):
        assert api_client.delete(subscription_url(location.pk)).status_code == 401


class TestMySubscriptions:
    def test_lists_only_own_live_subscriptions(self, auth_client, user):
        older = LocationSubscriptionFactory(user=user)
        newer = LocationSubscriptionFactory(user=user)
        deleted = LocationSubscriptionFactory(user=user)
        deleted.location.delete()
        LocationSubscriptionFactory()  # чужа

        response = auth_client.get(MY_SUBSCRIPTIONS_URL)

        assert response.status_code == 200
        assert response.data["count"] == 2
        assert [item["location"]["id"] for item in response.data["results"]] == [
            newer.location_id,
            older.location_id,
        ]

    def test_does_not_expose_emails(self, auth_client, user):
        LocationSubscriptionFactory(user=user)

        response = auth_client.get(MY_SUBSCRIPTIONS_URL)

        assert "@" not in response.content.decode()

    def test_constant_queries(self, auth_client, user, django_assert_num_queries):
        LocationSubscriptionFactory.create_batch(5, user=user)

        with django_assert_num_queries(2):  # count + сторінка з JOIN на локацію
            response = auth_client.get(MY_SUBSCRIPTIONS_URL)

        assert len(response.data["results"]) == 5

    def test_anonymous_is_rejected(self, api_client):
        assert api_client.get(MY_SUBSCRIPTIONS_URL).status_code == 401


def test_admin_changelist_opens():
    LocationSubscriptionFactory()
    client = Client()
    client.force_login(UserFactory(is_staff=True, is_superuser=True))

    assert client.get("/admin/notifications/locationsubscription/").status_code == 200
