from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.response import Response

from common.permissions import IsAdminOrReadOnly, IsOwnerOrAdminOrReadOnly

from . import selectors, services
from .filters import LocationFilterSet
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
    list=extend_schema(
        summary="Список локацій",
        description="Пошук, фільтри, сортування (за замовчуванням -popularity) і пагінація. "
        "Локації без відгуків (avg_rating = null) завжди в кінці сортування за рейтингом.",
    ),
    retrieve=extend_schema(
        summary="Локація",
        description="Реєструє перегляд: один на відвідувача (користувача або IP) за TTL "
        "дедуплікації; перегляди автором власної локації не рахуються.",
    ),
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
    filterset_class = LocationFilterSet

    def get_queryset(self):
        if self.action in ("list", "retrieve"):
            return selectors.get_locations()
        return selectors.get_locations_for_write()

    def filter_queryset(self, queryset):
        # Фільтри й сортування — лише для списку: get_object() теж викликає filter_queryset,
        # і ?min_rating/?ordering на деталях чи записі дали б 404/400 або FieldError (500)
        # на запиті без анотацій.
        if self.action != "list":
            return queryset
        return super().filter_queryset(queryset)

    def retrieve(self, request, *args, **kwargs):
        location = self.get_object()
        if services.register_view(location, request):
            # Перечитуємо, щоб лічильники й popularity враховували щойно записаний перегляд.
            location = selectors.get_location(location.pk)
        return Response(self.get_serializer(location).data)

    def perform_create(self, serializer):
        location = services.create_location(author=self.request.user, **serializer.validated_data)
        # Перечитуємо з анотаціями, щоб відповідь містила рейтинг і популярність.
        serializer.instance = selectors.get_location(location.pk)

    def perform_update(self, serializer):
        location = services.update_location(serializer.instance, **serializer.validated_data)
        serializer.instance = selectors.get_location(location.pk)

    def perform_destroy(self, instance):
        services.delete_location(instance)
