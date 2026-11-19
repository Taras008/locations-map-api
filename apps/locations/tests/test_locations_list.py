from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.locations.models import Location
from apps.locations.tests.factories import CategoryFactory, LocationFactory, LocationViewFactory
from apps.reviews.tests.factories import ReviewFactory
from apps.users.tests.factories import UserFactory
from common.pagination import DefaultPagination

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/locations/"


def ids(response) -> list[int]:
    assert response.status_code == 200, response.json()
    return [item["id"] for item in response.json()["results"]]


def rated(*ratings: int, **kwargs) -> Location:
    location = LocationFactory(**kwargs)
    for rating in ratings:
        ReviewFactory(location=location, rating=rating)
    return location


def assert_validation_error(response, field: str) -> None:
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field in error["details"]


class TestStatsFields:
    def test_list_and_detail_return_stats(self, api_client):
        location = rated(5, 4)
        LocationViewFactory.create_batch(3, location=location)
        with freeze_time(timezone.now() - timedelta(days=10)):
            LocationViewFactory(location=location)

        # Деталі першими: перегляд, який вони записують, уже видно й у списку.
        detail = api_client.get(f"{LIST_URL}{location.pk}/").json()
        item = api_client.get(LIST_URL).json()["results"][0]

        assert item["avg_rating"] == 4.5
        assert item["reviews_count"] == 2
        assert item["views_7d"] == 4
        assert item["views_total"] == 5
        assert isinstance(item["popularity"], float)
        assert {k: detail[k] for k in item} == item

    def test_avg_rating_is_rounded(self, api_client):
        rated(5, 4, 4)

        item = api_client.get(LIST_URL).json()["results"][0]

        assert item["avg_rating"] == 4.33


class TestOrdering:
    def test_default_is_popularity_desc(self, api_client):
        low = LocationFactory()
        high = rated(5, 5, 5)
        middle = rated(3)

        assert ids(api_client.get(LIST_URL)) == [high.pk, middle.pk, low.pk]

    @pytest.mark.parametrize("field", ["popularity", "avg_rating"])
    def test_by_rating_fields_both_directions(self, api_client, field):
        a, b, c = rated(2), rated(5, 5), rated(4)
        expected_desc = [b.pk, c.pk, a.pk]

        assert ids(api_client.get(LIST_URL, {"ordering": f"-{field}"})) == expected_desc
        assert ids(api_client.get(LIST_URL, {"ordering": field})) == expected_desc[::-1]

    def test_by_created_at_both_directions(self, api_client):
        now = timezone.now()
        locations = []
        for days in (3, 1, 2):
            with freeze_time(now - timedelta(days=days)):
                locations.append(LocationFactory())
        oldest, newest, middle = locations

        asc = ids(api_client.get(LIST_URL, {"ordering": "created_at"}))
        desc = ids(api_client.get(LIST_URL, {"ordering": "-created_at"}))

        assert asc == [oldest.pk, middle.pk, newest.pk]
        assert desc == [newest.pk, middle.pk, oldest.pk]

    @pytest.mark.parametrize("ordering", ["avg_rating", "-avg_rating"])
    def test_unrated_locations_are_last_in_both_directions(self, api_client, ordering):
        unrated = LocationFactory()
        low, high = rated(1), rated(5)

        result = ids(api_client.get(LIST_URL, {"ordering": ordering}))

        assert result[-1] == unrated.pk
        assert set(result[:2]) == {low.pk, high.pk}

    def test_ties_are_stable_by_id(self, api_client):
        first, second, third = (rated(4) for _ in range(3))

        result = ids(api_client.get(LIST_URL, {"ordering": "avg_rating"}))

        assert result == [third.pk, second.pk, first.pk]

    def test_unknown_field_is_400(self, api_client):
        response = api_client.get(LIST_URL, {"ordering": "name"})

        assert_validation_error(response, "ordering")


class TestSearch:
    def test_matches_name_and_description_case_insensitive(self, api_client):
        by_name = LocationFactory(name="Золоті Ворота", description="Пам'ятка")
        by_description = LocationFactory(name="Собор", description="Поруч із ЗОЛОТИМИ куполами")
        LocationFactory(name="Парк", description="Зелена зона")

        result = ids(api_client.get(LIST_URL, {"search": "золот"}))

        assert set(result) == {by_name.pk, by_description.pk}

    def test_blank_search_is_ignored(self, api_client):
        LocationFactory.create_batch(2)

        assert len(ids(api_client.get(LIST_URL, {"search": "   "}))) == 2


class TestSimpleFilters:
    def test_by_category(self, api_client):
        category = CategoryFactory()
        match = LocationFactory(category=category)
        LocationFactory()

        assert ids(api_client.get(LIST_URL, {"category": category.pk})) == [match.pk]

    def test_by_author(self, api_client):
        author = UserFactory()
        match = LocationFactory(author=author)
        LocationFactory()

        assert ids(api_client.get(LIST_URL, {"author": author.pk})) == [match.pk]

    @pytest.mark.parametrize("param", ["category", "author"])
    def test_unknown_id_returns_empty_list(self, api_client, param):
        LocationFactory()

        assert ids(api_client.get(LIST_URL, {param: 999999})) == []

    @pytest.mark.parametrize("param", ["category", "author"])
    @pytest.mark.parametrize("value", ["abc", "1.5", "1e999999999", "0", "-1"])
    def test_invalid_id_is_400(self, api_client, param, value):
        assert_validation_error(api_client.get(LIST_URL, {param: value}), param)

    @pytest.mark.parametrize("param", ["category", "author"])
    def test_id_out_of_db_range_returns_empty_list(self, api_client, param):
        LocationFactory()

        assert ids(api_client.get(LIST_URL, {param: 10**30})) == []


class TestRatingFilter:
    @pytest.fixture
    def locations(self):
        return {
            "unrated": LocationFactory(),
            "two": rated(2),
            "three": rated(3, 4),
            "five": rated(5),
        }

    def test_min_rating_is_inclusive_and_skips_unrated(self, api_client, locations):
        result = ids(api_client.get(LIST_URL, {"min_rating": "3.5"}))

        assert set(result) == {locations["three"].pk, locations["five"].pk}

    def test_max_rating_is_inclusive_and_skips_unrated(self, api_client, locations):
        result = ids(api_client.get(LIST_URL, {"max_rating": 2}))

        assert result == [locations["two"].pk]

    def test_range(self, api_client, locations):
        result = ids(api_client.get(LIST_URL, {"min_rating": 2, "max_rating": "3.5"}))

        assert set(result) == {locations["two"].pk, locations["three"].pk}

    @pytest.mark.parametrize(
        ("param", "value"),
        [("min_rating", "0"), ("min_rating", "6"), ("max_rating", "abc"), ("max_rating", "NaN")],
    )
    def test_invalid_value_is_400(self, api_client, param, value):
        assert_validation_error(api_client.get(LIST_URL, {param: value}), param)


class TestBBoxFilter:
    def at(self, lng: str, lat: str) -> Location:
        return LocationFactory(longitude=Decimal(lng), latitude=Decimal(lat))

    def test_returns_locations_inside_box_inclusive(self, api_client):
        inside = self.at("30.5", "50.4")
        on_edge = self.at("31", "51")
        self.at("31.1", "50.4")
        self.at("30.5", "49.9")

        result = ids(api_client.get(LIST_URL, {"bbox": "30,50,31,51"}))

        assert set(result) == {inside.pk, on_edge.pk}

    def test_crossing_antimeridian(self, api_client):
        east = self.at("179.5", "10")
        west = self.at("-179.5", "10")
        self.at("0", "10")

        result = ids(api_client.get(LIST_URL, {"bbox": "179,0,-179,20"}))

        assert set(result) == {east.pk, west.pk}

    @pytest.mark.parametrize(
        "bbox",
        [
            "30,50,31",
            "30,50,31,51,52",
            "a,b,c,d",
            "30,50,31,inf",
            "-181,50,31,51",
            "30,-91,31,51",
            "30,51,31,50",
        ],
    )
    def test_invalid_bbox_is_400(self, api_client, bbox):
        assert_validation_error(api_client.get(LIST_URL, {"bbox": bbox}), "bbox")


class TestCombined:
    def test_filters_and_ordering_combine(self, api_client):
        category = CategoryFactory()
        best = rated(5, 5, category=category, name="Музей мистецтв")
        good = rated(4, category=category, name="Музей історії")
        rated(5, name="Музей іграшок")
        rated(2, category=category, name="Музей техніки")
        LocationFactory(category=category, name="Музей без відгуків")

        response = api_client.get(
            LIST_URL,
            {"search": "музей", "category": category.pk, "min_rating": 4, "ordering": "avg_rating"},
        )

        assert ids(response) == [good.pk, best.pk]


class TestPagination:
    def test_pages(self, api_client):
        LocationFactory.create_batch(5)

        first = api_client.get(LIST_URL, {"page_size": 2}).json()
        last = api_client.get(LIST_URL, {"page_size": 2, "page": 3}).json()

        assert first["count"] == 5
        assert len(first["results"]) == 2
        assert first["previous"] is None
        assert len(last["results"]) == 1
        assert last["next"] is None

    def test_pages_do_not_overlap(self, api_client):
        LocationFactory.create_batch(5)

        pages = [
            ids(api_client.get(LIST_URL, {"page_size": 2, "page": page})) for page in (1, 2, 3)
        ]

        assert len({pk for page in pages for pk in page}) == 5

    def test_page_size_is_capped(self, api_client, monkeypatch):
        # max_page_size читається з settings під час імпорту — підміняємо атрибут класу.
        monkeypatch.setattr(DefaultPagination, "max_page_size", 2)
        LocationFactory.create_batch(3)

        response = api_client.get(LIST_URL, {"page_size": 1000})

        assert len(response.json()["results"]) == 2

    def test_page_out_of_range_is_404(self, api_client):
        LocationFactory()

        assert api_client.get(LIST_URL, {"page": 5}).status_code == 404


class TestQueries:
    def test_filtered_list_has_constant_queries(self, api_client, django_assert_num_queries):
        category = CategoryFactory()
        for location in LocationFactory.create_batch(4, category=category):
            ReviewFactory.create_batch(3, location=location, rating=4)
            LocationViewFactory.create_batch(2, location=location)

        with django_assert_num_queries(2):
            response = api_client.get(
                LIST_URL,
                {
                    "category": category.pk,
                    "min_rating": 3,
                    "search": "Локація",
                    "ordering": "-avg_rating",
                },
            )

        assert len(ids(response)) == 4


class TestFiltersOnlyApplyToList:
    QUERY = "?ordering=popularity&min_rating=3&bbox=0,0,1,1&category=999999"

    def test_detail_ignores_list_params(self, api_client):
        location = LocationFactory()

        response = api_client.get(f"{LIST_URL}{location.pk}/{self.QUERY}")

        assert response.status_code == 200

    def test_update_ignores_list_params(self, user):
        client = APIClient()
        client.force_authenticate(user)
        location = LocationFactory(author=user)

        response = client.patch(f"{LIST_URL}{location.pk}/{self.QUERY}", {"name": "Нове"})

        assert response.status_code == 200
        assert response.json()["name"] == "Нове"

    def test_delete_ignores_list_params(self, user):
        client = APIClient()
        client.force_authenticate(user)
        location = LocationFactory(author=user)

        response = client.delete(f"{LIST_URL}{location.pk}/{self.QUERY}")

        assert response.status_code == 204
