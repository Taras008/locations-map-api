from django.urls import path
from rest_framework.routers import DefaultRouter

from common.views import HealthView

router = DefaultRouter()

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    *router.urls,
]
