"""
Advanced rate limiting throttles for Django REST Framework.

Provides:
- Granular per-endpoint rate limits
- Sliding window algorithm
- Rate limit headers
- Admin bypass
- Load test bypass
"""

import time
from typing import Optional

from rest_framework.throttling import BaseThrottle, AnonRateThrottle, UserRateThrottle
from rest_framework.exceptions import Throttled

from core.utils.rate_limiter import get_rate_limiter


class LoadTestBypassMixin:
    """Mixin to bypass rate limiting for load tests."""
    
    def allow_request(self, request, view):
        """Check if request should bypass rate limiting."""
        # Check if rate limiting is disabled (for load testing)
        from django.conf import settings
        if getattr(settings, 'DISABLE_RATE_LIMITING', False):
            return True
        
        # Check for load test header (allows bypassing rate limits for load tests)
        if request.META.get('HTTP_X_LOAD_TEST') == 'true':
            return True
        
        # Call parent's allow_request
        return super().allow_request(request, view)


class LoadTestAnonRateThrottle(LoadTestBypassMixin, AnonRateThrottle):
    """Anonymous rate throttle with load test bypass."""
    pass


class LoadTestUserRateThrottle(LoadTestBypassMixin, UserRateThrottle):
    """User rate throttle with load test bypass."""
    pass


class AdvancedRateThrottle(BaseThrottle):
    """
    Advanced rate throttle with sliding window and rate limit headers.
    
    Supports:
    - Per-endpoint rate limits
    - IP-based and user-based limits
    - Admin bypass
    - Rate limit headers in responses
    """
    
    # Override these in subclasses
    scope = "default"
    rate_limit_anon: Optional[int] = None  # Requests per minute for anonymous
    rate_limit_user: Optional[int] = None  # Requests per minute for authenticated
    window_seconds: int = 60  # 1 minute window
    
    def get_ident(self, request):
        """
        Identify the client making the request.
        
        Returns IP address for anonymous users, user ID for authenticated users.
        """
        if request.user and request.user.is_authenticated:
            return f"user:{request.user.id}"
        return f"ip:{self.get_ip_address(request)}"
    
    def get_ip_address(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "unknown")
        return ip
    
    def get_rate_limit(self, request) -> Optional[int]:
        """
        Get rate limit for this request.
        
        Returns:
            Rate limit (requests per minute) or None if no limit
        """
        # Check if rate limiting is disabled (for load testing)
        from django.conf import settings
        if getattr(settings, 'DISABLE_RATE_LIMITING', False):
            return None
        
        # Check for load test header (allows bypassing rate limits for load tests)
        if request.META.get('HTTP_X_LOAD_TEST') == 'true':
            return None
        
        # Check if user is admin (bypass rate limits)
        if request.user and request.user.is_authenticated:
            if request.user.is_staff or request.user.is_superuser:
                return None  # No limit for admins
        
        # Return appropriate limit based on authentication
        if request.user and request.user.is_authenticated:
            return self.rate_limit_user
        return self.rate_limit_anon
    
    def allow_request(self, request, view):
        """
        Check if request should be throttled.
        
        Returns:
            True if request is allowed, False if throttled
        """
        # Get rate limit for this request
        rate_limit = self.get_rate_limit(request)
        
        # No limit (admin or None configured)
        if rate_limit is None:
            return True
        
        # Get identifier
        ident = self.get_ident(request)
        identifier_type = "user" if request.user and request.user.is_authenticated else "ip"
        
        # Add endpoint scope to identifier for per-endpoint limiting
        endpoint_ident = f"{self.scope}:{ident}"
        
        # Check rate limit
        rate_limiter = get_rate_limiter()
        is_allowed, rate_info = rate_limiter.check_rate_limit(
            identifier=endpoint_ident,
            limit=rate_limit,
            window_seconds=self.window_seconds,
            identifier_type=identifier_type,
        )
        
        # Store rate limit info for headers
        if not hasattr(request, "rate_limit_info"):
            request.rate_limit_info = {}
        request.rate_limit_info[self.scope] = rate_info
        
        if not is_allowed:
            # Calculate retry_after
            reset_time = rate_info["reset"]
            retry_after = max(0, reset_time - int(time.time()))
            
            raise Throttled(detail={
                "error": "Rate limit exceeded. Please try again later.",
                "retry_after": retry_after,
                "limit": rate_info["limit"],
                "reset": reset_time,
            })
        
        return True
    
    def wait(self):
        """Return wait time in seconds (not used with sliding window)."""
        return None


class VoteCastRateThrottle(AdvancedRateThrottle):
    """Rate throttle for vote casting endpoint."""
    
    scope = "vote_cast"
    rate_limit_anon = 10  # 10 requests per minute for anonymous
    rate_limit_user = 100  # 100 requests per minute for authenticated


class PollCreateRateThrottle(AdvancedRateThrottle):
    """Rate throttle for poll creation endpoint."""
    
    scope = "poll_create"
    rate_limit_anon = 5  # 5 requests per minute for anonymous (should be authenticated anyway)
    rate_limit_user = 20  # 20 requests per minute for authenticated


class PollReadRateThrottle(AdvancedRateThrottle):
    """Rate throttle for poll read endpoints."""
    
    scope = "poll_read"
    rate_limit_anon = 100  # 100 requests per minute for anonymous
    rate_limit_user = 1000  # 1000 requests per minute for authenticated

