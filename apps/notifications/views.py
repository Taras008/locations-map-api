from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from . import selectors
from .models import LocationSubscription
from .serializers import SubscriptionSerializer


@extend_schema(
    tags=["subscriptions"],
    summary="Мої підписки",
    description="Локації, на нові відгуки яких підписаний поточний користувач; "
    "видалені локації не показуються.",
    responses={
        200: SubscriptionSerializer,
        401: OpenApiResponse(description="Потрібна автентифікація."),
    },
)
class MySubscriptionsView(generics.ListAPIView):
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return LocationSubscription.objects.none()
        return selectors.get_user_subscriptions(self.request.user)
