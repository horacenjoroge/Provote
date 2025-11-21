"""
Test settings for Provote project using PostgreSQL.

This file can be used to run tests against PostgreSQL instead of SQLite.
Usage: pytest --ds=config.settings.test_postgresql
"""

import os
from pathlib import Path

from .base import *  # noqa: F403, F401

# Use PostgreSQL for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("TEST_DB_NAME", "provote_test_db"),
        "USER": os.environ.get("DB_USER", "provote_user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "provote_password"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5433"),  # Docker Compose uses 5433
        "OPTIONS": {
            "connect_timeout": 10,
        },
        "TEST": {
            "NAME": "test_provote_db",  # Separate test database
        },
    }
}

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
DATABASES["default"]["TEST"]["SERIALIZE"] = False

# Use Redis for cache and channel layer if available, otherwise fallback to in-memory/dummy
# This allows Redis integration tests to run when Redis is available
try:
    import redis
    redis_client = redis.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        db=int(os.environ.get("REDIS_DB", 0)),
        socket_connect_timeout=2,
    )
    redis_client.ping()
    # Redis is available - use it for cache and channels
    REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
    REDIS_DB = int(os.environ.get("REDIS_DB", 0))
    
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
            "KEY_PREFIX": "provote_test",
        }
    }
    
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [(REDIS_HOST, REDIS_PORT)],
            },
        },
    }
except Exception:
    # Redis not available - use in-memory/dummy fallbacks
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }
    
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            "LOCATION": "unique-snowflake",
        }
    }

# Disable migrations for faster tests (optional)
# Uncomment to skip migrations during tests
# class DisableMigrations:
#     def __contains__(self, item):
#         return True
#
#     def __getitem__(self, item):
#         return None
#
# MIGRATION_MODULES = DisableMigrations()

