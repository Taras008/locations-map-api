"""Базові налаштування. Усе, що відрізняється між середовищами, читається з env."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env_str(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Environment variable {name} is required")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = env_str("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "common",
    "apps.users",
    "apps.locations",
    "apps.reviews",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("POSTGRES_DB", "locations"),
        "USER": env_str("POSTGRES_USER", "locations"),
        "PASSWORD": env_str("POSTGRES_PASSWORD", "locations"),
        "HOST": env_str("POSTGRES_HOST", "localhost"),
        "PORT": env_int("POSTGRES_PORT", 5432),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
        "CONN_HEALTH_CHECKS": True,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Redis / cache ---
REDIS_URL = env_str("REDIS_URL", "redis://localhost:6379/0")
REDIS_HEALTHCHECK_TIMEOUT = env_float("REDIS_HEALTHCHECK_TIMEOUT", 1.0)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": env_float("REDIS_SOCKET_TIMEOUT", 1.0),
            "SOCKET_TIMEOUT": env_float("REDIS_SOCKET_TIMEOUT", 1.0),
            # Падіння Redis не повинно ламати запити: кеш просто "промахується".
            "IGNORE_EXCEPTIONS": True,
        },
        "KEY_PREFIX": "locations",
    }
}
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True

# --- Auth ---
AUTH_USER_MODEL = "users.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 24 * 14)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "common.exceptions.csrf_failure"
# Термін дії посилання для скидання пароля, секунд.
PASSWORD_RESET_TIMEOUT = env_int("PASSWORD_RESET_TIMEOUT", 60 * 60 * 24)

# --- i18n ---
LANGUAGE_CODE = "uk"
TIME_ZONE = env_str("TIME_ZONE", "Europe/Kyiv")
USE_I18N = True
USE_TZ = True

# --- Static ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- CORS / CSRF ---
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
FRONTEND_URL = env_str("FRONTEND_URL", "http://localhost:3000")

# --- Proxies ---
# Скільки довірених проксі стоїть перед застосунком (див. common.http.get_client_ip).
NUM_PROXIES = env_int("TRUSTED_PROXY_COUNT", 0)

# --- DRF ---
PAGE_SIZE = env_int("API_PAGE_SIZE", 20)
MAX_PAGE_SIZE = env_int("API_MAX_PAGE_SIZE", 100)

# --- Reviews ---
REVIEW_COMMENT_MAX_LENGTH = env_int("REVIEW_COMMENT_MAX_LENGTH", 2000)

# --- Popularity ---
# Формула — у docstring apps.locations.selectors.annotate_stats.
POPULARITY_BAYES_M = env_int("POPULARITY_BAYES_M", 5)
POPULARITY_BAYES_C = env_float("POPULARITY_BAYES_C", 3.0)
POPULARITY_QUALITY_POWER = env_float("POPULARITY_QUALITY_POWER", 2.0)
POPULARITY_WEIGHT_REVIEWS = env_float("POPULARITY_WEIGHT_REVIEWS", 1.5)
POPULARITY_WEIGHT_VIEWS = env_float("POPULARITY_WEIGHT_VIEWS", 1.0)
# Вікно для views_7d (днів).
POPULARITY_VIEWS_WINDOW_DAYS = env_int("POPULARITY_VIEWS_WINDOW_DAYS", 7)

# --- Views ---
# Повторний перегляд тим самим відвідувачем протягом цього часу (секунд) не рахується.
LOCATION_VIEW_DEDUP_TTL = env_int("LOCATION_VIEW_DEDUP_TTL", 60 * 60)

# --- List cache / export ---
# TTL кешу відповіді списку локацій, секунд (див. apps.locations.caching).
LOCATIONS_LIST_CACHE_TTL = env_int("LOCATIONS_LIST_CACHE_TTL", 5 * 60)
# Максимум рядків в одному файлі експорту.
EXPORT_MAX_ROWS = env_int("EXPORT_MAX_ROWS", 10_000)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "common.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.DefaultPagination",
    "PAGE_SIZE": PAGE_SIZE,
    "EXCEPTION_HANDLER": "common.exceptions.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "common.throttles.AnonThrottle",
        "common.throttles.UserThrottle",
    ],
    "NUM_PROXIES": NUM_PROXIES,
    "DEFAULT_THROTTLE_RATES": {
        "anon": env_str("THROTTLE_ANON", "60/min"),
        "user": env_str("THROTTLE_USER", "300/min"),
        "login": env_str("THROTTLE_LOGIN", "10/min"),
        "login_email": env_str("THROTTLE_LOGIN_EMAIL", "5/min"),
        "register": env_str("THROTTLE_REGISTER", "5/hour"),
        "password_reset": env_str("THROTTLE_PASSWORD_RESET", "5/hour"),
        "password_reset_confirm": env_str("THROTTLE_PASSWORD_RESET_CONFIRM", "10/hour"),
        "export": env_str("THROTTLE_EXPORT", "10/min"),
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Locations Map API",
    "DESCRIPTION": "API сервісу популярності локацій: локації, відгуки, рейтинг, популярність.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "ENUM_NAME_OVERRIDES": {"HealthStatusEnum": ["ok", "error"]},
}

# --- Celery ---
CELERY_BROKER_URL = env_str("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 60)
CELERY_TIMEZONE = TIME_ZONE
# Не перехоплювати root logger: логи worker'а йдуть через LOGGING (див. config/celery.py).
CELERY_WORKER_HIJACK_ROOT_LOGGER = False

# --- Email ---
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env_str("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 1025)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "Locations Map <noreply@locations.local>")
# Ретраї email-задач Celery: кількість повторів і експоненційна затримка (секунд, база).
EMAIL_TASK_MAX_RETRIES = env_int("EMAIL_TASK_MAX_RETRIES", 3)
EMAIL_TASK_RETRY_BACKOFF = env_int("EMAIL_TASK_RETRY_BACKOFF", 10)

# --- Logging ---
LOG_LEVEL = env_str("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = env_str("LOG_FORMAT", "json")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "common.logging.JsonFormatter"},
        "text": {"format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"},
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": LOG_FORMAT if LOG_FORMAT in {"json", "text"} else "json",
        },
    },
    "root": {"handlers": ["stdout"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["stdout"], "level": LOG_LEVEL, "propagate": False},
        "django.db.backends": {"level": "WARNING"},
        "celery": {"handlers": ["stdout"], "level": LOG_LEVEL, "propagate": False},
    },
}
