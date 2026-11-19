"""
Throttles. Ліміти (rates) задаються в settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] з env.
Scoped-ліміти підключаються у view: throttle_classes = [ScopedThrottle], throttle_scope = "login".
"""

from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle

from common.http import get_client_ip


class ClientIPMixin:
    """Ідентифікація анонімів за get_client_ip(), а не за сирим X-Forwarded-For."""

    def get_ident(self, request):
        return get_client_ip(request)


class AnonThrottle(ClientIPMixin, AnonRateThrottle):
    scope = "anon"


class UserThrottle(ClientIPMixin, UserRateThrottle):
    scope = "user"


class ScopedThrottle(ClientIPMixin, ScopedRateThrottle):
    pass


class IPScopedThrottle(ScopedThrottle):
    """
    Scoped-ліміт завжди за IP, навіть для залогінених. Для login/register/password reset:
    інакше після успішного входу чи реєстрації лічильник обнулюється (ключ змінюється на user id).
    """

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
