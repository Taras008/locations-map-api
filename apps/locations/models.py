from decimal import Decimal

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Upper

from common.models import SoftDeleteModel, TimeStampedModel

LATITUDE_RANGE = (Decimal("-90"), Decimal("90"))
LONGITUDE_RANGE = (Decimal("-180"), Decimal("180"))


class Category(TimeStampedModel):
    name = models.CharField("назва", max_length=100, unique=True)
    slug = models.SlugField("slug", max_length=120, unique=True, allow_unicode=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "категорія"
        verbose_name_plural = "категорії"

    def __str__(self) -> str:
        return self.name


class Location(TimeStampedModel, SoftDeleteModel):
    """
    Рейтинг, популярність і перегляди тут навмисно відсутні: вони обчислюються
    анотаціями в selectors, а не зберігаються.
    """

    name = models.CharField("назва", max_length=200)
    description = models.TextField("опис", blank=True)
    # PROTECT: категорію з локаціями (включно з м'яко видаленими) видалити не можна → 409.
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="locations", verbose_name="категорія"
    )
    address = models.CharField("адреса", max_length=255)
    latitude = models.DecimalField(
        "широта",
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(LATITUDE_RANGE[0]), MaxValueValidator(LATITUDE_RANGE[1])],
    )
    longitude = models.DecimalField(
        "довгота",
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(LONGITUDE_RANGE[0]), MaxValueValidator(LONGITUDE_RANGE[1])],
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="locations",
        verbose_name="автор",
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "локація"
        verbose_name_plural = "локації"
        indexes = [
            models.Index(fields=["is_deleted", "created_at"], name="location_alive_created_idx"),
            models.Index(fields=["latitude", "longitude"], name="location_coords_idx"),
            # icontains у PostgreSQL компілюється в UPPER(col::text) LIKE UPPER(...),
            # тож trigram-індекс будується саме по UPPER(col), інакше планувальник його не бере.
            GinIndex(OpClass(Upper("name"), name="gin_trgm_ops"), name="location_name_trgm_idx"),
            GinIndex(
                OpClass(Upper("description"), name="gin_trgm_ops"),
                name="location_description_trgm_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    latitude__gte=LATITUDE_RANGE[0], latitude__lte=LATITUDE_RANGE[1]
                ),
                name="location_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    longitude__gte=LONGITUDE_RANGE[0], longitude__lte=LONGITUDE_RANGE[1]
                ),
                name="location_longitude_range",
            ),
        ]

    def __str__(self) -> str:
        return self.name
