"""
Єдиний формат помилок API:
    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

import logging

from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError
from django.http import Http404, JsonResponse
from rest_framework import exceptions, status
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class ConflictError(exceptions.APIException):
    """Конфлікт стану ресурсу: дублікат, видалення пов'язаного об'єкта тощо."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Конфлікт стану ресурсу."
    default_code = "conflict"


class BusinessRuleError(exceptions.APIException):
    """Запит коректний за форматом, але порушує бізнес-правило."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Операцію заборонено бізнес-правилами."
    default_code = "business_rule"


def error_payload(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, ProtectedError):
        exc = ConflictError("Ресурс неможливо видалити: на нього посилаються інші об'єкти.")

    response = drf_exception_handler(exc, context)
    if response is None:
        # Необроблене виключення: Django залогує його й поверне handler500.
        return None

    if isinstance(exc, exceptions.ValidationError):
        details = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        payload = error_payload("validation_error", "Некоректні дані.", details)
    else:
        code = exc.get_codes() if isinstance(exc, exceptions.APIException) else "error"
        if not isinstance(code, str):
            code = "error"
        details = {}
        if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
            details["retry_after"] = int(exc.wait)
        payload = error_payload(code, str(getattr(exc, "detail", exc)), details)

    response.data = payload
    return response


# Обробники Django для помилок, що виникають поза DRF (middleware, звичайні view).


def handler400(request, exception=None):
    return JsonResponse(
        error_payload("bad_request", "Некоректний запит."), status=status.HTTP_400_BAD_REQUEST
    )


def handler403(request, exception=None):
    return JsonResponse(
        error_payload("permission_denied", "Недостатньо прав для виконання дії."),
        status=status.HTTP_403_FORBIDDEN,
    )


def csrf_failure(request, reason=""):
    return JsonResponse(
        error_payload("csrf_failed", "Перевірка CSRF не пройдена.", {"reason": reason}),
        status=status.HTTP_403_FORBIDDEN,
    )


def handler404(request, exception=None):
    return JsonResponse(
        error_payload("not_found", "Ресурс не знайдено."), status=status.HTTP_404_NOT_FOUND
    )


def handler500(request):
    return JsonResponse(
        error_payload("server_error", "Внутрішня помилка сервера."),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
