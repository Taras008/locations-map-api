from django.urls import include, path
from rest_framework.routers import DefaultRouter

from common.views import HealthView

router = DefaultRouter()

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("apps.users.urls")),
    *router.urls,
]
