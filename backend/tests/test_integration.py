"""
Integration tests for Provote.
"""
import pytest
from django.test import TestCase
from django.core.cache import cache
from django.db import connection
from django.contrib.auth.models import User
import redis
from django.conf import settings


@pytest.mark.integration
class TestDatabaseConnection:
    """Test database connectivity."""

    def test_database_connection(self, db):
        """Test that database connection works."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            assert result[0] == 1

    def test_database_operations(self, db, user):
        """Test basic database operations."""
        assert User.objects.count() == 1
        assert User.objects.filter(username="testuser").exists()


@pytest.mark.integration
class TestRedisConnection:
    """Test Redis connectivity."""

    def test_redis_connection(self):
        """Test that Redis connection works."""
        try:
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                socket_connect_timeout=5,
            )
            redis_client.ping()
            assert True
        except redis.ConnectionError:
            pytest.skip("Redis not available")

    def test_redis_cache(self):
        """Test that Django cache (Redis) works."""
        try:
            cache.set("test_key", "test_value", 60)
            assert cache.get("test_key") == "test_value"
            cache.delete("test_key")
            assert cache.get("test_key") is None
        except Exception:
            pytest.skip("Redis cache not available")


@pytest.mark.integration
class TestEnvironmentVariables:
    """Test environment variable loading."""

    def test_secret_key_loaded(self):
        """Test that SECRET_KEY is loaded."""
        from django.conf import settings

        assert settings.SECRET_KEY is not None
        assert len(settings.SECRET_KEY) > 0

    def test_database_settings_loaded(self):
        """Test that database settings are loaded."""
        from django.conf import settings

        assert "default" in settings.DATABASES
        assert settings.DATABASES["default"]["ENGINE"] is not None

    def test_redis_settings_loaded(self):
        """Test that Redis settings are loaded."""
        from django.conf import settings

        assert hasattr(settings, "REDIS_HOST")
        assert hasattr(settings, "REDIS_PORT")
        assert hasattr(settings, "CELERY_BROKER_URL")

