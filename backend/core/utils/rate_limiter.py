"""
Advanced rate limiting utility with sliding window algorithm.

Provides:
- Sliding window rate limiting using Redis
- Per-endpoint, per-user, and per-IP rate limiting
- Rate limit headers in responses
- Admin bypass support
"""

import time
from typing import Dict, Tuple





class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter using Redis sorted sets.

    Uses Redis sorted sets to implement a proper sliding window algorithm
    that tracks requests within a time window.
    """

    def __init__(self, cache_key_prefix: str = "rate_limit"):
        """
        Initialize rate limiter.

        Args:
            cache_key_prefix: Prefix for Redis keys
        """
        self.cache_key_prefix = cache_key_prefix

    def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        identifier_type: str = "ip",
    ) -> Tuple[bool, Dict[str, int]]:
        """
        Check if identifier has exceeded rate limit using sliding window.

        Args:
            identifier: IP address, user ID, or other identifier
            limit: Maximum number of requests allowed
            window_seconds: Time window in seconds
            identifier_type: Type of identifier ('ip', 'user', 'endpoint')

        Returns:
            Tuple of (is_allowed: bool, rate_limit_info: dict)
            rate_limit_info contains:
                - remaining: Number of requests remaining
                - reset: Unix timestamp when limit resets
                - limit: The rate limit value
        """
        cache_key = f"{self.cache_key_prefix}:{identifier_type}:{identifier}"
        now = int(time.time())
        window_start = now - window_seconds

        try:
            # Get Redis client from django-redis
            from django_redis import get_redis_connection

            redis_client = get_redis_connection("default")

            # Remove expired entries (older than window_start)
            redis_client.zremrangebyscore(cache_key, 0, window_start)

            # Count current requests in window
            current_count = redis_client.zcard(cache_key)

            # Check if limit exceeded
            if current_count >= limit:
                # Get oldest request timestamp to calculate reset time
                oldest = redis_client.zrange(cache_key, 0, 0, withscores=True)
                if oldest:
                    reset_time = int(oldest[0][1]) + window_seconds
                else:
                    reset_time = now + window_seconds

                return False, {
                    "remaining": 0,
                    "reset": reset_time,
                    "limit": limit,
                }

            # Add current request
            redis_client.zadd(cache_key, {str(now): now})

            # Set expiration on the key (window_seconds + small buffer)
            redis_client.expire(cache_key, window_seconds + 10)

            # Calculate remaining requests
            remaining = max(0, limit - current_count - 1)

            # Calculate reset time (oldest request + window)
            oldest = redis_client.zrange(cache_key, 0, 0, withscores=True)
            if oldest:
                reset_time = int(oldest[0][1]) + window_seconds
            else:
                reset_time = now + window_seconds

            return True, {
                "remaining": remaining,
                "reset": reset_time,
                "limit": limit,
            }

        except Exception as e:
            # If Redis fails, allow request (fail open)
            # In production, you might want to log this
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Rate limiter Redis error: {e}, allowing request")

            # Return permissive values
            return True, {
                "remaining": limit,
                "reset": now + window_seconds,
                "limit": limit,
            }

    def get_rate_limit_info(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        identifier_type: str = "ip",
    ) -> Dict[str, int]:
        """
        Get rate limit information without incrementing counter.

        Args:
            identifier: IP address, user ID, or other identifier
            limit: Maximum number of requests allowed
            window_seconds: Time window in seconds
            identifier_type: Type of identifier

        Returns:
            Dictionary with rate limit information
        """
        cache_key = f"{self.cache_key_prefix}:{identifier_type}:{identifier}"
        now = int(time.time())
        window_start = now - window_seconds

        try:
            from django_redis import get_redis_connection

            redis_client = get_redis_connection("default")

            # Remove expired entries
            redis_client.zremrangebyscore(cache_key, 0, window_start)

            # Count current requests
            current_count = redis_client.zcard(cache_key)

            # Calculate remaining
            remaining = max(0, limit - current_count)

            # Calculate reset time
            oldest = redis_client.zrange(cache_key, 0, 0, withscores=True)
            if oldest:
                reset_time = int(oldest[0][1]) + window_seconds
            else:
                reset_time = now + window_seconds

            return {
                "remaining": remaining,
                "reset": reset_time,
                "limit": limit,
            }

        except Exception:
            # Return permissive values on error
            return {
                "remaining": limit,
                "reset": now + window_seconds,
                "limit": limit,
            }


# Global rate limiter instance
_rate_limiter = None


def get_rate_limiter() -> SlidingWindowRateLimiter:
    """Get or create global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = SlidingWindowRateLimiter()
    return _rate_limiter
