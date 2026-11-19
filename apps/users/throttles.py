import hashlib

from rest_framework.throttling import SimpleRateThrottle

from .managers import UserManager


class LoginEmailThrottle(SimpleRateThrottle):
    """
    Ліміт спроб входу на один акаунт незалежно від IP — проти перебору пароля
    з багатьох адрес. Працює разом з IP-лімітом (scope "login").
    У ключі — хеш нормалізованого email, щоб адреси не лежали в Redis відкритим текстом.
    """

    scope = "login_email"

    def get_cache_key(self, request, view):
        email = request.data.get("email") if hasattr(request.data, "get") else None
        if not isinstance(email, str) or not email.strip():
            # Без email ліміт за акаунтом не застосовний; запит відсіє валідація.
            return None
        normalized = UserManager.normalize_email_address(email)
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}
