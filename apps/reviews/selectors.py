from django.db.models import Count, Q, QuerySet
from django.shortcuts import get_object_or_404

from apps.locations.models import Location

from .models import Review, ReviewReaction


def get_reviews() -> QuerySet[Review]:
    """
    Відгуки живих локацій з лічильниками реакцій. JOIN тут лише один (reactions),
    тож Count не множиться іншими зв'язками.
    """
    return (
        Review.objects.filter(location__is_deleted=False)
        .select_related("author")
        .annotate(
            likes_count=Count("reactions", filter=Q(reactions__value=ReviewReaction.Value.LIKE)),
            dislikes_count=Count(
                "reactions", filter=Q(reactions__value=ReviewReaction.Value.DISLIKE)
            ),
        )
        # GROUP BY від анотацій скидає Meta.ordering; id — стабільний тай-брейк для пагінації.
        .order_by("-created_at", "-id")
    )


def get_location_reviews(location: Location) -> QuerySet[Review]:
    return get_reviews().filter(location=location)


def get_review(pk: int) -> Review:
    return get_object_or_404(get_reviews(), pk=pk)
