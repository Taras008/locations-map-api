from decimal import Decimal

import factory

from apps.locations.models import Category, Location, LocationView
from apps.users.tests.factories import UserFactory


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Категорія {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")


class LocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Location

    name = factory.Sequence(lambda n: f"Локація {n}")
    description = "Опис локації"
    category = factory.SubFactory(CategoryFactory)
    address = "вул. Хрещатик, 1, Київ"
    latitude = Decimal("50.450100")
    longitude = Decimal("30.523400")
    author = factory.SubFactory(UserFactory)


class LocationViewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationView

    location = factory.SubFactory(LocationFactory)
    visitor_key = factory.Sequence(lambda n: f"anon:10.0.0.{n % 256}")
