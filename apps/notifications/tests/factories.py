import factory

from apps.locations.tests.factories import LocationFactory
from apps.notifications.models import LocationSubscription
from apps.users.tests.factories import UserFactory


class LocationSubscriptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LocationSubscription

    user = factory.SubFactory(UserFactory)
    location = factory.SubFactory(LocationFactory)
