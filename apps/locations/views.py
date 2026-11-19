from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.permissions import IsAdminOrReadOnly, IsOwnerOrAdminOrReadOnly
from common.throttles import ScopedThrottle

from . import caching, selectors, services
from .export import render_export
from .filters import LocationFilterSet
from .serializers import CategorySerializer, ExportQuerySerializer, LocationSerializer

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
    # Діє лише для export: ScopedThrottle додається в get_throttles().
    throttle_scope = "export"

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.action == "export":
            throttles.append(ScopedThrottle())
        return throttles

    def get_queryset(self):
        if self.action in ("list", "retrieve", "export"):
            return selectors.get_locations()
        return selectors.get_locations_for_write()

    def filter_queryset(self, queryset):
        # Фільтри й сортування — лише для списку: get_object() теж викликає filter_queryset,
        # і ?min_rating/?ordering на деталях чи записі дали б 404/400 або FieldError (500)
        # на запиті без анотацій.
        if self.action not in ("list", "export"):
            return queryset
        return super().filter_queryset(queryset)

    def list(self, request, *args, **kwargs):
        # Відповідь не залежить від request.user, тож кешується спільно для всіх.
        known_params = [
            *self.filterset_class.base_filters,
            self.paginator.page_query_param,
            self.paginator.page_size_query_param,
        ]
        key, data = caching.get_cached_list(request.query_params, known_params)
        if data is not None:
            return Response(data)
        response = super().list(request, *args, **kwargs)
        if key is not None and response.status_code == 200:
            caching.set_cached_list(key, response.data)
        return response

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

    @extend_schema(
        summary="Експорт локацій у CSV або JSON",
        description="Ті самі фільтри й сортування, що й у списку, без пагінації. Не більше "
        "EXPORT_MAX_ROWS рядків; якщо результат обрізано — заголовок X-Export-Truncated: true.",
        filters=True,
        parameters=[ExportQuerySerializer],
        responses={
            (200, "text/csv"): OpenApiTypes.BINARY,
            (200, "application/json"): OpenApiTypes.BINARY,
        },
    )
    @action(detail=False, methods=["get"], url_path="export", pagination_class=None)
    def export(self, request):
        params = ExportQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        queryset = self.filter_queryset(self.get_queryset())
        limit = settings.EXPORT_MAX_ROWS
        rows, truncated = selectors.get_export_rows(queryset, limit)

        export = render_export(rows, params.validated_data["file_format"])
        response = HttpResponse(export.content, content_type=export.content_type)
        response["Content-Disposition"] = f'attachment; filename="{export.filename}"'
        response["X-Export-Limit"] = str(limit)
        if truncated:
            response["X-Export-Truncated"] = "true"
        return response
