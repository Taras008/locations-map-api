from rest_framework.authentication import SessionAuthentication as BaseSessionAuthentication


class SessionAuthentication(BaseSessionAuthentication):
    """
    DRF перетворює NotAuthenticated на 403, якщо в схеми аутентифікації немає
    WWW-Authenticate. Повертаємо заголовок, щоб анонімний запит отримував 401.
    """

    def authenticate_header(self, request):
        return 'Session realm="api"'
