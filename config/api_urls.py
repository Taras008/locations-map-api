from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.locations.views import CategoryViewSet, LocationViewSet
from apps.notifications.views import MySubscriptionsView
from common.views import HealthView

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("locations", LocationViewSet, basename="location")

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("apps.users.urls")),
    path("me/subscriptions/", MySubscriptionsView.as_view(), name="my-subscriptions"),
    path("", include("apps.reviews.urls")),
    *router.urls,
]
