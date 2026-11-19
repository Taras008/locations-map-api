from decimal import Decimal, InvalidOperation

import django_filters
from django import forms
from django.db.models import F, Q, QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.reviews.models import RATING_MAX, RATING_MIN

from .models import LATITUDE_RANGE, LONGITUDE_RANGE, Location

BBOX_HELP = (
    "Видима область мапи: min_lng,min_lat,max_lng,max_lat. "
    "Якщо min_lng > max_lng — область перетинає антимеридіан (180°)."
)


class BBoxField(forms.CharField):
    """Рядок `min_lng,min_lat,max_lng,max_lat` → кортеж із чотирьох Decimal."""

    def clean(self, value):
        value = super().clean(value)
        if not value:
            return None
        parts = value.split(",")
        try:
            min_lng, min_lat, max_lng, max_lat = (Decimal(part.strip()) for part in parts)
        except (ValueError, InvalidOperation):
            raise forms.ValidationError(
                "Очікується чотири числа: min_lng,min_lat,max_lng,max_lat."
            ) from None
        if not all(part.is_finite() for part in (min_lng, min_lat, max_lng, max_lat)):
            raise forms.ValidationError("Координати мають бути скінченними числами.")
        lng_min, lng_max = LONGITUDE_RANGE
        lat_min, lat_max = LATITUDE_RANGE
        if not (lng_min <= min_lng <= lng_max and lng_min <= max_lng <= lng_max):
            raise forms.ValidationError(f"Довгота має бути в межах {lng_min}..{lng_max}.")
        if not (lat_min <= min_lat <= lat_max and lat_min <= max_lat <= lat_max):
            raise forms.ValidationError(f"Широта має бути в межах {lat_min}..{lat_max}.")
        if min_lat > max_lat:
            raise forms.ValidationError("min_lat не може бути більшим за max_lat.")
        return min_lng, min_lat, max_lng, max_lat


@extend_schema_field(OpenApiTypes.STR)
class BBoxFilter(django_filters.Filter):
    field_class = BBoxField

    def filter(self, qs: QuerySet, value) -> QuerySet:
        if not value:
            return qs
        min_lng, min_lat, max_lng, max_lat = value
        if min_lng <= max_lng:
            lng = Q(longitude__gte=min_lng, longitude__lte=max_lng)
        else:
            lng = Q(longitude__gte=min_lng) | Q(longitude__lte=max_lng)
        return qs.filter(lng, latitude__gte=min_lat, latitude__lte=max_lat)


class NullsLastOrderingFilter(django_filters.OrderingFilter):
    """
    Сортування, де локації без відгуків (avg_rating = NULL) завжди в кінці — в обидва
    боки, а id — тай-брейк для стабільної пагінації.
    """

    def get_ordering_value(self, param: str):
        descending = param.startswith("-")
        field = F(self.param_map[param.removeprefix("-")])
        return field.desc(nulls_last=True) if descending else field.asc(nulls_last=True)

    def filter(self, qs: QuerySet, value) -> QuerySet:
        if not value:
            return qs
        ordering = [self.get_ordering_value(param) for param in value if param]
        return qs.order_by(*ordering, "-id")


class IdFilter(django_filters.Filter):
    """
    Тільки цілі додатні id: NumberFilter (DecimalField) пропускає «1.9» (тихо стає 1)
    і «1e999999999» (int() будує гігантське число — дешевий DoS).
    """

    field_class = forms.IntegerField

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("min_value", 1)
        super().__init__(*args, **kwargs)


class LocationFilterSet(django_filters.FilterSet):
    search = django_filters.CharFilter(
        method="filter_search", help_text="Пошук за назвою та описом (без урахування регістру)."
    )
    category = IdFilter(field_name="category_id", help_text="ID категорії.")
    author = IdFilter(field_name="author_id", help_text="ID автора.")
    # Фільтр по анотації avg_rating (HAVING): локації без відгуків (NULL) не потрапляють.
    min_rating = django_filters.NumberFilter(
        field_name="avg_rating",
        lookup_expr="gte",
        min_value=RATING_MIN,
        max_value=RATING_MAX,
        help_text="Мінімальний середній рейтинг (включно).",
    )
    max_rating = django_filters.NumberFilter(
        field_name="avg_rating",
        lookup_expr="lte",
        min_value=RATING_MIN,
        max_value=RATING_MAX,
        help_text="Максимальний середній рейтинг (включно).",
    )
    bbox = BBoxFilter(help_text=BBOX_HELP)
    ordering = NullsLastOrderingFilter(
        fields=("created_at", "avg_rating", "popularity"),
        help_text="created_at | avg_rating | popularity, з '-' — за спаданням. "
        "За замовчуванням -popularity.",
    )

    class Meta:
        model = Location
        fields = ()

    def filter_search(self, qs: QuerySet, name: str, value: str) -> QuerySet:
        # icontains → UPPER(col) LIKE: працює по GIN trigram-індексах на UPPER(name/description).
        return qs.filter(Q(name__icontains=value) | Q(description__icontains=value))
