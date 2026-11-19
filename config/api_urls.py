from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.locations.views import CategoryViewSet, LocationViewSet
from common.views import HealthView

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("locations", LocationViewSet, basename="location")

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("apps.users.urls")),
    *router.urls,
]
