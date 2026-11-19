import logging

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.users.models import User
from common.exceptions import ConflictError

from .models import Category, Location

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
