from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import SessionAuthentication as BaseSessionAuthentication


class SessionAuthentication(BaseSessionAuthentication):
    """
    DRF перетворює NotAuthenticated на 403, якщо в схеми аутентифікації немає
    WWW-Authenticate. Повертаємо заголовок, щоб анонімний запит отримував 401.
    """

    def authenticate_header(self, request):
        return 'Session realm="api"'


class SessionAuthenticationScheme(OpenApiAuthenticationExtension):
    """Опис сесійної cookie в OpenAPI (вбудоване розширення не матчить підкласи)."""

    target_class = SessionAuthentication
    name = "cookieAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": settings.SESSION_COOKIE_NAME}
