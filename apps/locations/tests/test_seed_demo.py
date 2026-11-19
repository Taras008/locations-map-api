from io import StringIO
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.db.models import F

from apps.locations.management.commands.seed_demo import ADMIN_EMAIL, LOCATIONS, USERNAMES
from apps.locations.models import Category, Location
from apps.locations.selectors import annotate_stats
from apps.notifications.models import LocationSubscription
from apps.reviews.models import Review
from apps.users.models import User
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/locations/"


def seed(*args: str) -> str:
    out = StringIO()
    call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


@pytest.fixture(autouse=True)
def _debug(settings):
    settings.DEBUG = True


def test_creates_demo_data():
    with mock.patch("apps.notifications.services.enqueue_on_commit") as enqueue:
        output = seed()

    assert "Демо-дані створено" in output
    assert User.objects.filter(email=ADMIN_EMAIL, is_staff=True, is_superuser=True).exists()
    assert User.objects.filter(email__endswith="@demo.local").count() == len(USERNAMES) + 1
    deleted = sum(item.deleted for item in LOCATIONS)
    assert Location.all_objects.count() == len(LOCATIONS)
    assert Location.objects.count() == len(LOCATIONS) - deleted
    assert Review.objects.exists()
    assert LocationSubscription.objects.exists()
    enqueue.assert_not_called()


def test_respects_business_rules():
    seed()

    assert not Review.objects.filter(author=F("location__author")).exists()
    assert not LocationSubscription.objects.filter(user=F("location__author")).exists()
    assert not Location.all_objects.filter(views__user=F("author")).exists()


def test_views_spread_beyond_popularity_window():
    seed()

    stats = annotate_stats(Location.objects.all())
    assert all(location.views_7d <= location.views_total for location in stats)
    assert any(location.views_7d < location.views_total for location in stats)


def test_demo_users_can_log_in():
    seed("--password", "Another-pass-1")

    assert User.objects.get(email=ADMIN_EMAIL).check_password("Another-pass-1")


def test_second_run_is_noop():
    seed()
    reviews = Review.objects.count()

    output = seed()

    assert "вже є" in output
    assert Review.objects.count() == reviews
    assert User.objects.filter(email=ADMIN_EMAIL).count() == 1


def test_reset_recreates_data():
    seed()
    old_admin = User.objects.get(email=ADMIN_EMAIL)

    seed("--reset")

    assert User.objects.get(email=ADMIN_EMAIL).pk != old_admin.pk
    assert Location.all_objects.count() == len(LOCATIONS)


def test_refuses_without_debug(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError):
        seed()
    with pytest.raises(CommandError):
        seed("--allow-production")
    assert not User.objects.exists()

    output = seed("--allow-production", "--password", "Prod-secret-1")
    assert User.objects.get(email=ADMIN_EMAIL).check_password("Prod-secret-1")
    assert "Prod-secret-1" not in output


def test_detects_partial_demo_data():
    seed()
    User.objects.get(email=ADMIN_EMAIL).delete()

    assert "вже є" in seed()


def test_taken_username_is_reported():
    UserFactory(username=USERNAMES[0])

    with pytest.raises(CommandError, match=USERNAMES[0]):
        seed()
    assert not User.objects.filter(email__endswith="@demo.local").exists()


def test_reuses_existing_categories():
    by_name = Category.objects.create(name="Парки", slug="parky")
    empty = Category.objects.create(name="Пам'ятки архітектури", slug="landmarks")

    seed()
    seed("--reset")

    assert Location.objects.filter(category=by_name).exists()
    empty.refresh_from_db()
    assert Location.objects.filter(category=empty).exists()


def test_bad_reviews_rank_below_unreviewed(api_client):
    seed()

    results = api_client.get(LIST_URL, {"page_size": 100}).json()["results"]
    positions = {item["name"]: index for index, item in enumerate(results)}
    unreviewed = [item["name"] for item in results if item["reviews_count"] == 0]
    worst = min(
        (item for item in results if item["reviews_count"]), key=lambda item: item["avg_rating"]
    )
    assert unreviewed
    assert all(positions[worst["name"]] > positions[name] for name in unreviewed)
