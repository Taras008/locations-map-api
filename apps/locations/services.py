import logging

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.http import HttpRequest

from apps.users.models import User
from common.exceptions import ConflictError
from common.http import get_client_ip

from .models import Category, Location, LocationView

logger = logging.getLogger(__name__)

CATEGORY_EXISTS = "Категорія з такою назвою або slug уже існує."
CATEGORY_IN_USE = "Категорію неможливо видалити: до неї належать локації."


def create_category(**data) -> Category:
    try:
        with transaction.atomic():
            return Category.objects.create(**data)
    except IntegrityError as exc:
        # Паралельний запит з тією ж назвою/slug проскочив перевірку серіалізатора.
        raise ConflictError(CATEGORY_EXISTS) from exc


def update_category(category: Category, **data) -> Category:
    for field, value in data.items():
        setattr(category, field, value)
    try:
        with transaction.atomic():
            category.save()
    except IntegrityError as exc:
        raise ConflictError(CATEGORY_EXISTS) from exc
    return category


def delete_category(category: Category) -> None:
    try:
        with transaction.atomic():
            category.delete()
    except ProtectedError as exc:
        # PROTECT враховує й м'яко видалені локації: їхні рядки лишаються в БД.
        raise ConflictError(CATEGORY_IN_USE) from exc


def create_location(*, author: User, **data) -> Location:
    location = Location.objects.create(author=author, **data)
    logger.info("Location created", extra={"location_id": location.pk, "user_id": author.pk})
    return location


def update_location(location: Location, **data) -> Location:
    for field, value in data.items():
        setattr(location, field, value)
    location.save()
    return location


def delete_location(location: Location) -> None:
    """М'яке видалення: рядок і пов'язані дані лишаються в БД, локація зникає з API."""
    location.delete()
    logger.info("Location soft-deleted", extra={"location_id": location.pk})


def _visitor_key(request: HttpRequest) -> str:
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"
    return f"anon:{get_client_ip(request)}"


def register_view(location: Location, request: HttpRequest) -> bool:
    """
    Записує перегляд деталей локації; повертає True, якщо його зараховано.

    Один перегляд на відвідувача за LOCATION_VIEW_DEDUP_TTL; автор власну локацію
    не накручує. Якщо Redis недоступний — перегляд не рахується (без дедуплікації
    лічильник легко накрутити), а запит продовжується як звичайно.
    """
    user = request.user if request.user.is_authenticated else None
    if user is not None and user.pk == location.author_id:
        return False

    visitor_key = _visitor_key(request)
    try:
        # У django-redis це атомарний SET NX EX: з паралельних запитів пройде лише один.
        added = cache.add(
            f"location-view:{location.pk}:{visitor_key}", 1, settings.LOCATION_VIEW_DEDUP_TTL
        )
    except Exception:
        # Другий рубіж: зазвичай помилки Redis гасить IGNORE_EXCEPTIONS і add() повертає None.
        logger.warning(
            "View dedup cache unavailable", extra={"location_id": location.pk}, exc_info=True
        )
        return False
    if not added:
        return False

    LocationView.objects.create(location=location, user=user, visitor_key=visitor_key)
    return True
