from smtplib import SMTPException
from unittest import mock

import pytest
from django.conf import settings as django_settings
from django.core import mail
from django.core.cache import cache

from apps.notifications.tasks import send_new_review_email, send_new_review_notifications
from apps.notifications.tests.factories import LocationSubscriptionFactory
from apps.reviews.tests.factories import ReviewFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def review():
    return ReviewFactory()


class TestFanOut:
    def test_deleted_review_sends_nothing(self, review):
        review_id = review.pk
        review.delete()

        send_new_review_notifications(review_id)

        assert mail.outbox == []

    def test_soft_deleted_location_sends_nothing(self, review):
        LocationSubscriptionFactory(location=review.location)
        review.location.delete()

        send_new_review_notifications(review.pk)

        assert mail.outbox == []

    def test_retried_fan_out_does_not_duplicate_emails(self, review):
        LocationSubscriptionFactory(location=review.location)

        send_new_review_notifications(review.pk)
        send_new_review_notifications(review.pk)

        assert len(mail.outbox) == 2


class TestSendEmail:
    def test_repeated_delivery_sends_once(self, review):
        author_id = review.location.author_id

        send_new_review_email(review.pk, author_id)
        send_new_review_email(review.pk, author_id)

        assert len(mail.outbox) == 1

    def test_skips_while_another_worker_holds_the_slot(self, review):
        author_id = review.location.author_id
        cache.add(f"notifications:sent:{review.pk}:{author_id}", "sending", 60)

        send_new_review_email(review.pk, author_id)

        assert mail.outbox == []

    def test_sends_when_cache_is_unavailable(self, review):
        # django-redis з IGNORE_EXCEPTIONS повертає None замість помилки.
        with mock.patch("apps.notifications.tasks.cache.add", return_value=None):
            send_new_review_email(review.pk, review.location.author_id)

        assert len(mail.outbox) == 1

    def test_skipped_recipient_does_not_hold_the_slot(self, review):
        subscription = LocationSubscriptionFactory(location=review.location)
        subscription.delete()

        send_new_review_email(review.pk, subscription.user_id)

        assert cache.get(f"notifications:sent:{review.pk}:{subscription.user_id}") is None

    def test_failed_send_does_not_mark_as_sent(self, review):
        author_id = review.location.author_id
        with (
            mock.patch("apps.notifications.tasks.send_templated_email", side_effect=SMTPException),
            pytest.raises(SMTPException),
        ):
            send_new_review_email.run(review.pk, author_id)

        send_new_review_email(review.pk, author_id)

        assert len(mail.outbox) == 1

    def test_unsubscribed_before_delivery_gets_nothing(self, review):
        subscription = LocationSubscriptionFactory(location=review.location)
        subscription.delete()

        send_new_review_email(review.pk, subscription.user_id)

        assert mail.outbox == []

    def test_review_author_never_gets_email(self, review):
        LocationSubscriptionFactory(location=review.location, user=review.author)

        send_new_review_email(review.pk, review.author_id)

        assert mail.outbox == []

    def test_retry_policy_comes_from_settings(self):
        for task in (send_new_review_email, send_new_review_notifications):
            assert task.max_retries == django_settings.EMAIL_TASK_MAX_RETRIES

    def test_retries_on_smtp_error(self, review):
        with (
            mock.patch("apps.notifications.tasks.send_templated_email", side_effect=SMTPException),
            mock.patch.object(send_new_review_email, "retry", side_effect=RuntimeError) as retry,
            pytest.raises(RuntimeError),
        ):
            send_new_review_email.apply(args=[review.pk, review.location.author_id], throw=True)

        retry.assert_called_once()
