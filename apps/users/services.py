import logging

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.db import IntegrityError, transaction
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework.exceptions import ValidationError

from common.exceptions import ConflictError
from common.queue import enqueue_on_commit

from .models import User
from .serializers import validate_new_password
from .tasks import send_password_reset_email

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Невірний email або пароль."
INVALID_RESET_LINK = "Посилання для скидання пароля недійсне або застаріло."


def register_user(request, *, email: str, username: str, password: str) -> User:
    """Створює користувача й одразу відкриває для нього сесію."""
    try:
        with transaction.atomic():
            user = User.objects.create_user(email=email, username=username, password=password)
    except IntegrityError as exc:
        # Паралельна реєстрація з тим самим email/username проскочила перевірку серіалізатора.
        raise ConflictError("Користувач з таким email або ім'ям уже існує.") from exc
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    logger.info("User registered", extra={"user_id": user.pk})
    return user


def login_user(request, *, email: str, password: str) -> User:
    user = authenticate(request, email=email, password=password)
    if user is None:
        # Одне повідомлення для неіснуючого email і неправильного пароля.
        raise ValidationError({"non_field_errors": [INVALID_CREDENTIALS]})
    login(request, user)
    return user


def logout_user(request) -> None:
    logout(request)


def change_password(request, *, new_password: str) -> None:
    user = request.user
    user.set_password(new_password)
    user.save(update_fields=["password"])
    # Інші сесії користувача стають недійсними, поточна лишається.
    update_session_auth_hash(request, user)


def request_password_reset(email: str) -> None:
    """
    Ставить у чергу лист зі скиданням пароля. Нічого не повідомляє про існування email:
    view завжди відповідає 204.
    """
    user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    if user is None or not user.has_usable_password():
        logger.info("Password reset requested for unknown email")
        return
    enqueue_on_commit(send_password_reset_email, user.pk)


def confirm_password_reset(*, uid: str, token: str, new_password: str) -> User:
    user = _get_user_by_uid(uid)
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationError({"token": [INVALID_RESET_LINK]})
    try:
        validate_new_password(new_password, user)
    except ValidationError as exc:
        raise ValidationError({"new_password": exc.detail}) from exc
    # Зміна хешу пароля робить токен недійсним — посилання одноразове.
    user.set_password(new_password)
    user.save(update_fields=["password"])
    logger.info("Password reset completed", extra={"user_id": user.pk})
    return user


def _get_user_by_uid(uid: str) -> User | None:
    try:
        pk = int(force_str(urlsafe_base64_decode(uid)))
    except (TypeError, ValueError, OverflowError):
        return None
    return User.objects.filter(pk=pk, is_active=True).first()
