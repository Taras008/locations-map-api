import pytest
from django.db import IntegrityError

from apps.users.models import User

pytestmark = pytest.mark.django_db


def test_create_user_normalizes_email_and_hashes_password():
    user = User.objects.create_user(
        email="  John@Example.COM ", username="john", password="pw-12345!"
    )

    assert user.email == "john@example.com"
    assert user.check_password("pw-12345!")
    assert not user.is_staff
    assert not user.is_superuser
    assert str(user) == "john"


def test_email_is_unique_case_insensitive():
    User.objects.create_user(email="john@example.com", username="john", password="x")

    with pytest.raises(IntegrityError):
        User.objects.create(email="JOHN@example.com", username="john2")


def test_get_by_natural_key_is_case_insensitive():
    user = User.objects.create_user(email="john@example.com", username="john", password="x")

    assert User.objects.get_by_natural_key("John@Example.com") == user


def test_create_superuser():
    admin = User.objects.create_superuser(email="admin@example.com", username="admin", password="x")

    assert admin.is_staff
    assert admin.is_superuser


@pytest.mark.parametrize(("email", "username"), [("", "john"), ("john@example.com", "")])
def test_create_user_requires_email_and_username(email, username):
    with pytest.raises(ValueError):
        User.objects.create_user(email=email, username=username, password="x")


def test_create_superuser_rejects_non_staff():
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            email="admin@example.com", username="admin", password="x", is_staff=False
        )


def test_clean_normalizes_email():
    user = User(email=" Mixed@Example.com ", username="mixed")

    user.clean()

    assert user.email == "mixed@example.com"
