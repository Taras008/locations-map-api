from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    @staticmethod
    def normalize_email_address(email: str) -> str:
        # Email унікальний без урахування регістру — зберігаємо в нижньому регістрі.
        return email.strip().lower()

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)

    def _create_user(self, email: str, username: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        if not username:
            raise ValueError("Username is required")
        user = self.model(
            email=self.normalize_email_address(email),
            username=self.model.normalize_username(username),
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, username: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, username, password, **extra_fields)

    def create_superuser(self, email: str, username: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra["is_staff"] is not True or extra["is_superuser"] is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True")
        return self._create_user(email, username, password, **extra)
