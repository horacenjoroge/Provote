"""
Tests for sliding window rate limiter.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock

from core.utils.rate_limiter import SlidingWindowRateLimiter, get_rate_limiter


class TestSlidingWindowRateLimiter:
    """Tests for SlidingWindowRateLimiter."""

    def test_rate_limiter_initialization(self):
        """Test rate limiter initializes correctly."""
        limiter = SlidingWindowRateLimiter()
        assert limiter.cache_key_prefix == "rate_limit"

    def test_rate_limiter_custom_prefix(self):
        """Test rate limiter with custom prefix."""
        limiter = SlidingWindowRateLimiter(cache_key_prefix="custom")
        assert limiter.cache_key_prefix == "custom"

    @patch("django_redis.get_redis_connection")
    def test_check_rate_limit_allows_request(self, mock_get_redis):
        """Test rate limiter allows request within limit."""
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        
        # Mock Redis operations
        mock_redis.zremrangebyscore.return_value = 0
        mock_redis.zcard.return_value = 5  # 5 requests already
        mock_redis.zrange.return_value = [(str(int(time.time()) - 30), int(time.time()) - 30)]
        mock_redis.expire.return_value = True
        
        limiter = SlidingWindowRateLimiter()
        is_allowed, info = limiter.check_rate_limit(
            identifier="test_user",
            limit=10,
            window_seconds=60,
            identifier_type="user"
        )
        
        assert is_allowed is True
        assert info["remaining"] >= 0
        assert info["limit"] == 10
        assert "reset" in info

    @patch("django_redis.get_redis_connection")
    def test_check_rate_limit_blocks_request(self, mock_get_redis):
        """Test rate limiter blocks request when limit exceeded."""
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        
        # Mock Redis operations - limit exceeded
        mock_redis.zremrangebyscore.return_value = 0
        mock_redis.zcard.return_value = 10  # Already at limit
        mock_redis.zrange.return_value = [(str(int(time.time()) - 30), int(time.time()) - 30)]
        
        limiter = SlidingWindowRateLimiter()
        is_allowed, info = limiter.check_rate_limit(
            identifier="test_user",
            limit=10,
            window_seconds=60,
            identifier_type="user"
        )
        
        assert is_allowed is False
        assert info["remaining"] == 0
        assert info["limit"] == 10

    @patch("django_redis.get_redis_connection")
    def test_check_rate_limit_redis_failure(self, mock_get_redis):
        """Test rate limiter handles Redis failures gracefully."""
        mock_get_redis.side_effect = Exception("Redis connection failed")
        
        limiter = SlidingWindowRateLimiter()
        is_allowed, info = limiter.check_rate_limit(
            identifier="test_user",
            limit=10,
            window_seconds=60,
            identifier_type="user"
        )
        
        # Should allow request on Redis failure (fail open)
        assert is_allowed is True
        assert info["limit"] == 10

    @patch("django_redis.get_redis_connection")
    def test_get_rate_limit_info(self, mock_get_redis):
        """Test getting rate limit info without incrementing."""
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        
        mock_redis.zremrangebyscore.return_value = 0
        mock_redis.zcard.return_value = 3
        mock_redis.zrange.return_value = [(str(int(time.time()) - 20), int(time.time()) - 20)]
        
        limiter = SlidingWindowRateLimiter()
        info = limiter.get_rate_limit_info(
            identifier="test_user",
            limit=10,
            window_seconds=60,
            identifier_type="user"
        )
        
        assert info["remaining"] == 7  # 10 - 3
        assert info["limit"] == 10
        assert "reset" in info

    def test_get_rate_limiter_singleton(self):
        """Test get_rate_limiter returns singleton."""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        assert limiter1 is limiter2

