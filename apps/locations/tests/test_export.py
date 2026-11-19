import io
import json

import pandas as pd
import pytest
from freezegun import freeze_time

from apps.locations.export import EXPORT_COLUMNS
from apps.locations.tests.factories import CategoryFactory, LocationFactory
from apps.reviews.tests.factories import ReviewFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

EXPORT_URL = "/api/v1/locations/export/"


def export(client, **params):
    response = client.get(EXPORT_URL, params)
    assert response.status_code == 200, response.content
    return response


def json_rows(client, **params) -> list[dict]:
    return json.loads(export(client, file_format="json", **params).content)


def exported_ids(client, **params) -> list[int]:
    return [row["id"] for row in json_rows(client, **params)]


def rated(*ratings: int, **kwargs):
    location = LocationFactory(**kwargs)
    for rating in ratings:
        ReviewFactory(location=location, rating=rating)
    return location


class TestFormats:
    @freeze_time("2026-03-15 12:00:00")
    def test_csv(self, api_client):
        author = UserFactory(username="olena", email="olena@example.com")
        location = rated(5, 4, name="Кав'ярня, «Львів»", author=author)

        response = export(api_client, file_format="csv")

        assert response["Content-Type"] == "text/csv; charset=utf-8"
        assert response["Content-Disposition"] == 'attachment; filename="locations-2026-03-15.csv"'
        assert response.content.startswith(b"\xef\xbb\xbf")
        frame = pd.read_csv(io.BytesIO(response.content), encoding="utf-8-sig")
        assert tuple(frame.columns) == EXPORT_COLUMNS
        row = frame.iloc[0]
        assert row["id"] == location.pk
        assert row["name"] == "Кав'ярня, «Львів»"
        assert row["author_username"] == "olena"
        assert row["category_name"] == location.category.name
        assert row["avg_rating"] == 4.5
        assert row["reviews_count"] == 2
        assert b"olena@example.com" not in response.content

    @pytest.mark.parametrize("name", ['=HYPERLINK("http://evil")', "+1", "-1+2", "@SUM(A1)"])
    def test_csv_neutralizes_formulas(self, api_client, name):
        LocationFactory(name=name, address="\tвул. Табуляції")

        frame = pd.read_csv(io.BytesIO(export(api_client).content), encoding="utf-8-sig")

        assert frame.iloc[0]["name"] == f"'{name}"
        assert frame.iloc[0]["address"] == "'\tвул. Табуляції"

    def test_json_keeps_values_as_is(self, api_client):
        LocationFactory(name="=1+1")

        assert json_rows(api_client)[0]["name"] == "=1+1"

    def test_cors_exposes_export_headers(self, api_client, settings):
        settings.CORS_ALLOWED_ORIGINS = ["http://spa.example"]
        LocationFactory()

        response = api_client.get(EXPORT_URL, HTTP_ORIGIN="http://spa.example")

        exposed = {h.strip() for h in response["Access-Control-Expose-Headers"].split(",")}
        assert {"Content-Disposition", "X-Export-Truncated", "X-Export-Limit"} <= exposed

    def test_csv_is_default(self, api_client):
        LocationFactory()

        response = export(api_client)

        assert response["Content-Type"] == "text/csv; charset=utf-8"
        assert response["Content-Disposition"].endswith('.csv"')

    @freeze_time("2026-03-15 12:00:00")
    def test_json(self, api_client):
        location = LocationFactory(latitude="50.450100", longitude="30.523400")

        response = export(api_client, file_format="json")

        assert response["Content-Type"] == "application/json"
        assert response["Content-Disposition"] == 'attachment; filename="locations-2026-03-15.json"'
        [row] = json.loads(response.content)
        assert tuple(row) == EXPORT_COLUMNS
        assert row["id"] == location.pk
        assert row["latitude"] == 50.4501
        assert row["longitude"] == 30.5234
        assert row["avg_rating"] is None
        assert row["reviews_count"] == 0
        assert isinstance(row["popularity"], float)
        assert "email" not in json.dumps(row)

    def test_empty_result(self, api_client):
        assert json_rows(api_client) == []
        frame = pd.read_csv(io.BytesIO(export(api_client).content), encoding="utf-8-sig")
        assert tuple(frame.columns) == EXPORT_COLUMNS
        assert frame.empty


class TestFiltersAndOrdering:
    def test_default_ordering_is_popularity_desc(self, api_client):
        low, high, middle = LocationFactory(), rated(5, 5, 5), rated(3)

        assert exported_ids(api_client) == [high.pk, middle.pk, low.pk]

    def test_ordering(self, api_client):
        a, b, c = rated(2), rated(5), rated(4)
        no_reviews = LocationFactory()

        assert exported_ids(api_client, ordering="-avg_rating") == [b.pk, c.pk, a.pk, no_reviews.pk]

    def test_filters(self, api_client):
        cafes = CategoryFactory()
        good_cafe = rated(5, category=cafes, name="Затишна кава")
        rated(2, category=cafes, name="Погана кава")
        rated(5, name="Парк з кавою")
        LocationFactory(category=cafes, name="Без відгуків кава")

        assert exported_ids(api_client, category=cafes.pk, min_rating=4, search="кава") == [
            good_cafe.pk
        ]

    def test_bbox(self, api_client):
        inside = LocationFactory(latitude="50.45", longitude="30.52")
        LocationFactory(latitude="49.84", longitude="24.03")

        assert exported_ids(api_client, bbox="30,50,31,51") == [inside.pk]

    def test_soft_deleted_are_excluded(self, api_client):
        alive = LocationFactory()
        LocationFactory().delete()

        assert exported_ids(api_client) == [alive.pk]

    def test_not_paginated(self, api_client):
        LocationFactory.create_batch(3)

        assert len(json_rows(api_client, page_size=1, page=2)) == 3

    def test_query_count_does_not_grow(self, api_client, django_assert_max_num_queries):
        for _ in range(5):
            rated(4, 5)

        with django_assert_max_num_queries(1):
            assert len(json_rows(api_client)) == 5


class TestRowLimit:
    def test_truncated(self, api_client, settings):
        settings.EXPORT_MAX_ROWS = 2
        top, second = rated(5, 5), rated(4)
        LocationFactory()

        response = export(api_client, file_format="json")

        assert [row["id"] for row in json.loads(response.content)] == [top.pk, second.pk]
        assert response["X-Export-Truncated"] == "true"
        assert response["X-Export-Limit"] == "2"

    def test_not_truncated_at_exact_limit(self, api_client, settings):
        settings.EXPORT_MAX_ROWS = 2
        LocationFactory.create_batch(2)

        response = export(api_client, file_format="json")

        assert len(json.loads(response.content)) == 2
        assert "X-Export-Truncated" not in response


class TestErrors:
    @pytest.mark.parametrize(
        ("params", "field"),
        [({"file_format": "xlsx"}, "file_format"), ({"min_rating": "abc"}, "min_rating")],
    )
    def test_invalid_params(self, api_client, params, field):
        response = api_client.get(EXPORT_URL, params)

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert field in error["details"]

    def test_throttled(self, api_client, throttle_rates):
        throttle_rates(export="1/min")

        assert api_client.get(EXPORT_URL).status_code == 200
        response = api_client.get(EXPORT_URL)

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "throttled"

    def test_list_is_not_affected_by_export_throttle(self, api_client, throttle_rates):
        throttle_rates(export="1/min")
        api_client.get(EXPORT_URL)

        assert api_client.get("/api/v1/locations/").status_code == 200
