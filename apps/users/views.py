from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.decorators import csrf_protect_view
from common.throttles import IPScopedThrottle

from . import services
from .serializers import (
    LoginSerializer,
    MeSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
)
from .throttles import LoginEmailThrottle

NO_CONTENT = OpenApiResponse(description="Успішно, без тіла відповіді.")


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Отримати CSRF-токен",
        description=(
            "Встановлює cookie `csrftoken` і повертає той самий токен у тілі. "
            "Його треба передавати в заголовку `X-CSRFToken` у всіх POST/PATCH/DELETE."
        ),
        responses=inline_serializer("CsrfToken", {"csrf_token": serializers.CharField()}),
        tags=["auth"],
    )
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@csrf_protect_view
class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [IPScopedThrottle]
    throttle_scope = "register"

    @extend_schema(
        summary="Реєстрація",
        description="Створює користувача й одразу відкриває сесію.",
        request=RegisterSerializer,
        responses={201: MeSerializer},
        tags=["auth"],
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.register_user(request, **serializer.validated_data)
        return Response(MeSerializer(user).data, status=status.HTTP_201_CREATED)


@csrf_protect_view
class LoginView(APIView):
    permission_classes = [AllowAny]
    # Два незалежні ліміти: за IP (scope "login") і за акаунтом (scope "login_email").
    throttle_classes = [IPScopedThrottle, LoginEmailThrottle]
    throttle_scope = "login"

    @extend_schema(
        summary="Вхід за email і паролем",
        request=LoginSerializer,
        responses={200: MeSerializer},
        tags=["auth"],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.login_user(request, **serializer.validated_data)
        return Response(MeSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Вихід", request=None, responses={204: NO_CONTENT}, tags=["auth"])
    def post(self, request):
        services.logout_user(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Поточний користувач", responses=MeSerializer, tags=["auth"])
    def get(self, request):
        return Response(MeSerializer(request.user).data)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Зміна пароля",
        description="Поточна сесія лишається активною, інші сесії користувача завершуються.",
        request=PasswordChangeSerializer,
        responses={204: NO_CONTENT},
        tags=["auth"],
    )
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        services.change_password(request, new_password=serializer.validated_data["new_password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


@csrf_protect_view
class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [IPScopedThrottle]
    throttle_scope = "password_reset"

    @extend_schema(
        summary="Запит на скидання пароля",
        description=(
            "Надсилає лист із посиланням на фронтенд. Завжди відповідає 204, "
            "щоб не розкривати, чи зареєстрований email."
        ),
        request=PasswordResetSerializer,
        responses={204: NO_CONTENT},
        tags=["auth"],
    )
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response(status=status.HTTP_204_NO_CONTENT)


@csrf_protect_view
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [IPScopedThrottle]
    throttle_scope = "password_reset_confirm"

    @extend_schema(
        summary="Підтвердження скидання пароля",
        description="Приймає `uid` і `token` з посилання в листі та новий пароль.",
        request=PasswordResetConfirmSerializer,
        responses={204: NO_CONTENT},
        tags=["auth"],
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.confirm_password_reset(**serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)
