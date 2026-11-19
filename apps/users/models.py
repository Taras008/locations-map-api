from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

from .managers import UserManager


class User(AbstractUser):
    """Вхід за email; username — публічне ім'я, яке бачать інші користувачі."""

    email = models.EmailField("email", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="users_user_email_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.username

    def clean(self):
        super().clean()
        self.email = UserManager.normalize_email_address(self.email)
