"""
Redis-based rate limiting middleware for Provote.
Supports both IP-based and user-based rate limiting.
"""

from django.core.cache import cache
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


class RateLimitMiddleware(MiddlewareMixin):
    """
    Redis-based rate limiting middleware.
    Supports rate limiting per IP and per authenticated user.
    """

    # Rate limit configuration
    RATE_LIMIT_PER_IP = 100  # requests per window
    RATE_LIMIT_PER_USER = 1000  # requests per window
    RATE_LIMIT_WINDOW = 60  # seconds

    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)

    def __call__(self, request):
        # Skip rate limiting for admin and static files
        if request.path.startswith(("/admin/", "/static/", "/media/")):
            return self.get_response(request)

        # Bypass rate limiting for load tests
        from django.conf import settings
        if getattr(settings, 'DISABLE_RATE_LIMITING', False):
            return self.get_response(request)
        
        # Check for load test header (allows bypassing rate limits for load tests)
        if request.META.get('HTTP_X_LOAD_TEST') == 'true':
            return self.get_response(request)

        # Get identifiers
        ip_address = self.get_client_ip(request)
        user_id = (
            getattr(request.user, "id", None)
            if hasattr(request, "user") and request.user.is_authenticated
            else None
        )

        # Check IP-based rate limit
        if not self.check_rate_limit(ip_address, "ip"):
            return JsonResponse(
                {
                    "error": "Rate limit exceeded. Please try again later.",
                    "retry_after": self.RATE_LIMIT_WINDOW,
                },
                status=429,
            )

        # Check user-based rate limit (if authenticated)
        if user_id and not self.check_rate_limit(user_id, "user"):
            return JsonResponse(
                {
                    "error": "Rate limit exceeded. Please try again later.",
                    "retry_after": self.RATE_LIMIT_WINDOW,
                },
                status=429,
            )

        response = self.get_response(request)
        return response

    def check_rate_limit(self, identifier, limit_type):
        """
        Check if identifier has exceeded rate limit.

        Args:
            identifier: IP address or user ID
            limit_type: 'ip' or 'user'

        Returns:
            bool: True if within limit, False if exceeded
        """
        if limit_type == "ip":
            limit = self.RATE_LIMIT_PER_IP
            cache_key = f"rate_limit:ip:{identifier}"
        else:
            limit = self.RATE_LIMIT_PER_USER
            cache_key = f"rate_limit:user:{identifier}"

        # Get current count from Redis
        current_count = cache.get(cache_key, 0)

        if current_count >= limit:
            return False

        # Increment counter with sliding window
        # Use Redis INCR which is atomic
        try:
            # Try to increment, if key doesn't exist, set it
            new_count = cache.get_or_set(cache_key, 0, self.RATE_LIMIT_WINDOW)
            new_count = cache.incr(cache_key)

            # If this is the first request, set expiration
            if new_count == 1:
                cache.expire(cache_key, self.RATE_LIMIT_WINDOW)
        except Exception:
            # Fallback if Redis is unavailable - allow request
            return True

        return True

    @staticmethod
    def get_client_ip(request):
        """Get the client IP address from the request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "unknown")
        return ip
