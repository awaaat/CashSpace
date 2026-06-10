import os
from datetime import timedelta
from pathlib import Path
from decimal import Decimal

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Core ──────────────────────────────────────────────────────────────────────

SECRET_KEY = config("SECRET_KEY", default="change-me-in-production")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# ── Apps ──────────────────────────────────────────────────────────────────────

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "django_celery_beat",
    "django_celery_results",
    "channels",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.payments",
    "apps.merchants",
    "apps.notifications",
    "apps.gating",      # NEW: pay‑per‑asset gating
    "apps.creator",     # NEW: simplified creator backend
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware ────────────────────────────────────────────────────────────────

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestLoggingMiddleware",
]

ROOT_URLCONF = "cashspace.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "cashspace.wsgi.application"
ASGI_APPLICATION = "cashspace.asgi.application"

# ── Database ──────────────────────────────────────────────────────────────────

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="cashspace"),
        "USER": config("DB_USER", default="cashspace_user"),
        "PASSWORD": config("DB_PASSWORD", default="cashspace_password"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
    }
}

# ── Auth ──────────────────────────────────────────────────────────────────────

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── REST Framework ────────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/minute",
        "user": "100/minute",
        "auth": "5/minute",
        "payment": "10/minute",
        "checkout": "5/minute",
        "gating_verify": "30/minute",        # NEW
        "gating_verify_batch": "10/minute",  # NEW
    },
}

# ── JWT ───────────────────────────────────────────────────────────────────────

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=60, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.CustomTokenObtainPairSerializer",
}

# ── CORS ──────────────────────────────────────────────────────────────────────

CORS_ALLOWED_ORIGINS = [
    config("FRONTEND_URL", default="http://localhost:3000"),
]
CORS_ALLOW_CREDENTIALS = True

# ── Redis + Celery ────────────────────────────────────────────────────────────

REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "default"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

CELERY_BEAT_SCHEDULE = {
    "poll-open-payments": {
        "task": "payments.poll_open_payments",
        "schedule": 300,
    },
    # NEW: daily cleanup of expired tokens and abandoned sales
    "cleanup-expired-tokens": {
        "task": "gating.cleanup_used_tokens",
        "schedule": 86400,  # once per day
    },
    "revoke-expired-grants": {
        "task": "gating.revoke_expired_grants",
        "schedule": 3600,   # every hour
    },
    "creator-cleanup-abandoned": {
        "task": "creator.cleanup_abandoned_sales",
        "schedule": 3600,
    },
    "creator-daily-analytics": {
        "task": "creator.update_daily_analytics",
        "schedule": 86400,
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# ── Channels ─────────────────────────────────────────────────────────────────

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# ── PayRam ────────────────────────────────────────────────────────────────────

PAYRAM_BASE_URL = config("PAYRAM_BASE_URL", default="https://your-payram-server.com:8443")
PAYRAM_API_KEY = config("PAYRAM_API_KEY", default="placeholder-api-key")
PAYRAM_WEBHOOK_SECRET = config("PAYRAM_WEBHOOK_SECRET", default="placeholder-webhook-secret")

CASHSPACE_COMMISSION_RATE = Decimal(config("CASHSPACE_COMMISSION_RATE", default="0.30"))

MIN_TRANSACTION_USD = config("MIN_TRANSACTION_USD", default=10, cast=float)
MAX_TRANSACTION_USD = config("MAX_TRANSACTION_USD", default=10000, cast=float)

# ── Gating App Configuration (new) ────────────────────────────────────────────
GATING_TOKEN_TYPE = config("GATING_TOKEN_TYPE", default="HMAC")  # UUID, HMAC, JWT, PASETO
GATING_TOKEN_EXPIRY_SECONDS = config("GATING_TOKEN_EXPIRY_SECONDS", default=3600, cast=int)
GATING_TOKEN_MAX_USES = config("GATING_TOKEN_MAX_USES", default=1, cast=int)
GATING_NONCE_PREFIX = "gating:nonce:"
GATING_NONCE_TTL_SECONDS = config("GATING_NONCE_TTL_SECONDS", default=86400, cast=int)
GATING_NONCE_GRACE_SECONDS = config("GATING_NONCE_GRACE_SECONDS", default=300, cast=int)
GATING_VERIFICATION_CACHE_TTL = config("GATING_VERIFICATION_CACHE_TTL", default=5, cast=int)
GATING_VERIFICATION_REQUIRE_SIGNATURE = config("GATING_VERIFICATION_REQUIRE_SIGNATURE", default=False, cast=bool)
GATING_VERIFICATION_SHARED_SECRET = config("GATING_VERIFICATION_SHARED_SECRET", default="")
GATING_PROXY_TIMEOUT = config("GATING_PROXY_TIMEOUT", default=30, cast=int)
GATING_PROXY_STREAM_CHUNK_SIZE = config("GATING_PROXY_STREAM_CHUNK_SIZE", default=8192, cast=int)
GATING_PROXY_MAX_FILE_SIZE = config("GATING_PROXY_MAX_FILE_SIZE", default=2147483648, cast=int)  # 2GB
GATING_PROXY_CACHE_TTL = config("GATING_PROXY_CACHE_TTL", default=300, cast=int)
GATING_PROXY_ALLOW_REWRITE = config("GATING_PROXY_ALLOW_REWRITE", default=True, cast=bool)
GATING_HIGH_VALUE_ALERT_THRESHOLD = config("GATING_HIGH_VALUE_ALERT_THRESHOLD", default=500, cast=float)

# ── Creator App Configuration (new) ───────────────────────────────────────────
CREATOR_AUTO_CREATE_PROFILE = config("CREATOR_AUTO_CREATE_PROFILE", default=True, cast=bool)
CREATOR_DEFAULT_COMMISSION_RATE = Decimal(config("CREATOR_DEFAULT_COMMISSION_RATE", default="0.30"))

# ── Email ─────────────────────────────────────────────────────────────────────

EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="CashSpace <noreply@cashspace.com>")

ADMINS = [
    ("CashSpace Admin", config("ADMIN_EMAIL", default="admin@cashspace.com")),
]

# ── Static / Media ────────────────────────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ── Internationalisation ──────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Misc ──────────────────────────────────────────────────────────────────────

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000")
X_FRAME_OPTIONS = "SAMEORIGIN"

# ── Logging ───────────────────────────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}