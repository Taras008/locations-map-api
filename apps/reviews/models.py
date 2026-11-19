from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.locations.models import Location
from common.models import TimeStampedModel

RATING_MIN, RATING_MAX = 1, 5


class Review(TimeStampedModel):
    """
    Видаляється фізично: після видалення автор може написати новий відгук.
    Лічильники реакцій — анотації в selectors, а не поля.
    """

    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="reviews", verbose_name="локація"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="автор",
    )
    rating = models.PositiveSmallIntegerField(
        "рейтинг", validators=[MinValueValidator(RATING_MIN), MaxValueValidator(RATING_MAX)]
    )
    comment = models.TextField("коментар")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "відгук"
        verbose_name_plural = "відгуки"
        indexes = [
            models.Index(fields=["location", "created_at"], name="review_location_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["author", "location"], name="review_unique_author_location"
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=RATING_MIN, rating__lte=RATING_MAX),
                name="review_rating_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.author} → {self.location}: {self.rating}"


class ReviewReaction(models.Model):
    class Value(models.IntegerChoices):
        LIKE = 1, "like"
        DISLIKE = -1, "dislike"

    review = models.ForeignKey(
        Review, on_delete=models.CASCADE, related_name="reactions", verbose_name="відгук"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_reactions",
        verbose_name="користувач",
    )
    value = models.SmallIntegerField("голос", choices=Value.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "реакція на відгук"
        verbose_name_plural = "реакції на відгуки"
        constraints = [
            models.UniqueConstraint(fields=["user", "review"], name="reaction_unique_user_review"),
            models.CheckConstraint(
                condition=models.Q(value__in=[1, -1]), name="reaction_value_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} {self.get_value_display()} #{self.review_id}"
