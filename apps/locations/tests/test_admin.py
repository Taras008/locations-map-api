import pytest
from django.test import Client

from apps.locations.models import Location
from apps.locations.tests.factories import LocationFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

CHANGELIST_URL = "/admin/locations/location/"


@pytest.fixture
def admin_client_():
    client = Client()
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    return client


def test_changelist_shows_deleted_locations(admin_client_):
    alive = LocationFactory(name="Жива")
    deleted = LocationFactory(name="Видалена")
    deleted.delete()

    response = admin_client_.get(CHANGELIST_URL)

    assert response.status_code == 200
    assert {alive.pk, deleted.pk} == {obj.pk for obj in response.context["cl"].result_list}


def test_filter_by_deleted(admin_client_):
    LocationFactory()
    deleted = LocationFactory()
    deleted.delete()

    response = admin_client_.get(CHANGELIST_URL, {"is_deleted__exact": "1"})

    assert [obj.pk for obj in response.context["cl"].result_list] == [deleted.pk]


def test_deleted_location_change_page_opens(admin_client_):
    location = LocationFactory()
    location.delete()

    response = admin_client_.get(f"{CHANGELIST_URL}{location.pk}/change/")

    assert response.status_code == 200


def test_restore_action_returns_location_to_api(admin_client_, api_client):
    location = LocationFactory()
    location.delete()
    assert api_client.get(f"/api/v1/locations/{location.pk}/").status_code == 404

    response = admin_client_.post(
        CHANGELIST_URL,
        {"action": "restore_selected", "_selected_action": [location.pk]},
    )

    assert response.status_code == 302
    location.refresh_from_db()
    assert not location.is_deleted
    assert location.deleted_at is None
    assert api_client.get(f"/api/v1/locations/{location.pk}/").status_code == 200


def test_delete_action_is_soft(admin_client_):
    location = LocationFactory()

    admin_client_.post(
        CHANGELIST_URL,
        {"action": "soft_delete_selected", "_selected_action": [location.pk]},
    )

    assert Location.all_objects.get(pk=location.pk).is_deleted
    assert not Location.objects.filter(pk=location.pk).exists()


def test_physical_delete_action_is_not_offered(admin_client_):
    response = admin_client_.get(CHANGELIST_URL)

    choices = [value for value, _ in response.context["action_form"].fields["action"].choices]
    assert "delete_selected" not in choices
    assert {"soft_delete_selected", "restore_selected"} <= set(choices)


def test_delete_view_is_soft(admin_client_):
    location = LocationFactory()

    response = admin_client_.post(f"{CHANGELIST_URL}{location.pk}/delete/", {"post": "yes"})

    assert response.status_code == 302
    assert Location.all_objects.get(pk=location.pk).is_deleted
