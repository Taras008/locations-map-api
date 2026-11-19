import pytest
from django.db import IntegrityError

from apps.reviews.models import Review, ReviewReaction
from apps.reviews.tests.factories import ReviewFactory, ReviewReactionFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("rating", [0, 6])
def test_rating_check_constraint(rating):
    with pytest.raises(IntegrityError):
        ReviewFactory(rating=rating)


def test_one_review_per_user_and_location():
    review = ReviewFactory()

    with pytest.raises(IntegrityError):
        ReviewFactory(author=review.author, location=review.location)


def test_reaction_value_check_constraint():
    with pytest.raises(IntegrityError):
        ReviewReactionFactory(value=0)


def test_one_reaction_per_user_and_review():
    reaction = ReviewReactionFactory()

    with pytest.raises(IntegrityError):
        ReviewReactionFactory(review=reaction.review, user=reaction.user)


def test_deleting_review_deletes_reactions():
    reaction = ReviewReactionFactory()

    reaction.review.delete()

    assert not Review.objects.exists()
    assert not ReviewReaction.objects.exists()


def test_soft_deleting_location_keeps_reviews():
    review = ReviewFactory()

    review.location.delete()

    assert Review.objects.filter(pk=review.pk).exists()
