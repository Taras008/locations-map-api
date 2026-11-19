from django.db.models import QuerySet

from .models import Category, Location


def get_categories() -> QuerySet[Category]:
    return Category.objects.all()


def get_locations() -> QuerySet[Location]:
    """Живі (не видалені) локації з усім, що потрібно серіалізатору, без N+1."""
    return Location.objects.select_related("category", "author")
