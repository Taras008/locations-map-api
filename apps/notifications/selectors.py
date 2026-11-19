from django.db.models import Q, QuerySet

from apps.reviews.models import Review
from apps.users.models import User

from .models import LocationSubscription


def get_user_subscriptions(user: User) -> QuerySet[LocationSubscription]:
    # JOIN на локацію не проходить через Location.objects, тож видалені відсікаємо явно.
    return (
        LocationSubscription.objects.filter(user=user, location__is_deleted=False)
        .select_related("location")
        .order_by("-created_at", "-id")
    )


def get_review_for_notification(review_id: int) -> Review | None:
    """Відгук для листа; None, якщо його вже видалено або локацію м'яко видалено."""
    return (
        Review.objects.select_related("location", "author")
        .filter(pk=review_id, location__is_deleted=False)
        .first()
    )


def get_review_recipients(review: Review) -> QuerySet[User]:
    """
    Хто отримує лист про новий відгук: автор локації та підписники, без автора відгуку.
    Один рядок на користувача — автор, підписаний на власну локацію, отримає один лист.
    """
    is_author = Q(pk=review.location.author_id)
    is_subscriber = Q(location_subscriptions__location_id=review.location_id)
    return (
        User.objects.filter(is_author | is_subscriber, is_active=True)
        .exclude(pk=review.author_id)
        .distinct()
        .order_by("pk")
    )
