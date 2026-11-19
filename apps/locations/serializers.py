from django.utils.text import slugify
from rest_framework import serializers

from apps.users.serializers import PublicUserSerializer

from .export import ExportFormat
from .models import Category, Location


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {
            "slug": {"required": False, "help_text": "Якщо не передано — генерується з назви."}
        }

    def validate(self, attrs: dict) -> dict:
        if self.instance is None and not attrs.get("slug"):
            slug = slugify(attrs["name"], allow_unicode=True)
            if not slug:
                raise serializers.ValidationError(
                    {"slug": ["Не вдалося згенерувати slug з назви."]}
                )
            if Category.objects.filter(slug=slug).exists():
                raise serializers.ValidationError({"slug": ["Категорія з таким slug уже існує."]})
            attrs["slug"] = slug
        return attrs


class CategoryShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug")
        read_only_fields = fields


class LocationSerializer(serializers.ModelSerializer):
    category = CategoryShortSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=Category.objects.all(), write_only=True
    )
    # Автор завжди request.user: поле лише для читання, передане значення ігнорується.
    author = PublicUserSerializer(read_only=True)
    # Статистика — анотації selectors.annotate_stats(), не поля моделі.
    avg_rating = serializers.DecimalField(
        max_digits=3, decimal_places=2, coerce_to_string=False, allow_null=True, read_only=True
    )
    reviews_count = serializers.IntegerField(read_only=True)
    views_7d = serializers.IntegerField(read_only=True)
    views_total = serializers.IntegerField(read_only=True)
    popularity = serializers.DecimalField(
        max_digits=8, decimal_places=3, coerce_to_string=False, read_only=True
    )

    class Meta:
        model = Location
        fields = (
            "id",
            "name",
            "description",
            "category",
            "category_id",
            "address",
            "latitude",
            "longitude",
            "author",
            "avg_rating",
            "reviews_count",
            "views_7d",
            "views_total",
            "popularity",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        # Координати числами, а не рядками — зручніше для клієнтів мапи.
        extra_kwargs = {
            "latitude": {"coerce_to_string": False},
            "longitude": {"coerce_to_string": False},
        }


class ExportQuerySerializer(serializers.Serializer):
    # Не `format`: цей параметр перехоплює content negotiation DRF.
    file_format = serializers.ChoiceField(
        choices=ExportFormat.CHOICES, default=ExportFormat.CSV, help_text="Формат файлу."
    )
