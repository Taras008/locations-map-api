import pytest
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView

from apps.users.models import User
from apps.users.serializers import PublicUserSerializer
from apps.users.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.users.throttles import LoginEmailThrottle

pytestmark = pytest.mark.django_db

CSRF_URL = "/api/v1/auth/csrf/"
REGISTER_URL = "/api/v1/auth/register/"
LOGIN_URL = "/api/v1/auth/login/"
LOGOUT_URL = "/api/v1/auth/logout/"
ME_URL = "/api/v1/auth/me/"
PASSWORD_CHANGE_URL = "/api/v1/auth/password/change/"
RESET_URL = "/api/v1/auth/password/reset/"
RESET_CONFIRM_URL = "/api/v1/auth/password/reset/confirm/"

NEW_PASSWORD = "An0ther-strong-pass"


def register_payload(**overrides) -> dict:
    return {"email": "new@example.com", "username": "newbie", "password": NEW_PASSWORD, **overrides}


def login(client: APIClient, user: User, password: str = DEFAULT_PASSWORD):
    return client.post(LOGIN_URL, {"email": user.email, "password": password})


class TestCsrf:
    def test_csrf_endpoint_sets_cookie_and_returns_token(self, api_client):
        response = api_client.get(CSRF_URL)

        assert response.status_code == 200
        assert response.json()["csrf_token"]
        assert "csrftoken" in response.cookies

    # Ці view виконуються для анонімного користувача, тож SessionAuthentication CSRF
    # не перевіряє — без @csrf_protect_view запити пройшли б без токена.
    @pytest.mark.parametrize(
        ("url", "payload"),
        [
            (LOGIN_URL, {"email": "a@example.com", "password": "x"}),
            (REGISTER_URL, register_payload()),
            (RESET_URL, {"email": "a@example.com"}),
            (RESET_CONFIRM_URL, {"uid": "x", "token": "y", "new_password": "z"}),
        ],
    )
    def test_anonymous_post_without_token_is_rejected(self, url, payload):
        client = APIClient(enforce_csrf_checks=True)

        response = client.post(url, payload)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_failed"

    def test_login_with_token_passes(self, user):
        client = APIClient(enforce_csrf_checks=True)
        token = client.get(CSRF_URL).json()["csrf_token"]

        response = client.post(
            LOGIN_URL, {"email": user.email, "password": DEFAULT_PASSWORD}, HTTP_X_CSRFTOKEN=token
        )

        assert response.status_code == 200

    def test_authenticated_post_without_token_is_rejected(self, user):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)

        response = client.post(LOGOUT_URL)

        assert response.status_code == 403


class TestRegister:
    def test_creates_user_and_logs_in(self, api_client):
        response = api_client.post(REGISTER_URL, register_payload(email="New@Example.COM"))

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "new@example.com"
        assert body["username"] == "newbie"
        assert "password" not in body
        user = User.objects.get(pk=body["id"])
        assert user.check_password(NEW_PASSWORD)
        assert api_client.get(ME_URL).json()["id"] == user.pk

    def test_duplicate_email_is_case_insensitive(self, api_client):
        UserFactory(email="taken@example.com")

        response = api_client.post(REGISTER_URL, register_payload(email="TAKEN@example.com"))

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert "email" in error["details"]

    def test_duplicate_username_is_case_insensitive(self, api_client):
        UserFactory(username="admin")

        response = api_client.post(REGISTER_URL, register_payload(username="Admin"))

        assert response.status_code == 400
        assert "username" in response.json()["error"]["details"]

    @pytest.mark.parametrize("password", ["short", "12345678901", "newbie2024"])
    def test_weak_password_is_rejected(self, api_client, password):
        response = api_client.post(REGISTER_URL, register_payload(password=password))

        assert response.status_code == 400
        assert "password" in response.json()["error"]["details"]
        assert not User.objects.exists()

    def test_required_fields(self, api_client):
        response = api_client.post(REGISTER_URL, {})

        assert response.status_code == 400
        assert set(response.json()["error"]["details"]) == {"email", "username", "password"}

    def test_race_on_unique_constraint_returns_409(self, api_client, monkeypatch):
        UserFactory(email="taken@example.com")
        # Імітуємо гонку: перевірка серіалізатора пройшла, але запис уже з'явився.
        monkeypatch.setattr(
            "apps.users.serializers.RegisterSerializer.validate_email",
            lambda self, value: value.lower(),
        )

        response = api_client.post(REGISTER_URL, register_payload(email="taken@example.com"))

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_throttled_after_limit(self, api_client, throttle_rates):
        throttle_rates(register="2/hour")

        statuses = [
            api_client.post(
                REGISTER_URL, register_payload(email=f"u{i}@example.com", username=f"u{i}")
            ).status_code
            for i in range(3)
        ]

        # Реєстрація логінить, але ліміт рахується за IP, а не за новим user id.
        assert statuses == [201, 201, 429]


class TestLogin:
    def test_success_with_case_insensitive_email(self, api_client, user):
        response = api_client.post(
            LOGIN_URL, {"email": user.email.upper(), "password": DEFAULT_PASSWORD}
        )

        assert response.status_code == 200
        assert response.json()["id"] == user.pk
        assert "sessionid" in response.cookies
        assert api_client.get(ME_URL).status_code == 200

    def test_wrong_password(self, api_client, user):
        response = login(api_client, user, password="wrong-password")

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert error["details"] == {"non_field_errors": ["Невірний email або пароль."]}
        assert api_client.get(ME_URL).status_code == 401

    def test_unknown_email_gives_same_error_as_wrong_password(self, api_client):
        response = api_client.post(
            LOGIN_URL, {"email": "ghost@example.com", "password": DEFAULT_PASSWORD}
        )

        assert response.status_code == 400
        assert response.json()["error"]["details"] == {
            "non_field_errors": ["Невірний email або пароль."]
        }

    def test_inactive_user_cannot_login(self, api_client):
        user = UserFactory(is_active=False)

        assert login(api_client, user).status_code == 400

    def test_returns_429_after_limit(self, api_client, user, throttle_rates):
        throttle_rates(login="3/min")

        statuses = [login(api_client, user, password="wrong").status_code for _ in range(4)]

        assert statuses == [400, 400, 400, 429]
        # Ліміт діє і на правильний пароль — інакше перебір просто продовжиться.
        response = login(api_client, user)
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "throttled"


class TestLoginEmailThrottle:
    def test_sixth_attempt_on_same_email_from_different_ips_returns_429(
        self, api_client, user, throttle_rates
    ):
        throttle_rates(login_email="5/min")

        statuses = [
            api_client.post(
                LOGIN_URL,
                {"email": user.email, "password": "wrong"},
                REMOTE_ADDR=f"10.0.0.{i}",
            ).status_code
            for i in range(1, 7)
        ]

        assert statuses == [400, 400, 400, 400, 400, 429]
        assert (
            api_client.post(
                LOGIN_URL,
                {"email": user.email, "password": DEFAULT_PASSWORD},
                REMOTE_ADDR="10.0.0.99",
            ).status_code
            == 429
        )

    def test_email_is_normalized_for_the_limit(self, api_client, user, throttle_rates):
        throttle_rates(login_email="2/min")
        variants = [user.email, f"  {user.email.upper()} ", user.email.capitalize()]

        statuses = [
            api_client.post(LOGIN_URL, {"email": email, "password": "wrong"}).status_code
            for email in variants
        ]

        assert statuses == [400, 400, 429]

    def test_other_accounts_are_not_affected(self, api_client, user, throttle_rates):
        throttle_rates(login_email="1/min")
        other = UserFactory()
        login(api_client, user, password="wrong")

        assert login(api_client, other).status_code == 200

    def test_cache_key_does_not_contain_plain_email(self, user):
        request = APIView().initialize_request(
            APIRequestFactory().post(LOGIN_URL, {"email": user.email}, format="json")
        )

        key = LoginEmailThrottle().get_cache_key(request, view=None)

        assert key.startswith("throttle_login_email_")
        assert user.email not in key

    def test_missing_email_is_a_validation_error_not_a_crash(self, api_client):
        response = api_client.post(LOGIN_URL, {"password": "x"})

        assert response.status_code == 400
        assert "email" in response.json()["error"]["details"]


class TestLogoutAndMe:
    def test_logout_ends_session(self, api_client, user):
        login(api_client, user)

        response = api_client.post(LOGOUT_URL)

        assert response.status_code == 204
        assert api_client.get(ME_URL).status_code == 401

    def test_logout_requires_auth(self, api_client):
        assert api_client.post(LOGOUT_URL).status_code == 401

    def test_me_returns_own_profile(self, auth_client, user):
        response = auth_client.get(ME_URL)

        assert response.status_code == 200
        assert response.json() == {
            "id": user.pk,
            "email": user.email,
            "username": user.username,
            "is_staff": False,
            "date_joined": response.json()["date_joined"],
        }

    def test_me_anonymous_returns_401(self, api_client):
        response = api_client.get(ME_URL)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"


class TestPasswordChange:
    def test_success_keeps_current_session(self, api_client, user):
        login(api_client, user)

        response = api_client.post(
            PASSWORD_CHANGE_URL, {"old_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD}
        )

        assert response.status_code == 204
        user.refresh_from_db()
        assert user.check_password(NEW_PASSWORD)
        assert api_client.get(ME_URL).status_code == 200

    def test_other_sessions_are_invalidated(self, user):
        other_device = APIClient()
        login(other_device, user)
        current = APIClient()
        login(current, user)

        current.post(
            PASSWORD_CHANGE_URL, {"old_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD}
        )

        assert other_device.get(ME_URL).status_code == 401

    def test_wrong_old_password(self, auth_client, user):
        response = auth_client.post(
            PASSWORD_CHANGE_URL, {"old_password": "wrong", "new_password": NEW_PASSWORD}
        )

        assert response.status_code == 400
        assert "old_password" in response.json()["error"]["details"]
        user.refresh_from_db()
        assert user.check_password(DEFAULT_PASSWORD)

    def test_weak_new_password(self, auth_client):
        response = auth_client.post(
            PASSWORD_CHANGE_URL, {"old_password": DEFAULT_PASSWORD, "new_password": "123"}
        )

        assert response.status_code == 400
        assert "new_password" in response.json()["error"]["details"]

    def test_requires_auth(self, api_client):
        response = api_client.post(
            PASSWORD_CHANGE_URL, {"old_password": "x", "new_password": NEW_PASSWORD}
        )

        assert response.status_code == 401


class TestEmailIsNotPublic:
    def test_public_user_serializer_exposes_only_id_and_username(self, user):
        assert PublicUserSerializer(user).data == {"id": user.pk, "username": user.username}

    def test_auth_errors_do_not_leak_email(self, api_client, user):
        responses = [
            login(api_client, user, password="wrong"),
            api_client.post(REGISTER_URL, register_payload(email=user.email)),
        ]

        for response in responses:
            assert user.email not in response.content.decode()
