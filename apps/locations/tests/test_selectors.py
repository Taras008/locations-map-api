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


def expected_popularity(settings, ratings: list[int], views_7d: int = 0) -> float:
    m, c, power = (
        settings.POPULARITY_BAYES_M,
        settings.POPULARITY_BAYES_C,
        settings.POPULARITY_QUALITY_POWER,
    )
    bayes = (sum(ratings) + m * c) / (len(ratings) + m)
    quality = ((bayes - 1) / 4) ** power
    prior = ((c - 1) / 4) ** power
    return (
        prior
        + (quality - prior) * (1 + settings.POPULARITY_WEIGHT_REVIEWS * math.log(1 + len(ratings)))
        + quality * settings.POPULARITY_WEIGHT_VIEWS * math.log(1 + views_7d)
    )


# Набори оцінок, що дають задане середнє на кожен «крок» (рейтинги цілі).
RATING_STEPS = {1: [1], 2: [2], 2.5: [2, 3], 3: [3], 3.5: [3, 4], 4: [4], 5: [5]}


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
        [([], 0), ([], 1000), ([5], 0), ([1], 0), ([4, 5, 3], 10), ([1, 2], 50), ([5] * 7, 3)],
    )
    def test_matches_formula(self, settings, ratings, views):
        location = make_location(ratings=ratings, views=views)

        result = stats(location)

        assert result.popularity == pytest.approx(expected_popularity(settings, ratings, views))

    def test_location_without_activity_gets_prior_quality(self, settings):
        result = stats(make_location())

        assert result.popularity == pytest.approx(((settings.POPULARITY_BAYES_C - 1) / 4) ** 2)

    def test_reference_ordering(self, settings):
        bad = make_location(ratings=[1] * 100)
        empty = make_location()
        one_good = make_location(ratings=[5])
        many_good = make_location(ratings=[5] * 20)

        values = [stats(loc).popularity for loc in (bad, empty, one_good, many_good)]

        expected = [expected_popularity(settings, r) for r in ([1] * 100, [], [5], [5] * 20)]
        assert values == pytest.approx(expected)
        assert values == sorted(values)
        # 100 відгуків «1» — нижче нуля: популярність може бути від'ємною.
        assert values[0] < 0

    @pytest.mark.parametrize("rating", [1, 2, 2.5, 3.5, 4, 5])
    def test_monotonic_in_reviews_count(self, rating):
        location = LocationFactory()
        values = [stats(location).popularity]
        for _ in range(4):
            for value in RATING_STEPS[rating]:
                ReviewFactory(location=location, rating=value)
            values.append(stats(location).popularity)

        if rating > 3:
            assert values == sorted(values) and len(set(values)) == len(values)
        else:
            assert values == sorted(values, reverse=True) and len(set(values)) == len(values)

    def test_neutral_rating_does_not_depend_on_reviews_count(self):
        location = LocationFactory()
        values = [stats(location).popularity]
        for _ in range(5):
            ReviewFactory(location=location, rating=3)
            values.append(stats(location).popularity)

        assert values == pytest.approx([values[0]] * len(values))

    @pytest.mark.parametrize("ratings", [[], [1], [1] * 10, [2, 3], [3], [4], [5] * 5])
    def test_more_views_never_lower_popularity(self, ratings):
        location = make_location(ratings=ratings)
        values = [stats(location).popularity]
        for batch in (1, 10, 100):
            LocationViewFactory.create_batch(batch, location=location)
            values.append(stats(location).popularity)

        assert values == sorted(values)

    def test_views_help_location_without_reviews(self):
        quiet = make_location()
        visited = make_location(views=1000)

        assert stats(visited).popularity > stats(quiet).popularity

    def test_only_recent_views_affect_popularity(self, settings):
        location = make_location(ratings=[4])
        with freeze_time(timezone.now() - timedelta(days=30)):
            LocationViewFactory.create_batch(5, location=location)

        result = stats(location)

        assert result.popularity == pytest.approx(expected_popularity(settings, [4], 0))

    def test_coefficients_come_from_settings(self, settings):
        settings.POPULARITY_BAYES_M = 2
        settings.POPULARITY_BAYES_C = 4.0
        settings.POPULARITY_QUALITY_POWER = 1.0
        settings.POPULARITY_WEIGHT_REVIEWS = 3.0
        settings.POPULARITY_WEIGHT_VIEWS = 0.5
        location = make_location(ratings=[5, 1], views=6)

        result = stats(location)

        bayes = (6 + 2 * 4.0) / (2 + 2)  # 3.5
        quality, prior = (bayes - 1) / 4, (4.0 - 1) / 4
        expected = prior + (quality - prior) * (1 + 3.0 * math.log(3)) + quality * 0.5 * math.log(7)
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
