from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.locations.models import Location
from apps.locations.tests.factories import CategoryFactory, LocationFactory, LocationViewFactory
from apps.reviews.tests.factories import ReviewFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/locations/"


def detail_url(location: Location) -> str:
    return f"{LIST_URL}{location.pk}/"


@pytest.fixture
def category():
    return CategoryFactory()


@pytest.fixture
def payload(category) -> dict:
    return {
        "name": "Андріївський узвіз",
        "description": "Історична вулиця",
        "category_id": category.pk,
        "address": "Андріївський узвіз, Київ",
        "latitude": "50.459000",
        "longitude": "30.517500",
    }


@pytest.fixture
def own_location(user):
    return LocationFactory(author=user)


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


class TestRead:
    def test_anonymous_can_list_and_retrieve(self, api_client):
        location = LocationFactory(latitude=Decimal("50.450100"), longitude=Decimal("-30.523400"))

        # Деталі першими: перегляд, який вони записують, уже видно й у списку.
        detail_response = api_client.get(detail_url(location))
        list_response = api_client.get(LIST_URL)

        assert list_response.status_code == 200
        assert list_response.json()["count"] == 1
        assert list_response.json()["results"] == [detail_response.json()]
        body = detail_response.json()
        assert body == {
            "id": location.pk,
            "name": location.name,
            "description": location.description,
            "category": {
                "id": location.category.pk,
                "name": location.category.name,
                "slug": location.category.slug,
            },
            "address": location.address,
            "latitude": 50.4501,
            "longitude": -30.5234,
            "author": {"id": location.author.pk, "username": location.author.username},
            "avg_rating": None,
            "reviews_count": 0,
            "views_7d": 1,
            "views_total": 1,
            "popularity": body["popularity"],
            "created_at": body["created_at"],
            "updated_at": body["updated_at"],
        }

    def test_author_email_is_not_exposed(self, api_client):
        location = LocationFactory()

        response = api_client.get(detail_url(location))

        assert location.author.email not in response.content.decode()

    def test_list_is_paginated(self, api_client):
        LocationFactory.create_batch(3)

        response = api_client.get(LIST_URL, {"page_size": 2})

        assert response.json()["count"] == 3
        assert len(response.json()["results"]) == 2
        assert response.json()["next"]

    def test_list_has_no_n_plus_one(self, api_client, django_assert_num_queries):
        for location in LocationFactory.create_batch(5):
            ReviewFactory.create_batch(2, location=location)
            LocationViewFactory.create_batch(2, location=location)

        # count для пагінації + одна вибірка з JOIN категорії й автора та статистикою.
        with django_assert_num_queries(2):
            response = api_client.get(LIST_URL)

        assert len(response.json()["results"]) == 5

    def test_unknown_location_is_404(self, api_client):
        response = api_client.get(f"{LIST_URL}999999/")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


class TestCreate:
    def test_anonymous_cannot_create(self, api_client, payload):
        response = api_client.post(LIST_URL, payload)

        assert response.status_code == 401
        assert not Location.objects.exists()

    def test_authenticated_user_creates_location(self, auth_client, user, payload, category):
        response = auth_client.post(LIST_URL, payload)

        assert response.status_code == 201
        body = response.json()
        assert body["author"] == {"id": user.pk, "username": user.username}
        assert body["category"]["id"] == category.pk
        assert body["avg_rating"] is None
        assert body["reviews_count"] == 0
        location = Location.objects.get(pk=body["id"])
        assert location.author == user
        assert location.latitude == Decimal("50.459000")
        assert location.longitude == Decimal("30.517500")

    def test_author_cannot_be_spoofed(self, auth_client, user, payload):
        other = UserFactory()

        response = auth_client.post(
            LIST_URL, {**payload, "author": other.pk, "author_id": other.pk}
        )

        assert response.status_code == 201
        assert Location.objects.get(pk=response.json()["id"]).author == user

    def test_stats_cannot_be_written(self, auth_client, payload):
        response = auth_client.post(
            LIST_URL, {**payload, "avg_rating": 5, "reviews_count": 100, "popularity": 999}
        )

        assert response.status_code == 201
        assert response.json()["avg_rating"] is None
        assert response.json()["reviews_count"] == 0
        assert response.json()["popularity"] < 999

    @pytest.mark.parametrize("field", ["name", "category_id", "address", "latitude", "longitude"])
    def test_required_fields(self, auth_client, payload, field):
        del payload[field]

        response = auth_client.post(LIST_URL, payload)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "validation_error"
        assert field in response.json()["error"]["details"]

    def test_description_is_optional(self, auth_client, payload):
        del payload["description"]

        response = auth_client.post(LIST_URL, payload)

        assert response.status_code == 201
        assert response.json()["description"] == ""

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("latitude", "90.000001"),
            ("latitude", "-90.5"),
            ("longitude", "180.000001"),
            ("longitude", "-181"),
            ("latitude", "50.1234567"),  # більше 6 знаків після коми
            ("longitude", "abc"),
        ],
    )
    def test_invalid_coordinates(self, auth_client, payload, field, value):
        response = auth_client.post(LIST_URL, {**payload, field: value})

        assert response.status_code == 400
        assert field in response.json()["error"]["details"]

    @pytest.mark.parametrize(
        ("latitude", "longitude"), [("90", "180"), ("-90", "-180"), ("0", "0")]
    )
    def test_boundary_coordinates_are_valid(self, auth_client, payload, latitude, longitude):
        response = auth_client.post(
            LIST_URL, {**payload, "latitude": latitude, "longitude": longitude}
        )

        assert response.status_code == 201

    def test_unknown_category(self, auth_client, payload):
        response = auth_client.post(LIST_URL, {**payload, "category_id": 999999})

        assert response.status_code == 400
        assert "category_id" in response.json()["error"]["details"]


class TestUpdate:
    def test_author_updates_own_location(self, auth_client, own_location):
        new_category = CategoryFactory()

        response = auth_client.patch(
            detail_url(own_location), {"name": "Нова назва", "category_id": new_category.pk}
        )

        assert response.status_code == 200
        assert response.json()["category"]["id"] == new_category.pk
        assert "popularity" in response.json()
        own_location.refresh_from_db()
        assert own_location.name == "Нова назва"
        assert own_location.category == new_category

    def test_full_update(self, auth_client, own_location, payload):
        response = auth_client.put(detail_url(own_location), payload)

        assert response.status_code == 200
        own_location.refresh_from_db()
        assert own_location.name == payload["name"]

    def test_author_cannot_be_changed(self, auth_client, own_location, user):
        other = UserFactory()

        response = auth_client.patch(detail_url(own_location), {"author": other.pk})

        assert response.status_code == 200
        own_location.refresh_from_db()
        assert own_location.author == user

    def test_other_user_cannot_update(self, auth_client):
        location = LocationFactory(name="Чужа")

        response = auth_client.patch(detail_url(location), {"name": "Зламано"})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"
        location.refresh_from_db()
        assert location.name == "Чужа"

    def test_anonymous_cannot_update(self, api_client):
        location = LocationFactory()

        response = api_client.patch(detail_url(location), {"name": "Зламано"})

        assert response.status_code == 401

    def test_admin_updates_any_location(self, staff_client):
        location = LocationFactory()
        author = location.author

        response = staff_client.patch(detail_url(location), {"name": "Модеровано"})

        assert response.status_code == 200
        location.refresh_from_db()
        assert location.name == "Модеровано"
        assert location.author == author  # admin не стає автором

    def test_invalid_coordinates_on_update(self, auth_client, own_location):
        response = auth_client.patch(detail_url(own_location), {"latitude": "91"})

        assert response.status_code == 400


class TestSoftDelete:
    def test_author_soft_deletes_own_location(self, auth_client, api_client, own_location):
        response = auth_client.delete(detail_url(own_location))

        assert response.status_code == 204
        # Лишається в БД, позначена видаленою.
        stored = Location.all_objects.get(pk=own_location.pk)
        assert stored.is_deleted
        assert stored.deleted_at is not None
        # Зникає з API: деталі → 404, у списку відсутня.
        assert api_client.get(detail_url(own_location)).status_code == 404
        assert api_client.get(LIST_URL).json()["count"] == 0

    def test_deleted_location_cannot_be_updated_or_deleted_again(self, auth_client, own_location):
        own_location.delete()

        assert auth_client.patch(detail_url(own_location), {"name": "x"}).status_code == 404
        assert auth_client.delete(detail_url(own_location)).status_code == 404

    def test_other_user_cannot_delete(self, auth_client):
        location = LocationFactory()

        response = auth_client.delete(detail_url(location))

        assert response.status_code == 403
        assert Location.objects.filter(pk=location.pk).exists()

    def test_anonymous_cannot_delete(self, api_client):
        location = LocationFactory()

        response = api_client.delete(detail_url(location))

        assert response.status_code == 401
        assert Location.objects.filter(pk=location.pk).exists()

    def test_admin_deletes_any_location(self, staff_client):
        location = LocationFactory()

        response = staff_client.delete(detail_url(location))

        assert response.status_code == 204
        assert Location.all_objects.get(pk=location.pk).is_deleted

    def test_list_shows_only_alive_locations(self, api_client):
        alive = LocationFactory()
        LocationFactory().delete()

        response = api_client.get(LIST_URL)

        assert [item["id"] for item in response.json()["results"]] == [alive.pk]


class TestCsrf:
    def test_session_user_needs_csrf_token(self, user, payload):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)

        response = client.post(LIST_URL, payload)

        assert response.status_code == 403
        assert not Location.objects.exists()
