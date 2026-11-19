import factory

from apps.locations.tests.factories import LocationFactory
from apps.reviews.models import Review, ReviewReaction
from apps.users.tests.factories import UserFactory


class ReviewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Review

    location = factory.SubFactory(LocationFactory)
    author = factory.SubFactory(UserFactory)
    rating = 4
    comment = "Гарне місце"


class ReviewReactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReviewReaction

    review = factory.SubFactory(ReviewFactory)
    user = factory.SubFactory(UserFactory)
    value = ReviewReaction.Value.LIKE
