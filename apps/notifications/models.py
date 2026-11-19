from django.conf import settings
from django.db import models

from apps.locations.models import Location


class LocationSubscription(models.Model):
    """Підписка на нові відгуки локації. Лишається в БД і після м'якого видалення локації."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="location_subscriptions",
        verbose_name="користувач",
    )
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="subscriptions", verbose_name="локація"
    )
    created_at = models.DateTimeField("створено", auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "підписка на локацію"
        verbose_name_plural = "підписки на локації"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "location"], name="subscription_unique_user_location"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.location}"
