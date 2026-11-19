import factory

from apps.users.models import User

DEFAULT_PASSWORD = "S3cure-pass-123"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.Sequence(lambda n: f"user{n}")
    password = factory.PostGenerationMethodCall("set_password", DEFAULT_PASSWORD)

    @factory.post_generation
    def _save_password(obj, create, extracted, **kwargs):
        if create:
            obj.save(update_fields=["password"])
