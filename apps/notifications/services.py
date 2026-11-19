import logging

from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound

from apps.locations.models import Location
from apps.reviews.models import Review
from apps.users.models import User
from common.exceptions import ConflictError
from common.queue import enqueue_on_commit

from .models import LocationSubscription
from .tasks import send_new_review_notifications

logger = logging.getLogger(__name__)

SUBSCRIPTION_EXISTS = "Ви вже підписані на цю локацію."
SUBSCRIPTION_NOT_FOUND = "Ви не підписані на цю локацію."


def subscribe(*, user: User, location: Location) -> LocationSubscription:
    if LocationSubscription.objects.filter(user=user, location=location).exists():
        raise ConflictError(SUBSCRIPTION_EXISTS)
    try:
        with transaction.atomic():
            subscription = LocationSubscription.objects.create(user=user, location=location)
    except IntegrityError as exc:
        raise ConflictError(SUBSCRIPTION_EXISTS) from exc
    logger.info("Subscribed to location", extra={"location_id": location.pk, "user_id": user.pk})
    return subscription


def unsubscribe(*, user: User, location: Location) -> None:
    deleted, _ = LocationSubscription.objects.filter(user=user, location=location).delete()
    if not deleted:
        raise NotFound(SUBSCRIPTION_NOT_FOUND)
    logger.info(
        "Unsubscribed from location", extra={"location_id": location.pk, "user_id": user.pk}
    )


def notify_new_review(review: Review) -> None:
    """Листи автору локації й підписникам — після коміту, щоб воркер точно побачив відгук."""
    enqueue_on_commit(send_new_review_notifications, review.pk)
