from unittest import mock

import pytest
from django.test import Client, override_settings
from redis.exceptions import ConnectionError as RedisConnectionError
from rest_framework.test import APIClient

from apps.locations.models import Location
from apps.locations.tests.factories import CategoryFactory, LocationFactory
from apps.reviews.tests.factories import ReviewFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/locations/"
CACHE = "apps.locations.caching.cache"


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def results(client: APIClient, params: dict | None = None) -> list[dict]:
    response = client.get(LIST_URL, params or {})
    assert response.status_code == 200, response.json()
    return response.json()["results"]


def names(client: APIClient) -> list[str]:
    return [item["name"] for item in results(client)]


@pytest.fixture
def location():
    return LocationFactory(name="Початкова")


class TestCacheHit:
    def test_second_request_does_not_query_db(
        self, api_client, location, django_assert_num_queries
    ):
        first = api_client.get(LIST_URL, {"ordering": "-created_at"})

        with django_assert_num_queries(0):
            second = api_client.get(LIST_URL, {"ordering": "-created_at"})

        assert second.status_code == 200
        assert second.json() == first.json()

    def test_shared_between_anonymous_and_authenticated(
        self, api_client, location, django_assert_num_queries
    ):
        api_client.get(LIST_URL)
        other = client_for(UserFactory())

        with django_assert_num_queries(0):
            response = other.get(LIST_URL)

        assert [item["id"] for item in response.json()["results"]] == [location.pk]

    def test_param_order_and_unknown_params_do_not_matter(
        self, api_client, location, django_assert_num_queries
    ):
        api_client.get(f"{LIST_URL}?search=поч&ordering=created_at")

        with django_assert_num_queries(0):
            response = api_client.get(f"{LIST_URL}?ordering=created_at&utm=x&search=поч")

        assert response.status_code == 200

    def test_different_params_are_cached_separately(self, api_client):
        cafe, park = CategoryFactory(), CategoryFactory()
        in_cafe = LocationFactory(category=cafe)
        in_park = LocationFactory(category=park)

        assert [i["id"] for i in results(api_client, {"category": cafe.pk})] == [in_cafe.pk]
        assert [i["id"] for i in results(api_client, {"category": park.pk})] == [in_park.pk]

    def test_other_page_goes_to_db(self, api_client):
        LocationFactory.create_batch(3)
        api_client.get(LIST_URL, {"page_size": 2})

        response = api_client.get(LIST_URL, {"page_size": 2, "page": 2})

        assert len(response.json()["results"]) == 1

    def test_pagination_links_are_built_per_request(self, api_client, django_assert_num_queries):
        LocationFactory.create_batch(3)
        api_client.get(LIST_URL, {"page_size": 1, "page": 2, "utm": "junk"}, HTTP_HOST="a.example")

        with django_assert_num_queries(0):
            body = api_client.get(
                LIST_URL, {"page": 2, "page_size": 1}, HTTP_HOST="b.example"
            ).json()

        assert body["next"] == "http://b.example/api/v1/locations/?page=3&page_size=1"
        assert body["previous"] == "http://b.example/api/v1/locations/?page_size=1"
        assert list(body) == ["count", "next", "previous", "results"]

    def test_cached_links_match_fresh_ones(self, api_client):
        LocationFactory.create_batch(3)
        params = {"page_size": 1, "page": 2, "ordering": "created_at"}

        fresh = api_client.get(LIST_URL, params).json()
        cached = api_client.get(LIST_URL, params).json()

        assert cached == fresh

    def test_errors_are_not_cached(self, api_client):
        assert api_client.get(LIST_URL, {"min_rating": "abc"}).status_code == 400
        assert api_client.get(LIST_URL, {"min_rating": "abc"}).status_code == 400

    def test_detail_view_does_not_invalidate(self, api_client, location, django_assert_num_queries):
        # Свідомий компроміс: перегляди не скидають кеш, views_7d у списку відстає до TTL.
        api_client.get(LIST_URL)
        api_client.get(f"{LIST_URL}{location.pk}/")

        with django_assert_num_queries(0):
            response = api_client.get(LIST_URL)

        assert response.json()["results"][0]["views_total"] == 0


class TestInvalidationViaApi:
    def test_location_create(self, api_client, auth_client, location):
        names(api_client)

        response = auth_client.post(
            LIST_URL,
            {
                "name": "Нова",
                "category_id": location.category_id,
                "address": "вул. Нова, 1",
                "latitude": 50.0,
                "longitude": 30.0,
            },
        )

        assert response.status_code == 201, response.json()
        assert "Нова" in names(api_client)

    def test_location_update(self, api_client, location):
        names(api_client)

        client_for(location.author).patch(f"{LIST_URL}{location.pk}/", {"name": "Оновлена"})

        assert names(api_client) == ["Оновлена"]

    def test_location_delete(self, api_client, location):
        names(api_client)

        client_for(location.author).delete(f"{LIST_URL}{location.pk}/")

        assert names(api_client) == []

    def test_review_create_update_delete(self, api_client, location):
        reviewer = client_for(UserFactory())
        assert results(api_client)[0]["reviews_count"] == 0

        review_id = reviewer.post(
            f"{LIST_URL}{location.pk}/reviews/", {"rating": 5, "comment": "Супер"}
        ).json()["id"]
        assert results(api_client)[0]["avg_rating"] == 5

        reviewer.patch(f"/api/v1/reviews/{review_id}/", {"rating": 2})
        assert results(api_client)[0]["avg_rating"] == 2

        reviewer.delete(f"/api/v1/reviews/{review_id}/")
        assert results(api_client)[0]["reviews_count"] == 0

    def test_category_update(self, api_client, staff_client, location):
        results(api_client)

        staff_client.patch(f"/api/v1/categories/{location.category_id}/", {"name": "Парки"})

        assert results(api_client)[0]["category"]["name"] == "Парки"


class TestInvalidationViaOrm:
    def test_location_save(self, api_client, location):
        names(api_client)

        location.name = "Через ORM"
        location.save()

        assert names(api_client) == ["Через ORM"]

    def test_location_hard_delete(self, api_client, location):
        names(api_client)

        location.hard_delete()

        assert names(api_client) == []

    def test_review_create_and_delete(self, api_client, location):
        results(api_client)

        review = ReviewFactory(location=location, rating=3)
        assert results(api_client)[0]["reviews_count"] == 1

        review.delete()
        assert results(api_client)[0]["reviews_count"] == 0

    def test_category_save(self, api_client, location):
        results(api_client)

        location.category.name = "Музеї"
        location.category.save()

        assert results(api_client)[0]["category"]["name"] == "Музеї"


class TestInvalidationViaAdmin:
    @pytest.fixture
    def admin(self):
        client = Client()
        client.force_login(UserFactory(is_staff=True, is_superuser=True))
        return client

    def test_change_form(self, api_client, admin, location):
        names(api_client)

        response = admin.post(
            f"/admin/locations/location/{location.pk}/change/",
            {
                "name": "З адмінки",
                "description": location.description,
                "category": location.category_id,
                "address": location.address,
                "latitude": location.latitude,
                "longitude": location.longitude,
                "author": location.author_id,
            },
        )

        assert response.status_code == 302
        assert names(api_client) == ["З адмінки"]

    def test_soft_delete_and_restore_actions(self, api_client, admin, location):
        changelist = "/admin/locations/location/"
        names(api_client)

        admin.post(
            changelist, {"action": "soft_delete_selected", "_selected_action": [location.pk]}
        )
        assert names(api_client) == []

        admin.post(changelist, {"action": "restore_selected", "_selected_action": [location.pk]})
        assert names(api_client) == ["Початкова"]
        assert not Location.all_objects.get(pk=location.pk).is_deleted


class TestInvalidationOnUsernameChange:
    @pytest.fixture
    def author(self, location):
        return location.author

    def author_username(self, client: APIClient) -> str:
        return results(client)[0]["author"]["username"]

    def test_orm_save(self, api_client, author):
        self.author_username(api_client)

        author.username = "renamed"
        author.save()

        assert self.author_username(api_client) == "renamed"

    def test_save_with_update_fields(self, api_client, author):
        self.author_username(api_client)

        author.username = "renamed"
        author.save(update_fields=["username"])

        assert self.author_username(api_client) == "renamed"

    def test_admin_change_form(self, api_client, author):
        self.author_username(api_client)
        admin = Client()
        admin.force_login(UserFactory(is_staff=True, is_superuser=True))

        response = admin.post(
            f"/admin/users/user/{author.pk}/change/",
            {
                "email": author.email,
                "username": "from-admin",
                "is_active": "on",
                "date_joined_0": author.date_joined.strftime("%d.%m.%Y"),
                "date_joined_1": author.date_joined.strftime("%H:%M:%S"),
            },
        )

        assert response.status_code == 302, response.context["adminform"].form.errors
        assert self.author_username(api_client) == "from-admin"

    def test_other_changes_keep_cache(self, api_client, author, django_assert_num_queries):
        api_client.get(LIST_URL)

        author.first_name = "Олена"
        author.save()
        with django_assert_num_queries(1):
            # Як у login: лише UPDATE, без запиту на перевірку username.
            author.save(update_fields=["last_login"])

        with django_assert_num_queries(0):
            api_client.get(LIST_URL)

    def test_new_user_keeps_cache(self, api_client, location, django_assert_num_queries):
        api_client.get(LIST_URL)
        UserFactory()

        with django_assert_num_queries(0):
            api_client.get(LIST_URL)


class TestRedisUnavailable:
    def test_cache_errors_fall_back_to_db(self, api_client, location):
        # Підміняємо лише кеш списку: throttling і сесії ходять у той самий Redis окремо.
        broken = mock.Mock(
            **{
                f"{method}.side_effect": RedisConnectionError("down")
                for method in ("get", "add", "set", "incr")
            }
        )
        with mock.patch(CACHE, broken):
            assert names(api_client) == ["Початкова"]
            location.name = "Без кешу"
            location.save()
            assert names(api_client) == ["Без кешу"]

    def test_unreachable_redis_is_ignored(self, api_client, location):
        caches = {
            "default": {
                "BACKEND": "django_redis.cache.RedisCache",
                "LOCATION": "redis://127.0.0.1:1/0",
                "OPTIONS": {
                    "CLIENT_CLASS": "django_redis.client.DefaultClient",
                    "SOCKET_CONNECT_TIMEOUT": 0.1,
                    "SOCKET_TIMEOUT": 0.1,
                    "IGNORE_EXCEPTIONS": True,
                },
            }
        }
        with override_settings(CACHES=caches):
            assert names(api_client) == ["Початкова"]
            assert names(api_client) == ["Початкова"]
