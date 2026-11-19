import logging
from urllib.parse import urlencode

from celery import shared_task
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from common.email import EMAIL_TASK_OPTIONS, send_templated_email

from .models import User

logger = logging.getLogger(__name__)


@shared_task(**EMAIL_TASK_OPTIONS)
def send_password_reset_email(user_id: int) -> None:
    # Токен генеруємо тут, а не у view: він не потрапляє в брокер і логи черги.
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None or not user.has_usable_password():
        return

    query = urlencode(
        {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }
    )
    send_templated_email(
        "users/email/password_reset",
        to=[user.email],
        context={
            "username": user.username,
            "reset_url": f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?{query}",
            "valid_for": format_duration(settings.PASSWORD_RESET_TIMEOUT),
        },
    )
    logger.info("Password reset email sent", extra={"user_id": user.pk})


def format_duration(seconds: int) -> str:
    """Тривалість для тексту листа: цілі години, а коротше за годину — хвилини."""
    if seconds >= 3600:
        return f"{seconds // 3600} год."
    return f"{max(seconds // 60, 1)} хв."
