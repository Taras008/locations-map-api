import math
from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.locations import selectors
from apps.locations.models import Location
from apps.locations.tests.factories import LocationFactory, LocationViewFactory
from apps.reviews.tests.factories import ReviewFactory

pytestmark = pytest.mark.django_db


def stats(location: Location) -> Location:
    return selectors.annotate_stats(Location.objects.filter(pk=location.pk)).get()


def expected_popularity(settings, ratings: list[int], views_7d: int) -> float:
    m, c = settings.POPULARITY_BAYES_M, settings.POPULARITY_BAYES_C
    bayes = (sum(ratings) + m * c) / (len(ratings) + m)
    return (
        settings.POPULARITY_WEIGHT_RATING * bayes
        + settings.POPULARITY_WEIGHT_REVIEWS * math.log(1 + len(ratings))
        + settings.POPULARITY_WEIGHT_VIEWS * math.log(1 + views_7d)
    )


def make_location(ratings: list[int] = (), views: int = 0) -> Location:
    location = LocationFactory()
    for rating in ratings:
        ReviewFactory(location=location, rating=rating)
    LocationViewFactory.create_batch(views, location=location)
    return location


STATS = {"avg_rating", "reviews_count", "views_7d", "views_total", "popularity"}


def test_stats_are_not_model_fields():
    assert STATS.isdisjoint(field.name for field in Location._meta.get_fields())


class TestRating:
    def test_avg_rating_and_reviews_count(self):
        location = make_location(ratings=[5, 4, 4, 2])

        result = stats(location)

        assert result.avg_rating == pytest.approx((5 + 4 + 4 + 2) / 4)
        assert result.reviews_count == 4

    def test_location_without_reviews_has_null_rating(self):
        result = stats(make_location())

        assert result.avg_rating is None
        assert result.reviews_count == 0

    def test_views_do_not_multiply_reviews(self):
        # JOIN переглядів поруч із відгуками помножив би рядки: count став би 3 * 4.
        location = make_location(ratings=[5, 3, 1], views=4)

        result = stats(location)

        assert result.reviews_count == 3
        assert result.avg_rating == pytest.approx(3.0)
        assert result.views_7d == 4
        assert result.views_total == 4

    def test_other_locations_reviews_are_not_counted(self):
        location = make_location(ratings=[5])
        make_location(ratings=[1, 1], views=3)

        result = stats(location)

        assert result.avg_rating == pytest.approx(5.0)
        assert result.reviews_count == 1
        assert result.views_total == 0


class TestViews:
    def test_views_7d_ignores_views_older_than_window(self):
        location = LocationFactory()
        now = timezone.now()
        with freeze_time(now - timedelta(days=8)):
            LocationViewFactory(location=location)
        with freeze_time(now - timedelta(days=6, hours=23)):
            LocationViewFactory(location=location)
        LocationViewFactory(location=location)

        with freeze_time(now):
            result = stats(location)

        assert result.views_7d == 2
        assert result.views_total == 3

    def test_window_comes_from_settings(self, settings):
        settings.POPULARITY_VIEWS_WINDOW_DAYS = 1
        location = LocationFactory()
        with freeze_time(timezone.now() - timedelta(days=2)):
            LocationViewFactory(location=location)
        LocationViewFactory(location=location)

        result = stats(location)

        assert result.views_7d == 1
        assert result.views_total == 2


class TestPopularity:
    @pytest.mark.parametrize(
        ("ratings", "views"),
        [([], 0), ([5], 0), ([4, 5, 3], 10), ([1, 2], 50), ([5] * 7, 3)],
    )
    def test_matches_formula(self, settings, ratings, views):
        location = make_location(ratings=ratings, views=views)

        result = stats(location)

        assert result.popularity == pytest.approx(expected_popularity(settings, ratings, views))

    def test_location_without_activity_gets_prior_rating(self, settings):
        result = stats(make_location())

        expected = settings.POPULARITY_WEIGHT_RATING * settings.POPULARITY_BAYES_C
        assert result.popularity == pytest.approx(expected)

    def test_only_recent_views_affect_popularity(self, settings):
        location = make_location(ratings=[4])
        with freeze_time(timezone.now() - timedelta(days=30)):
            LocationViewFactory.create_batch(5, location=location)

        result = stats(location)

        assert result.popularity == pytest.approx(expected_popularity(settings, [4], 0))

    def test_coefficients_come_from_settings(self, settings):
        settings.POPULARITY_BAYES_M = 2
        settings.POPULARITY_BAYES_C = 4.0
        settings.POPULARITY_WEIGHT_RATING = 1.0
        settings.POPULARITY_WEIGHT_REVIEWS = 3.0
        settings.POPULARITY_WEIGHT_VIEWS = 0.5
        location = make_location(ratings=[5, 1], views=6)

        result = stats(location)

        expected = 1.0 * (6 + 2 * 4.0) / (2 + 2) + 3.0 * math.log(3) + 0.5 * math.log(7)
        assert result.popularity == pytest.approx(expected)

    def test_single_perfect_review_does_not_beat_many_good_ones(self):
        lucky = make_location(ratings=[5])
        # 14 × 5 + 6 × 4 = 94 → середнє 4.7 на 20 відгуках.
        solid = make_location(ratings=[5] * 14 + [4] * 6)

        assert stats(solid).avg_rating == pytest.approx(4.7)
        assert stats(solid).popularity > stats(lucky).popularity


class TestGetLocations:
    def test_default_order_is_popularity_desc(self):
        low = make_location()
        high = make_location(ratings=[5, 5, 5], views=10)
        middle = make_location(ratings=[3])

        assert list(selectors.get_locations()) == [high, middle, low]

    def test_hides_soft_deleted(self):
        alive = make_location()
        make_location(ratings=[5]).delete()

        assert list(selectors.get_locations()) == [alive]
