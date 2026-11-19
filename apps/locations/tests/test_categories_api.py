import pytest

from apps.locations.models import Category
from apps.locations.tests.factories import CategoryFactory, LocationFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/categories/"


def detail_url(category: Category) -> str:
    return f"{LIST_URL}{category.pk}/"


class TestRead:
    def test_anonymous_can_list_and_retrieve(self, api_client):
        category = CategoryFactory(name="Парки", slug="parky")

        list_response = api_client.get(LIST_URL)
        detail_response = api_client.get(detail_url(category))

        assert list_response.status_code == 200
        assert list_response.json()["results"] == [detail_response.json()]
        assert detail_response.json() == {
            "id": category.pk,
            "name": "Парки",
            "slug": "parky",
            "created_at": detail_response.json()["created_at"],
            "updated_at": detail_response.json()["updated_at"],
        }


class TestWritePermissions:
    @pytest.mark.parametrize(
        ("client_fixture", "status_code", "code"),
        [("api_client", 401, "not_authenticated"), ("auth_client", 403, "permission_denied")],
    )
    def test_non_admin_cannot_write(self, request, client_fixture, status_code, code):
        client = request.getfixturevalue(client_fixture)
        category = CategoryFactory()

        responses = [
            client.post(LIST_URL, {"name": "Музеї"}),
            client.patch(detail_url(category), {"name": "Інше"}),
            client.delete(detail_url(category)),
        ]

        assert [r.status_code for r in responses] == [status_code] * 3
        assert {r.json()["error"]["code"] for r in responses} == {code}
        assert Category.objects.get(pk=category.pk).name == category.name


class TestAdminCrud:
    def test_create_generates_slug_from_name(self, staff_client):
        response = staff_client.post(LIST_URL, {"name": "Кав'ярні та бари"})

        assert response.status_code == 201
        assert response.json()["slug"] == "кавярні-та-бари"
        assert Category.objects.filter(slug="кавярні-та-бари").exists()

    def test_create_with_explicit_slug(self, staff_client):
        response = staff_client.post(LIST_URL, {"name": "Музеї", "slug": "museums"})

        assert response.status_code == 201
        assert response.json()["slug"] == "museums"

    def test_duplicate_name_is_rejected(self, staff_client):
        CategoryFactory(name="Музеї")

        response = staff_client.post(LIST_URL, {"name": "Музеї", "slug": "other"})

        assert response.status_code == 400
        assert "name" in response.json()["error"]["details"]

    def test_generated_slug_collision_is_rejected(self, staff_client):
        CategoryFactory(name="Museums old", slug="museums")

        response = staff_client.post(LIST_URL, {"name": "Museums"})

        assert response.status_code == 400
        assert "slug" in response.json()["error"]["details"]

    def test_unsluggable_name_is_rejected(self, staff_client):
        response = staff_client.post(LIST_URL, {"name": "!!!"})

        assert response.status_code == 400
        assert "slug" in response.json()["error"]["details"]

    def test_update(self, staff_client):
        category = CategoryFactory(slug="old")

        response = staff_client.patch(detail_url(category), {"name": "Нова назва"})

        assert response.status_code == 200
        category.refresh_from_db()
        assert category.name == "Нова назва"
        assert category.slug == "old"  # slug при зміні назви не перегенеровується

    def test_delete_empty_category(self, staff_client):
        category = CategoryFactory()

        response = staff_client.delete(detail_url(category))

        assert response.status_code == 204
        assert not Category.objects.filter(pk=category.pk).exists()

    def test_delete_category_with_locations_is_conflict(self, staff_client):
        location = LocationFactory()

        response = staff_client.delete(detail_url(location.category))

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"
        assert Category.objects.filter(pk=location.category_id).exists()

    def test_delete_category_with_only_soft_deleted_locations_is_conflict(self, staff_client):
        # Рядки м'яко видалених локацій лишаються в БД і посилаються на категорію.
        location = LocationFactory()
        location.delete()

        response = staff_client.delete(detail_url(location.category))

        assert response.status_code == 409
