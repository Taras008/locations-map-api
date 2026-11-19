import pytest
from django.test import Client

from apps.reviews.tests.factories import ReviewReactionFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client_():
    client = Client()
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    return client


@pytest.mark.parametrize("url", ["/admin/reviews/review/", "/admin/reviews/reviewreaction/"])
def test_changelists_open(admin_client_, url):
    ReviewReactionFactory()

    assert admin_client_.get(url).status_code == 200
