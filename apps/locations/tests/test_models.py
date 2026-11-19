from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from apps.locations.models import Location
from apps.locations.tests.factories import LocationFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", Decimal("90.000001")),
        ("latitude", Decimal("-90.000001")),
        ("longitude", Decimal("180.000001")),
        ("longitude", Decimal("-180.000001")),
    ],
)
def test_coordinates_check_constraints(field, value):
    # CheckConstraint — остання лінія захисту для записів повз серіалізатор.
    with pytest.raises(IntegrityError), transaction.atomic():
        LocationFactory(**{field: value})


def test_pg_trgm_extension_is_installed():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
        assert cursor.fetchone() == (1,)


@pytest.mark.parametrize(
    ("lookup", "index_name"),
    [
        ("name__icontains", "location_name_trgm_idx"),
        ("description__icontains", "location_description_trgm_idx"),
    ],
)
def test_icontains_search_uses_trigram_index(lookup, index_name):
    LocationFactory.create_batch(3)
    queryset = Location.all_objects.filter(**{lookup: "хрещ"})

    with connection.cursor() as cursor:
        # На кількох рядках планувальник обрав би seq scan — забороняємо його, щоб
        # перевірити саме те, що індекс придатний для запиту, який генерує ORM.
        cursor.execute("SET LOCAL enable_seqscan = off")
        plan = queryset.explain()

    assert index_name in plan
