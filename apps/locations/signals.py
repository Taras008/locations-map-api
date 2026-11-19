"""
Інвалідація кешу списку локацій. Сигнали, а не виклики в services: так кеш скидається
й при змінах через Django Admin чи ORM. QuerySet.update()/bulk_* сигналів не шлють,
тому для цих моделей не використовуються.
"""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.reviews.models import Review
from apps.users.models import User

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


@receiver(pre_save, sender=User, dispatch_uid="locations_list_cache_user_username_check")
def remember_username_change(sender, instance: User, update_fields=None, **kwargs) -> None:
    """
    Список віддає username автора, тож його зміна має скидати кеш. Решта змін User — ні:
    last_login зберігається при кожному вході й обнуляв би кеш без потреби.
    """
    instance._username_changed = False
    if instance._state.adding or (update_fields is not None and "username" not in update_fields):
        # Новий користувач ще не автор локацій; save(update_fields=[...]) без username
        # (як у login) обходиться без зайвого запиту.
        return
    old = User.objects.filter(pk=instance.pk).values_list("username", flat=True).first()
    instance._username_changed = old != instance.username


@receiver(post_save, sender=User, dispatch_uid="locations_list_cache_user_saved")
def invalidate_on_username_change(sender, instance: User, **kwargs) -> None:
    if getattr(instance, "_username_changed", False):
        instance._username_changed = False
        invalidate_list_cache()
