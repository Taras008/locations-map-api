from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import viewsets

from common.permissions import IsAdminOrReadOnly, IsOwnerOrAdminOrReadOnly

from . import selectors, services
from .serializers import CategorySerializer, LocationSerializer

CONFLICT = OpenApiResponse(description="Категорія містить локації.")


@extend_schema_view(
    list=extend_schema(summary="Список категорій"),
    retrieve=extend_schema(summary="Категорія"),
    create=extend_schema(summary="Створити категорію (admin)"),
    update=extend_schema(summary="Оновити категорію (admin)"),
    partial_update=extend_schema(summary="Частково оновити категорію (admin)"),
    destroy=extend_schema(
        summary="Видалити категорію (admin)",
        description="Категорію, до якої належать локації, видалити не можна — 409.",
        responses={204: None, 409: CONFLICT},
    ),
)
@extend_schema(tags=["categories"])
class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        return selectors.get_categories()

    def perform_create(self, serializer):
        serializer.instance = services.create_category(**serializer.validated_data)

    def perform_update(self, serializer):
        services.update_category(serializer.instance, **serializer.validated_data)

    def perform_destroy(self, instance):
        services.delete_category(instance)


@extend_schema_view(
    list=extend_schema(summary="Список локацій"),
    retrieve=extend_schema(summary="Локація"),
    create=extend_schema(
        summary="Створити локацію",
        description="Автором стає поточний користувач.",
    ),
    update=extend_schema(summary="Оновити локацію (автор або admin)"),
    partial_update=extend_schema(summary="Частково оновити локацію (автор або admin)"),
    destroy=extend_schema(
        summary="Видалити локацію (автор або admin)",
        description="М'яке видалення: локація зникає з API, але лишається в БД.",
    ),
)
@extend_schema(tags=["locations"])
class LocationViewSet(viewsets.ModelViewSet):
    serializer_class = LocationSerializer
    permission_classes = [IsOwnerOrAdminOrReadOnly]
    owner_field = "author"

    def get_queryset(self):
        return selectors.get_locations()

    def perform_create(self, serializer):
        serializer.instance = services.create_location(
            author=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer):
        services.update_location(serializer.instance, **serializer.validated_data)

    def perform_destroy(self, instance):
        services.delete_location(instance)
