from datetime import timedelta

from django.conf import settings
from django.db.models import (
    Avg,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    IntegerField,
    OuterRef,
    QuerySet,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Cast, Coalesce, Ln, Power
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.reviews.models import RATING_MAX, RATING_MIN

from .models import Category, Location, LocationView


def get_categories() -> QuerySet[Category]:
    return Category.objects.all()


def _views_count(**filters) -> Coalesce:
    """
    Кількість переглядів окремим Subquery, а не Count("views"): JOIN переглядів поруч
    із JOIN відгуків множив би рядки й ламав Avg/Sum рейтингу.
    """
    views = (
        LocationView.objects.filter(location=OuterRef("pk"), **filters)
        .order_by()
        .values("location")
        .annotate(count=Count("*"))
        .values("count")
    )
    return Coalesce(Subquery(views, output_field=IntegerField()), 0)


def annotate_stats(queryset: QuerySet[Location]) -> QuerySet[Location]:
    """
    Додає avg_rating, reviews_count, views_7d, views_total і popularity. Нічого з цього
    не зберігається в БД. Формула популярності (коефіцієнти — у settings):

        bayes      = (sum(ratings) + M * C) / (reviews_count + M)
        quality    = ((bayes - 1) / 4) ** P              # 0..1; без відгуків — q0
        q0         = ((C - 1) / 4) ** P
        popularity = q0
                   + (quality - q0) * (1 + W_REVIEWS * ln(1 + reviews_count))
                   + quality * W_VIEWS * ln(1 + views_7d)

    Відгуки підсилюють відхилення якості від апріорної: хороші піднімають популярність,
    погані — опускають (100 відгуків «1» нижче за локацію без відгуків). Перегляди —
    окремий невід'ємний доданок, масштабований якістю: більше переглядів ніколи не
    шкодить, але поганому місцю допомагає мало. Значення може бути від'ємним.
    """
    since = timezone.now() - timedelta(days=settings.POPULARITY_VIEWS_WINDOW_DAYS)
    m = float(settings.POPULARITY_BAYES_M)
    c = float(settings.POPULARITY_BAYES_C)
    power = float(settings.POPULARITY_QUALITY_POWER)
    rating_span = float(RATING_MAX - RATING_MIN)

    queryset = queryset.annotate(
        avg_rating=Avg("reviews__rating"),
        reviews_count=Count("reviews", distinct=True),
        views_7d=_views_count(created_at__gte=since),
        views_total=_views_count(),
    )

    reviews = Cast(F("reviews_count"), FloatField())
    ratings_sum = Cast(Coalesce(Sum("reviews__rating"), 0), FloatField())
    bayes = (ratings_sum + Value(m * c)) / (reviews + Value(m))
    quality = Power((bayes - Value(float(RATING_MIN))) / Value(rating_span), Value(power))
    prior = Value(((c - RATING_MIN) / rating_span) ** power)
    review_boost = Value(1.0) + Value(settings.POPULARITY_WEIGHT_REVIEWS) * Ln(reviews + Value(1.0))
    views_boost = Value(settings.POPULARITY_WEIGHT_VIEWS) * Ln(
        Cast(F("views_7d"), FloatField()) + Value(1.0)
    )
    popularity = prior + (quality - prior) * review_boost + quality * views_boost
    return queryset.annotate(popularity=ExpressionWrapper(popularity, output_field=FloatField()))


def get_locations_for_write() -> QuerySet[Location]:
    """Живі локації без анотацій — для update/delete, де статистика не потрібна."""
    return Location.objects.select_related("category", "author")


def get_locations() -> QuerySet[Location]:
    """
    Живі локації зі статистикою, без N+1. За замовчуванням — найпопулярніші першими;
    id — стабільний тай-брейк для пагінації.
    """
    return annotate_stats(get_locations_for_write()).order_by(F("popularity").desc(), "-id")


def get_location(pk: int) -> Location:
    return get_object_or_404(get_locations(), pk=pk)


def get_export_rows(queryset: QuerySet[Location], limit: int) -> tuple[list[dict], bool]:
    """
    Плоскі рядки для експорту з уже відфільтрованого й відсортованого queryset (з анотаціями
    annotate_stats). Повертає (рядки, чи обрізано за limit). Email автора не потрапляє.
    """
    locations = list(queryset[: limit + 1])
    truncated = len(locations) > limit
    rows = [
        {
            "id": location.pk,
            "name": location.name,
            "description": location.description,
            "address": location.address,
            "latitude": float(location.latitude),
            "longitude": float(location.longitude),
            "category_id": location.category_id,
            "category_name": location.category.name,
            "author_id": location.author_id,
            "author_username": location.author.username,
            "avg_rating": None if location.avg_rating is None else round(location.avg_rating, 2),
            "reviews_count": location.reviews_count,
            "views_7d": location.views_7d,
            "popularity": round(location.popularity, 3),
            "created_at": location.created_at.isoformat(),
        }
        for location in locations[:limit]
    ]
    return rows, truncated
