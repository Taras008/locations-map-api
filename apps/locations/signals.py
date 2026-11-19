"""
Інвалідація кешу списку локацій. Сигнали, а не виклики в services: так кеш скидається
й при змінах через Django Admin чи ORM. QuerySet.update()/bulk_* сигналів не шлють,
тому для цих моделей не використовуються.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.reviews.models import Review

from .caching import invalidate_list_cache
from .models import Category, Location


@receiver(post_save, sender=Location, dispatch_uid="locations_list_cache_location_saved")
@receiver(post_delete, sender=Location, dispatch_uid="locations_list_cache_location_deleted")
@receiver(post_save, sender=Category, dispatch_uid="locations_list_cache_category_saved")
@receiver(post_delete, sender=Category, dispatch_uid="locations_list_cache_category_deleted")
@receiver(post_save, sender=Review, dispatch_uid="locations_list_cache_review_saved")
@receiver(post_delete, sender=Review, dispatch_uid="locations_list_cache_review_deleted")
def invalidate_location_list(**kwargs) -> None:
    invalidate_list_cache()
