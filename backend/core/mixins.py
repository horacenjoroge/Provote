"""
Mixin classes for Django REST Framework views.
"""

from rest_framework.response import Response


class RateLimitHeadersMixin:
    """
    Mixin to add rate limit headers to API responses.
    
    Adds standard rate limit headers:
    - X-RateLimit-Limit: The rate limit ceiling
    - X-RateLimit-Remaining: Number of requests left in current window
    - X-RateLimit-Reset: Unix timestamp when the rate limit resets
    """
    
    def finalize_response(self, request, response, *args, **kwargs):
        """Add rate limit headers to response."""
        response = super().finalize_response(request, response, *args, **kwargs)
        
        # Get rate limit info from request (set by throttle)
        if hasattr(request, "rate_limit_info") and request.rate_limit_info:
            # Get the most restrictive limit info (lowest remaining)
            rate_info = min(
                request.rate_limit_info.values(),
                key=lambda x: x.get("remaining", float("inf"))
            )
            
            # Add headers
            response["X-RateLimit-Limit"] = str(rate_info["limit"])
            response["X-RateLimit-Remaining"] = str(rate_info["remaining"])
            response["X-RateLimit-Reset"] = str(rate_info["reset"])
        
        return response

