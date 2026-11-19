"""Тестовий urlconf: view, що кидають різні виключення, для перевірки формату помилок."""

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db.models import ProtectedError
from django.http import Http404
from django.urls import path
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from common.decorators import csrf_protect_view
from common.exceptions import BusinessRuleError, ConflictError
from config import urls as root_urls


def raising_view(exc_factory):
    class RaisingView(APIView):
        permission_classes = []
        throttle_classes = []

        def get(self, request):
            raise exc_factory()

    return RaisingView.as_view()


@csrf_protect_view
class CsrfProtectedView(APIView):
    permission_classes = []

    def post(self, request):
        return Response({"ok": True})


def django_view(exc_factory):
    """Звичайна Django-view (не DRF): помилки обробляють handler400/403 з urlconf."""

    def view(request):
        raise exc_factory()

    return view


urlpatterns = [
    path("http404/", raising_view(Http404)),
    path("not-found/", raising_view(exceptions.NotFound)),
    path(
        "validation/",
        raising_view(lambda: exceptions.ValidationError({"name": ["Обов'язкове поле."]})),
    ),
    path("validation-list/", raising_view(lambda: exceptions.ValidationError(["Помилка."]))),
    path("conflict/", raising_view(lambda: ConflictError("Вже існує."))),
    path("business/", raising_view(BusinessRuleError)),
    path("protected/", raising_view(lambda: ProtectedError("protected", set()))),
    path("django-forbidden/", raising_view(PermissionDenied)),
    path("unauthenticated/", raising_view(exceptions.NotAuthenticated)),
    path("throttled/", raising_view(lambda: exceptions.Throttled(wait=42))),
    path("crash/", raising_view(lambda: RuntimeError("boom"))),
    path("csrf-protected/", CsrfProtectedView.as_view()),
    path("django-suspicious/", django_view(lambda: SuspiciousOperation("bad"))),
    path("django-403/", django_view(PermissionDenied)),
]

# Ті самі обробники помилок, що й у кореневому urlconf (яких там немає — Django-дефолтні).
for _name in ("handler400", "handler403", "handler404", "handler500"):
    if hasattr(root_urls, _name):
        globals()[_name] = getattr(root_urls, _name)
