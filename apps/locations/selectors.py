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
from django.db.models.functions import Cast, Coalesce, Ln
from django.shortcuts import get_object_or_404
from django.utils import timezone

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
        popularity = W_RATING * bayes
                   + W_REVIEWS * ln(1 + reviews_count)
                   + W_VIEWS * ln(1 + views_7d)

    Байєсівське згладжування тягне рейтинг локацій з малою кількістю відгуків до C,
    тож один відгук «5» не обганяє десятки відгуків «4.7»; логарифми не дають
    кількості відгуків і переглядів задавити якість.
    """
    since = timezone.now() - timedelta(days=settings.POPULARITY_VIEWS_WINDOW_DAYS)
    m = float(settings.POPULARITY_BAYES_M)
    c = float(settings.POPULARITY_BAYES_C)

    queryset = queryset.annotate(
        avg_rating=Avg("reviews__rating"),
        reviews_count=Count("reviews", distinct=True),
        views_7d=_views_count(created_at__gte=since),
        views_total=_views_count(),
    )

    reviews = Cast(F("reviews_count"), FloatField())
    ratings_sum = Cast(Coalesce(Sum("reviews__rating"), 0), FloatField())
    bayes = (ratings_sum + Value(m * c)) / (reviews + Value(m))
    views = Cast(F("views_7d"), FloatField())
    popularity = (
        Value(settings.POPULARITY_WEIGHT_RATING) * bayes
        + Value(settings.POPULARITY_WEIGHT_REVIEWS) * Ln(reviews + Value(1.0))
        + Value(settings.POPULARITY_WEIGHT_VIEWS) * Ln(views + Value(1.0))
    )
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
