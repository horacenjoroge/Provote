"""
Rate limiting middleware for Provote.
"""

from django.core.cache import cache
from django.http import JsonResponse


class RateLimitMiddleware:
    """
    Simple rate limiting middleware using Django cache.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip rate limiting for admin and static files
        if not request.path.startswith(("/admin/", "/static/", "/media/")):
            # Get client IP
            ip_address = self.get_client_ip(request)

            # Rate limit: 100 requests per minute per IP
            cache_key = f"rate_limit:{ip_address}"
            requests = cache.get(cache_key, 0)

            if requests >= 100:
                return JsonResponse(
                    {"error": "Rate limit exceeded. Please try again later."},
                    status=429,
                )

            # Increment counter
            cache.set(cache_key, requests + 1, 60)  # 60 seconds TTL

        response = self.get_response(request)
        return response

    @staticmethod
    def get_client_ip(request):
        """
        Get the client IP address from the request.
        """
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip
