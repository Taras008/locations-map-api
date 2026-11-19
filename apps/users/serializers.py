from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .managers import UserManager
from .models import User


class PublicUserSerializer(serializers.ModelSerializer):
    """Користувач у публічних відповідях (автор локації, відгуку): без email."""

    class Meta:
        model = User
        fields = ("id", "username")
        read_only_fields = fields


class MeSerializer(serializers.ModelSerializer):
    """Власний профіль — єдине місце, де користувач бачить свій email."""

    class Meta:
        model = User
        fields = ("id", "email", "username", "is_staff", "date_joined")
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    username = serializers.RegexField(
        r"^[\w.@+-]+\Z",
        max_length=150,
        error_messages={"invalid": "Допустимі лише літери, цифри та символи @/./+/-/_."},
    )
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_email(self, value: str) -> str:
        value = UserManager.normalize_email_address(value)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Користувач з таким email уже існує.")
        return value

    def validate_username(self, value: str) -> str:
        # Без урахування регістру, щоб не можна було видати себе за "Admin" при наявному "admin".
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Це ім'я користувача вже зайняте.")
        return value

    def validate(self, attrs: dict) -> dict:
        # Валідатори паролів (зокрема схожість з email/username) потребують даних користувача.
        user = User(email=attrs["email"], username=attrs["username"])
        try:
            validate_new_password(attrs["password"], user)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"password": exc.detail}) from exc
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_old_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Поточний пароль введено неправильно.")
        return value

    def validate_new_password(self, value: str) -> str:
        validate_new_password(value, self.context["request"].user)
        return value


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})


def validate_new_password(password: str, user: User) -> None:
    try:
        password_validation.validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc
