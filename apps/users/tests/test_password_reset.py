import html
import re
from smtplib import SMTPException
from unittest import mock

import pytest
from django.conf import settings as django_settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient

from apps.users.tasks import format_duration, send_password_reset_email
from apps.users.tests.factories import DEFAULT_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db

RESET_URL = "/api/v1/auth/password/reset/"
CONFIRM_URL = "/api/v1/auth/password/reset/confirm/"
NEW_PASSWORD = "Brand-new-pass-42"


def make_uid(user) -> str:
    return urlsafe_base64_encode(force_bytes(user.pk))


def request_reset(client, email: str, capture_on_commit):
    with capture_on_commit(execute=True):
        return client.post(RESET_URL, {"email": email})


def extract_link_params(body: str) -> dict:
    match = re.search(r"http://frontend\.test/reset-password\?uid=([\w-]+)&token=([\w-]+)", body)
    assert match, body
    return {"uid": match.group(1), "token": match.group(2)}


@pytest.fixture(autouse=True)
def _frontend_url(settings):
    settings.FRONTEND_URL = "http://frontend.test/"


class TestPasswordResetRequest:
    def test_sends_email_with_frontend_link(
        self, api_client, user, django_capture_on_commit_callbacks
    ):
        response = request_reset(api_client, user.email.upper(), django_capture_on_commit_callbacks)

        assert response.status_code == 204
        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert message.to == [user.email]
        assert "\n" not in message.subject
        html_body = message.alternatives[0][0]
        assert extract_link_params(message.body) == extract_link_params(html.unescape(html_body))

    def test_email_is_sent_only_after_commit(self, api_client, user):
        with mock.patch("apps.users.services.send_password_reset_email.delay") as delay:
            api_client.post(RESET_URL, {"email": user.email})

        # У тестовій транзакції on_commit не спрацьовує — задачу ще не поставлено.
        delay.assert_not_called()

    def test_broker_down_still_returns_204(
        self, api_client, user, django_capture_on_commit_callbacks
    ):
        # Інакше 500 для відомого email і 204 для невідомого розкривали б існування акаунта.
        with mock.patch(
            "apps.users.services.send_password_reset_email.delay",
            side_effect=OperationalError("broker down"),
        ) as delay:
            response = request_reset(api_client, user.email, django_capture_on_commit_callbacks)

        assert response.status_code == 204
        delay.assert_called_once_with(user.pk)

    def test_unknown_email_returns_204_without_email(
        self, api_client, django_capture_on_commit_callbacks
    ):
        response = request_reset(
            api_client, "ghost@example.com", django_capture_on_commit_callbacks
        )

        assert response.status_code == 204
        assert response.content == b""
        assert mail.outbox == []

    def test_inactive_user_gets_no_email(self, api_client, django_capture_on_commit_callbacks):
        user = UserFactory(is_active=False)

        response = request_reset(api_client, user.email, django_capture_on_commit_callbacks)

        assert response.status_code == 204
        assert mail.outbox == []

    def test_invalid_email_format(self, api_client):
        response = api_client.post(RESET_URL, {"email": "not-an-email"})

        assert response.status_code == 400
        assert "email" in response.json()["error"]["details"]

    def test_throttled_after_limit(self, api_client, throttle_rates):
        throttle_rates(password_reset="2/hour")

        statuses = [
            api_client.post(RESET_URL, {"email": "ghost@example.com"}).status_code for _ in range(3)
        ]

        assert statuses == [204, 204, 429]


class TestPasswordResetConfirm:
    def test_has_own_throttle_scope(self, api_client, throttle_rates):
        throttle_rates(password_reset="1/hour", password_reset_confirm="2/hour")
        api_client.post(RESET_URL, {"email": "ghost@example.com"})
        payload = {"uid": "x", "token": "y", "new_password": NEW_PASSWORD}

        statuses = [api_client.post(CONFIRM_URL, payload).status_code for _ in range(3)]

        # Вичерпаний ліміт запитів листа не блокує підтвердження, і навпаки.
        assert statuses == [400, 400, 429]
        assert api_client.post(RESET_URL, {"email": "ghost@example.com"}).status_code == 429

    def test_full_flow_from_email(self, api_client, user, django_capture_on_commit_callbacks):
        request_reset(api_client, user.email, django_capture_on_commit_callbacks)
        params = extract_link_params(mail.outbox[0].body)

        response = api_client.post(CONFIRM_URL, {**params, "new_password": NEW_PASSWORD})

        assert response.status_code == 204
        user.refresh_from_db()
        assert user.check_password(NEW_PASSWORD)
        assert (
            api_client.post(
                "/api/v1/auth/login/", {"email": user.email, "password": NEW_PASSWORD}
            ).status_code
            == 200
        )

    def test_success_ends_existing_sessions(self, api_client, user):
        stolen_session = APIClient()
        stolen_session.force_login(user)
        payload = {
            "uid": make_uid(user),
            "token": default_token_generator.make_token(user),
            "new_password": NEW_PASSWORD,
        }

        assert api_client.post(CONFIRM_URL, payload).status_code == 204

        assert stolen_session.get("/api/v1/auth/me/").status_code == 401

    def test_token_is_single_use(self, api_client, user):
        payload = {
            "uid": make_uid(user),
            "token": default_token_generator.make_token(user),
            "new_password": NEW_PASSWORD,
        }
        assert api_client.post(CONFIRM_URL, payload).status_code == 204

        response = api_client.post(CONFIRM_URL, {**payload, "new_password": "Yet-another-pass-7"})

        assert response.status_code == 400
        assert "token" in response.json()["error"]["details"]

    @pytest.mark.parametrize(
        ("uid", "token"),
        [
            ("valid", "wrong-token"),
            ("!!!", "valid"),
            (urlsafe_base64_encode(b"999999"), "valid"),
            (urlsafe_base64_encode(b"abc"), "valid"),
        ],
    )
    def test_invalid_uid_or_token(self, api_client, user, uid, token):
        payload = {
            "uid": make_uid(user) if uid == "valid" else uid,
            "token": default_token_generator.make_token(user) if token == "valid" else token,
            "new_password": NEW_PASSWORD,
        }

        response = api_client.post(CONFIRM_URL, payload)

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert "token" in error["details"]
        user.refresh_from_db()
        assert user.check_password(DEFAULT_PASSWORD)

    def test_weak_new_password(self, api_client, user):
        payload = {
            "uid": make_uid(user),
            "token": default_token_generator.make_token(user),
            "new_password": "123",
        }

        response = api_client.post(CONFIRM_URL, payload)

        assert response.status_code == 400
        assert "new_password" in response.json()["error"]["details"]


class TestPasswordResetTask:
    def test_retry_policy_comes_from_settings(self):
        assert send_password_reset_email.max_retries == django_settings.EMAIL_TASK_MAX_RETRIES
        assert send_password_reset_email.max_retries == 3

    def test_short_timeout_is_shown_in_minutes(self, user, settings):
        settings.PASSWORD_RESET_TIMEOUT = 30 * 60

        send_password_reset_email(user.pk)

        assert "дійсне 30 хв." in mail.outbox[0].body

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [(86400, "24 год."), (3600, "1 год."), (5400, "1 год."), (1800, "30 хв."), (10, "1 хв.")],
    )
    def test_format_duration(self, seconds, expected):
        assert format_duration(seconds) == expected

    def test_skips_missing_user(self):
        send_password_reset_email(999_999)

        assert mail.outbox == []

    def test_retries_on_smtp_error(self, user):
        with (
            mock.patch("apps.users.tasks.send_templated_email", side_effect=SMTPException),
            mock.patch.object(
                send_password_reset_email, "retry", side_effect=RuntimeError
            ) as retry,
            pytest.raises(RuntimeError),
        ):
            send_password_reset_email.apply(args=[user.pk], throw=True)

        retry.assert_called_once()
