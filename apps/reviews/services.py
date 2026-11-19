import logging

from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound

from apps.locations.models import Location
from apps.users.models import User
from common.exceptions import BusinessRuleError, ConflictError

from .models import Review, ReviewReaction

logger = logging.getLogger(__name__)

REVIEW_EXISTS = "Ви вже залишили відгук до цієї локації."
OWN_LOCATION = "Не можна залишити відгук до власної локації."
REACTION_EXISTS = "Ви вже проголосували за цей відгук. Щоб змінити голос, спершу зніміть його."
OWN_REVIEW = "Не можна голосувати за власний відгук."
REACTION_NOT_FOUND = "Ви ще не голосували за цей відгук."


def create_review(*, author: User, location: Location, **data) -> Review:
    if location.author_id == author.pk:
        raise BusinessRuleError(OWN_LOCATION)
    if Review.objects.filter(author=author, location=location).exists():
        raise ConflictError(REVIEW_EXISTS)
    try:
        with transaction.atomic():
            review = Review.objects.create(author=author, location=location, **data)
    except IntegrityError as exc:
        # Паралельний запит того ж користувача проскочив перевірку exists().
        raise ConflictError(REVIEW_EXISTS) from exc
    logger.info(
        "Review created",
        extra={"review_id": review.pk, "location_id": location.pk, "user_id": author.pk},
    )
    return review


def update_review(review: Review, **data) -> Review:
    for field, value in data.items():
        setattr(review, field, value)
    review.save()
    return review


def delete_review(review: Review) -> None:
    review_id = review.pk
    review.delete()
    logger.info("Review deleted", extra={"review_id": review_id})


def add_reaction(*, user: User, review: Review, value: int) -> ReviewReaction:
    """Голос один на користувача: щоб змінити його, спершу remove_reaction()."""
    if review.author_id == user.pk:
        raise BusinessRuleError(OWN_REVIEW)
    if ReviewReaction.objects.filter(user=user, review=review).exists():
        raise ConflictError(REACTION_EXISTS)
    try:
        with transaction.atomic():
            return ReviewReaction.objects.create(user=user, review=review, value=value)
    except IntegrityError as exc:
        raise ConflictError(REACTION_EXISTS) from exc


def remove_reaction(*, user: User, review: Review) -> None:
    deleted, _ = ReviewReaction.objects.filter(user=user, review=review).delete()
    if not deleted:
        raise NotFound(REACTION_NOT_FOUND)
