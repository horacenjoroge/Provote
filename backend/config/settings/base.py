"""
Base Django settings for Provote project.
"""

from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Initialize environment variables
env = environ.Env(
    DEBUG=(bool, False),
    SECURE_SSL_REDIRECT=(bool, False),
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),
)

# Read .env file
environ.Env.read_env(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party apps
    "rest_framework",
    "corsheaders",
    "django_celery_beat",
    "django_celery_results",
    # Local apps
    "apps.polls",
    "apps.votes",
    "apps.users",
    "apps.analytics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Custom middleware (order matters!)
    "core.middleware.request_id.RequestIDMiddleware",  # First - adds request ID
    "core.middleware.fingerprint.FingerprintMiddleware",  # Second - extracts fingerprint
    "core.middleware.audit_log.AuditLogMiddleware",  # Third - logs requests
    "core.middleware.rate_limit.RateLimitMiddleware",  # Last - rate limiting
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "backend" / "templates"],
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

WSGI_APPLICATION = "config.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "backend" / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "backend" / "static"]

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "backend" / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Redis Configuration
REDIS_HOST = env("REDIS_HOST", default="localhost")
REDIS_PORT = env.int("REDIS_PORT", default=6379)
REDIS_DB = env.int("REDIS_DB", default=0)

# Cache Configuration (Redis)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "provote",
    }
}

# Celery Configuration
CELERY_BROKER_URL = env(
    "CELERY_BROKER_URL", default=f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
)
CELERY_RESULT_BACKEND = env(
    "CELERY_RESULT_BACKEND", default=f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
    "EXCEPTION_HANDLER": "core.exceptions.handlers.custom_exception_handler",
}

# CORS Settings
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# Security Settings (override in production.py)
SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env("CSRF_COOKIE_SECURE", default=False)

# Fingerprint Validation Settings
FINGERPRINT_CHECK_ENABLED = env.bool("FINGERPRINT_CHECK_ENABLED", default=True)
FINGERPRINT_CACHE_TTL = env.int("FINGERPRINT_CACHE_TTL", default=3600)  # 1 hour
FINGERPRINT_TIME_WINDOW_HOURS = env.int("FINGERPRINT_TIME_WINDOW_HOURS", default=24)
FINGERPRINT_ANALYSIS_WINDOW_HOURS = env.int("FINGERPRINT_ANALYSIS_WINDOW_HOURS", default=168)  # 7 days for async analysis
FINGERPRINT_SUSPICIOUS_THRESHOLDS = {
    "different_users": env.int("FP_THRESHOLD_DIFF_USERS", default=2),  # Same fingerprint, different users
    "rapid_votes_minutes": env.int("FP_THRESHOLD_RAPID_MINUTES", default=5),  # Multiple votes within minutes
    "rapid_votes_count": env.int("FP_THRESHOLD_RAPID_COUNT", default=3),  # Number of votes in time window
    "different_ips": env.int("FP_THRESHOLD_DIFF_IPS", default=2),  # Same fingerprint, different IPs
}

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
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
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
