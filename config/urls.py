from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include("config.api_urls")),
]

handler400 = "common.exceptions.handler400"
handler403 = "common.exceptions.handler403"
handler404 = "common.exceptions.handler404"
handler500 = "common.exceptions.handler500"
