from unittest import mock

import pytest
from django.db.models import QuerySet

from apps.reviews import services
from apps.reviews.models import ReviewReaction
from apps.reviews.tests.factories import ReviewFactory, ReviewReactionFactory
from common.exceptions import ConflictError

pytestmark = pytest.mark.django_db


@pytest.fixture
def race():
    """Паралельний запит проскочив перевірку exists(): спрацьовує лише UniqueConstraint."""
    with mock.patch.object(QuerySet, "exists", return_value=False):
        yield


def test_concurrent_duplicate_review_is_conflict(race):
    review = ReviewFactory()

    with pytest.raises(ConflictError):
        services.create_review(
            author=review.author, location=review.location, rating=3, comment="Ще раз"
        )


def test_concurrent_duplicate_reaction_is_conflict(race):
    reaction = ReviewReactionFactory()

    with pytest.raises(ConflictError):
        services.add_reaction(
            user=reaction.user, review=reaction.review, value=ReviewReaction.Value.DISLIKE
        )


def test_remove_reaction_only_removes_own_vote():
    reaction = ReviewReactionFactory()
    other = ReviewReactionFactory(review=reaction.review)

    services.remove_reaction(user=reaction.user, review=reaction.review)

    assert list(ReviewReaction.objects.all()) == [other]
