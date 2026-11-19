from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.locations import selectors as location_selectors
from common.permissions import IsOwnerOrAdminDeleteOrReadOnly

from . import selectors, services
from .models import Review
from .serializers import ReactionSerializer, ReviewSerializer

NOT_FOUND = OpenApiResponse(description="Не знайдено (зокрема видалена локація).")
UNAUTHORIZED = OpenApiResponse(description="Потрібна автентифікація.")


@extend_schema_view(
    get=extend_schema(summary="Відгуки локації"),
    post=extend_schema(
        summary="Залишити відгук",
        description=(
            "Один відгук на локацію від користувача: повторний — 409. "
            "Відгук до власної локації — 400."
        ),
        responses={
            201: ReviewSerializer,
            400: OpenApiResponse(description="Некоректні дані або власна локація."),
            401: UNAUTHORIZED,
            404: NOT_FOUND,
            409: OpenApiResponse(description="Відгук уже існує."),
        },
    ),
)
@extend_schema(tags=["reviews"])
class LocationReviewListCreateView(generics.ListCreateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_location(self):
        # Видалена локація ховається менеджером → 404 і для списку, і для створення.
        if not hasattr(self, "_location"):
            self._location = get_object_or_404(
                location_selectors.get_locations(), pk=self.kwargs["location_id"]
            )
        return self._location

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # генерація схеми без location_id
            return Review.objects.none()
        return selectors.get_location_reviews(self.get_location())

    def perform_create(self, serializer):
        review = services.create_review(
            author=self.request.user, location=self.get_location(), **serializer.validated_data
        )
        serializer.instance = selectors.get_review(review.pk)


@extend_schema_view(
    patch=extend_schema(
        summary="Змінити власний відгук",
        description="Лише автор; admin чужий відгук може тільки видалити.",
        responses={
            200: ReviewSerializer,
            400: OpenApiResponse(description="Некоректні дані."),
            401: UNAUTHORIZED,
            403: OpenApiResponse(description="Не автор відгуку."),
            404: NOT_FOUND,
        },
    ),
    delete=extend_schema(
        summary="Видалити відгук (автор або admin)",
        description="Після видалення автор може залишити новий відгук.",
        responses={
            204: None,
            401: UNAUTHORIZED,
            403: OpenApiResponse(description="Не автор і не admin."),
            404: NOT_FOUND,
        },
    ),
)
@extend_schema(tags=["reviews"])
class ReviewDetailView(generics.UpdateAPIView, generics.DestroyAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [IsOwnerOrAdminDeleteOrReadOnly]
    http_method_names = ["patch", "delete", "options"]
    owner_field = "author"

    def get_queryset(self):
        return selectors.get_reviews()

    def perform_update(self, serializer):
        services.update_review(serializer.instance, **serializer.validated_data)

    def perform_destroy(self, instance):
        services.delete_review(instance)


@extend_schema(tags=["reviews"])
class ReviewReactionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Поставити like/dislike",
        description=(
            "Один голос на користувача: повторний голос (зокрема зміна like на dislike) — 409; "
            "щоб змінити голос, спершу зніміть його через DELETE. "
            "Голос за власний відгук — 400. Повертає відгук з оновленими лічильниками."
        ),
        request=ReactionSerializer,
        responses={
            201: ReviewSerializer,
            400: OpenApiResponse(description="Некоректне значення або власний відгук."),
            401: UNAUTHORIZED,
            404: NOT_FOUND,
            409: OpenApiResponse(description="Користувач уже проголосував."),
        },
    )
    def post(self, request, pk: int):
        review = selectors.get_review(pk)
        serializer = ReactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.add_reaction(
            user=request.user, review=review, value=serializer.validated_data["value"]
        )
        return Response(
            ReviewSerializer(selectors.get_review(pk)).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Зняти свій голос",
        request=None,
        responses={
            204: None,
            401: UNAUTHORIZED,
            404: OpenApiResponse(description="Голосу немає або відгук не знайдено."),
        },
    )
    def delete(self, request, pk: int):
        services.remove_reaction(user=request.user, review=selectors.get_review(pk))
        return Response(status=status.HTTP_204_NO_CONTENT)
