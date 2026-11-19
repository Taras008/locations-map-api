import pytest

from apps.locations import services
from apps.locations.models import Category
from apps.locations.tests.factories import CategoryFactory
from common.exceptions import ConflictError

pytestmark = pytest.mark.django_db


# Серіалізатор перевіряє унікальність, але паралельний запит може проскочити між
# перевіркою й INSERT — тоді IntegrityError має перетворитися на 409, а не 500.


def test_create_category_race_is_conflict():
    CategoryFactory(name="Музеї", slug="museums")

    with pytest.raises(ConflictError):
        services.create_category(name="Музеї", slug="museums-2")

    assert Category.objects.count() == 1


def test_update_category_race_is_conflict():
    CategoryFactory(slug="taken")
    category = CategoryFactory()

    with pytest.raises(ConflictError):
        services.update_category(category, slug="taken")
