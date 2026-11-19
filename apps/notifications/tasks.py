import logging

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from kombu.exceptions import OperationalError

from apps.reviews.models import RATING_MAX
from common.email import EMAIL_TASK_OPTIONS, send_templated_email

from . import selectors

logger = logging.getLogger(__name__)


@shared_task(
    autoretry_for=(OperationalError, OSError),
    retry_backoff=settings.EMAIL_TASK_RETRY_BACKOFF,
    retry_jitter=True,
    max_retries=settings.EMAIL_TASK_MAX_RETRIES,
)
def send_new_review_notifications(review_id: int) -> None:
    """
    Розсилка про новий відгук: окрема задача на кожного отримувача, щоб ретрай
    збою SMTP для одного не надсилав повторно листи іншим.
    """
    review = selectors.get_review_for_notification(review_id)
    if review is None:
        return
    recipient_ids = list(selectors.get_review_recipients(review).values_list("pk", flat=True))
    for user_id in recipient_ids:
        send_new_review_email.delay(review_id, user_id)
    logger.info(
        "Review notifications queued",
        extra={"review_id": review_id, "recipients": len(recipient_ids)},
    )


@shared_task(**EMAIL_TASK_OPTIONS)
def send_new_review_email(review_id: int, user_id: int) -> None:
    # Ідемпотентність: повторна доставка задачі (acks_late, повтор розсилки) не шле дубль.
    # cache.add — атомарний SET NX: з двох паралельних копій лист надішле лише одна.
    # Претензія живе не довше за саму задачу, тож упалий воркер не блокує лист надовго;
    # «надіслано» на NOTIFICATION_SENT_MARKER_TTL ставимо тільки після успіху.
    # Недоступний Redis (django-redis поверне None) не повинен зупиняти розсилку.
    marker = f"notifications:sent:{review_id}:{user_id}"
    if cache.add(marker, "sending", settings.CELERY_TASK_TIME_LIMIT) is False:
        return
    try:
        sent = _send_new_review_email(review_id, user_id)
    except Exception:
        cache.delete(marker)  # звільняємо слот, щоб autoretry спробував ще раз
        raise
    if not sent:
        cache.delete(marker)
        return
    cache.set(marker, "sent", settings.NOTIFICATION_SENT_MARKER_TTL)
    logger.info("Review notification sent", extra={"review_id": review_id, "user_id": user_id})


def _send_new_review_email(review_id: int, user_id: int) -> bool:
    # Стан міг змінитися, поки задача чекала в черзі: відгук видалено, користувач відписався.
    review = selectors.get_review_for_notification(review_id)
    if review is None:
        return False
    user = selectors.get_review_recipients(review).filter(pk=user_id).first()
    if user is None:
        return False

    location = review.location
    send_templated_email(
        "notifications/email/new_review",
        to=[user.email],
        context={
            "username": user.username,
            "location_name": location.name,
            "location_url": f"{settings.FRONTEND_URL.rstrip('/')}/locations/{location.pk}",
            "reviewer": review.author.username,
            "rating": review.rating,
            "rating_max": RATING_MAX,
            "comment": review.comment,
            "is_location_author": user.pk == location.author_id,
        },
    )
    return True
