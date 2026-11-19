from unittest import mock

import pytest
from django.core import mail
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient

from apps.locations.tests.factories import LocationFactory
from apps.notifications.tests.factories import LocationSubscriptionFactory
from apps.reviews.models import Review
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PAYLOAD = {"rating": 5, "comment": "Чудовий краєвид"}


@pytest.fixture(autouse=True)
def _frontend_url(settings):
    settings.FRONTEND_URL = "http://frontend.test/"


@pytest.fixture
def location():
    return LocationFactory()


@pytest.fixture
def reviewer():
    return UserFactory()


@pytest.fixture
def post_review(reviewer, django_capture_on_commit_callbacks):
    def post(location, user=None):
        client = APIClient()
        client.force_authenticate(user or reviewer)
        with django_capture_on_commit_callbacks(execute=True):
            return client.post(f"/api/v1/locations/{location.pk}/reviews/", PAYLOAD)

    return post


def recipients() -> list[str]:
    return sorted(email for message in mail.outbox for email in message.to)


class TestRecipients:
    def test_location_author_is_notified(self, post_review, location, reviewer):
        response = post_review(location)

        assert response.status_code == 201
        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert message.to == [location.author.email]
        assert location.name in message.subject
        assert "\n" not in message.subject
        assert "ви автор цієї локації" in message.body
        assert reviewer.username in message.body
        assert "http://frontend.test/locations/" in message.body
        assert message.alternatives[0][1] == "text/html"

    def test_subscribers_are_notified_one_email_each(self, post_review, location):
        subscribers = [
            s.user for s in LocationSubscriptionFactory.create_batch(3, location=location)
        ]

        post_review(location)

        assert len(mail.outbox) == 4
        assert all(len(message.to) == 1 for message in mail.outbox)
        assert recipients() == sorted([location.author.email, *(u.email for u in subscribers)])
        subscriber_message = next(m for m in mail.outbox if m.to == [subscribers[0].email])
        assert "підписані на нові відгуки" in subscriber_message.body

    def test_review_author_is_not_notified(self, post_review, location, reviewer):
        LocationSubscriptionFactory(location=location, user=reviewer)

        post_review(location)

        assert recipients() == [location.author.email]

    def test_author_subscribed_to_own_location_gets_one_email(self, post_review, location):
        LocationSubscriptionFactory(location=location, user=location.author)

        post_review(location)

        assert recipients() == [location.author.email]

    def test_other_locations_subscribers_are_not_notified(self, post_review, location):
        LocationSubscriptionFactory()

        post_review(location)

        assert recipients() == [location.author.email]

    def test_unsubscribed_user_is_not_notified(self, post_review, location):
        subscription = LocationSubscriptionFactory(location=location)
        subscription.delete()

        post_review(location)

        assert recipients() == [location.author.email]

    def test_inactive_users_are_not_notified(self, post_review):
        location = LocationFactory(author=UserFactory(is_active=False))
        LocationSubscriptionFactory(location=location, user=UserFactory(is_active=False))

        post_review(location)

        assert mail.outbox == []

    def test_reviewer_email_is_not_disclosed(self, post_review, location, reviewer):
        LocationSubscriptionFactory(location=location)

        post_review(location)

        for message in mail.outbox:
            assert reviewer.email not in message.body
            assert reviewer.email not in message.alternatives[0][0]

    def test_comment_is_escaped_in_html(
        self, location, reviewer, django_capture_on_commit_callbacks
    ):
        client = APIClient()
        client.force_authenticate(reviewer)
        with django_capture_on_commit_callbacks(execute=True):
            client.post(
                f"/api/v1/locations/{location.pk}/reviews/",
                {"rating": 4, "comment": "<script>alert(1)</script>"},
            )

        html_body = mail.outbox[0].alternatives[0][0]
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body


class TestDelivery:
    def test_queued_only_after_commit(self, location, reviewer):
        client = APIClient()
        client.force_authenticate(reviewer)
        with mock.patch("apps.notifications.services.send_new_review_notifications.delay") as delay:
            client.post(f"/api/v1/locations/{location.pk}/reviews/", PAYLOAD)

        # У тестовій транзакції on_commit не спрацьовує — задачу ще не поставлено.
        delay.assert_not_called()

    def test_queued_with_review_id(self, post_review, location):
        with mock.patch("apps.notifications.services.send_new_review_notifications.delay") as delay:
            response = post_review(location)

        delay.assert_called_once_with(response.data["id"])

    def test_broker_down_still_creates_review(self, post_review, location):
        with mock.patch(
            "apps.notifications.services.send_new_review_notifications.delay",
            side_effect=OperationalError("broker down"),
        ):
            response = post_review(location)

        assert response.status_code == 201
        assert Review.objects.filter(pk=response.data["id"]).exists()
        assert mail.outbox == []

    def test_rejected_review_sends_nothing(self, post_review, location):
        response = post_review(location, user=location.author)

        assert response.status_code == 400
        assert mail.outbox == []

    def test_review_update_sends_nothing(
        self, post_review, location, reviewer, django_capture_on_commit_callbacks
    ):
        review_id = post_review(location).data["id"]
        mail.outbox.clear()
        client = APIClient()
        client.force_authenticate(reviewer)

        with django_capture_on_commit_callbacks(execute=True):
            client.patch(f"/api/v1/reviews/{review_id}/", {"rating": 1})

        assert mail.outbox == []
