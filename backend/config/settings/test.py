"""
Test settings for Provote project.
"""

from pathlib import Path

from .base import *  # noqa: F403, F401

# Use file-based database for tests in a reliable location
# pytest-django will automatically create tables and run migrations
# Use a database file in the project directory for CI/CD compatibility
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEST_DB = BASE_DIR / "test_db.sqlite3"
# Ensure parent directory exists
TEST_DB.parent.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(TEST_DB),
        "OPTIONS": {
            "timeout": 20,
        },
    }
}

# Note: Migrations are enabled for CI/CD
# For faster unit tests, use pytest with --nomigrations flag
# MIGRATION_MODULES = DisableMigrations()

# Password hashing for tests (faster)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable security features for tests
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Celery configuration for tests (synchronous execution)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable logging during tests
LOGGING_CONFIG = None

# Disable database serialization for tests
# This prevents Django from trying to serialize the database during test setup
# which fails when migrations haven't created all tables yet
# List all apps to prevent serialization
TEST_NON_SERIALIZED_APPS = [
    "admin",
    "auth",
    "contenttypes",
    "sessions",
    "django_celery_beat",
    "django_celery_results",
    "apps.polls",
    "apps.votes",
    "apps.users",
    "apps.analytics",
]

# Override cache configuration for tests to use dummy backend
# This avoids Redis connection issues during tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Override Celery configuration for tests (synchronous execution)
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# Static directory will be created by the workflow
# This is handled in .github/workflows/test.yml
