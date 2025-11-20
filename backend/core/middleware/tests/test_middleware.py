"""
Comprehensive tests for custom middleware.
"""

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory
from django.http import JsonResponse

from core.middleware.rate_limit import RateLimitMiddleware
from core.middleware.audit_log import AuditLogMiddleware
from core.middleware.fingerprint import FingerprintMiddleware
from core.middleware.request_id import RequestIDMiddleware


@pytest.mark.unit
class TestRateLimitMiddleware:
    """Test rate limiting middleware."""

    def test_rate_limit_blocks_after_threshold(self):
        """Test that rate limiting blocks requests after threshold."""
        from django.conf import settings
        
        # Skip test if rate limiting is disabled or cache is dummy backend
        if getattr(settings, 'DISABLE_RATE_LIMITING', False):
            pytest.skip("Rate limiting is disabled in test environment")
        
        cache_backend = getattr(settings, 'CACHES', {}).get('default', {}).get('BACKEND', '')
        if 'dummy' in cache_backend.lower():
            pytest.skip("Rate limiting requires a functional cache backend (Redis or locmem), not DummyCache")
        
        middleware = RateLimitMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        # Create request
        request = factory.get("/api/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        # Clear cache
        cache.clear()

        # Make requests up to limit
        for i in range(RateLimitMiddleware.RATE_LIMIT_PER_IP):
            response = middleware(request)
            assert response.status_code == 200

        # Next request should be blocked
        response = middleware(request)
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.content.decode()

    def test_rate_limit_resets_after_time_window(self):
        """Test that rate limit resets after time window."""
        middleware = RateLimitMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        request = factory.get("/api/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.2"

        cache.clear()

        # Exceed limit
        for i in range(RateLimitMiddleware.RATE_LIMIT_PER_IP + 1):
            middleware(request)

        # Manually expire the cache key to simulate time window passing
        cache_key = f"rate_limit:ip:{request.META['REMOTE_ADDR']}"
        cache.delete(cache_key)

        # Should be able to make requests again
        response = middleware(request)
        assert response.status_code == 200

    def test_rate_limit_per_user(self, user):
        """Test user-based rate limiting."""
        from django.conf import settings
        
        # Skip test if rate limiting is disabled or cache is dummy backend
        if getattr(settings, 'DISABLE_RATE_LIMITING', False):
            pytest.skip("Rate limiting is disabled in test environment")
        
        cache_backend = getattr(settings, 'CACHES', {}).get('default', {}).get('BACKEND', '')
        if 'dummy' in cache_backend.lower():
            pytest.skip("Rate limiting requires a functional cache backend (Redis or locmem), not DummyCache")
        
        middleware = RateLimitMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        request = factory.get("/api/test/")
        request.user = user
        request.META["REMOTE_ADDR"] = "192.168.1.3"

        cache.clear()

        # Make requests up to user limit
        for i in range(RateLimitMiddleware.RATE_LIMIT_PER_USER):
            response = middleware(request)
            assert response.status_code == 200

        # Next request should be blocked
        response = middleware(request)
        assert response.status_code == 429

    def test_rate_limit_skips_admin(self):
        """Test that admin paths are skipped."""
        middleware = RateLimitMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        request = factory.get("/admin/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        cache.clear()

        # Make many requests - should not be rate limited
        for i in range(200):
            response = middleware(request)
            assert response.status_code == 200


@pytest.mark.django_db
class TestAuditLogMiddleware:
    """Test audit logging middleware."""

    def test_audit_log_created_for_requests(self):
        """Test that audit logs are created for requests."""
        from apps.analytics.models import AuditLog

        middleware = AuditLogMiddleware(
            lambda req: JsonResponse({"ok": True}, status=200)
        )
        factory = RequestFactory()

        request = factory.get("/api/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        request.user = None

        # Clear existing logs
        AuditLog.objects.all().delete()

        # Process request
        middleware(request)

        # Check log was created
        logs = AuditLog.objects.all()
        assert logs.count() == 1
        log = logs.first()
        assert log.method == "GET"
        assert log.path == "/api/test/"
        assert log.status_code == 200
        assert log.ip_address == "192.168.1.1"

    def test_audit_log_includes_user(self, user):
        """Test that audit log includes user information."""
        from apps.analytics.models import AuditLog

        middleware = AuditLogMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        request = factory.post("/api/votes/", data={"poll_id": 1})
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        request.user = user

        AuditLog.objects.all().delete()

        middleware(request)

        log = AuditLog.objects.first()
        assert log.user == user
        assert log.method == "POST"

    def test_audit_log_skips_static_files(self):
        """Test that static files are not logged."""
        from apps.analytics.models import AuditLog

        middleware = AuditLogMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        request = factory.get("/static/css/style.css")
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        AuditLog.objects.all().delete()

        middleware(request)

        assert AuditLog.objects.count() == 0

    def test_audit_log_includes_request_id(self):
        """Test that audit log includes request ID."""
        from apps.analytics.models import AuditLog

        middleware = AuditLogMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        request = factory.get("/api/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        request.request_id = "test-request-id-123"

        AuditLog.objects.all().delete()

        middleware(request)

        log = AuditLog.objects.first()
        assert log.request_id == "test-request-id-123"


@pytest.mark.unit
class TestFingerprintMiddleware:
    """Test fingerprint middleware."""

    def test_fingerprint_extracted_correctly(self):
        """Test that fingerprint is extracted correctly."""
        middleware = FingerprintMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        request = factory.get(
            "/api/test/",
            HTTP_USER_AGENT="Mozilla/5.0",
            HTTP_ACCEPT_LANGUAGE="en-US",
        )

        middleware(request)

        assert hasattr(request, "fingerprint")
        assert len(request.fingerprint) == 64  # SHA256 hex length
        assert isinstance(request.fingerprint, str)

    def test_fingerprint_consistent_for_same_headers(self):
        """Test that same headers produce same fingerprint."""
        middleware = FingerprintMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        headers = {
            "HTTP_USER_AGENT": "Mozilla/5.0",
            "HTTP_ACCEPT_LANGUAGE": "en-US",
        }

        request1 = factory.get("/api/test/", **headers)
        request2 = factory.get("/api/test/", **headers)

        middleware(request1)
        middleware(request2)

        assert request1.fingerprint == request2.fingerprint

    def test_fingerprint_different_for_different_headers(self):
        """Test that different headers produce different fingerprints."""
        middleware = FingerprintMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        request1 = factory.get("/api/test/", HTTP_USER_AGENT="Mozilla/5.0")
        request2 = factory.get("/api/test/", HTTP_USER_AGENT="Chrome/91.0")

        middleware(request1)
        middleware(request2)

        assert request1.fingerprint != request2.fingerprint


@pytest.mark.unit
class TestRequestIDMiddleware:
    """Test request ID middleware."""

    def test_request_id_generated(self):
        """Test that request ID is generated if not present."""
        middleware = RequestIDMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        request = factory.get("/api/test/")

        response = middleware(request)

        assert hasattr(request, "request_id")
        assert request.request_id is not None
        assert "X-Request-ID" in response
        assert response["X-Request-ID"] == request.request_id

    def test_request_id_from_header(self):
        """Test that request ID is taken from header if present."""
        middleware = RequestIDMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        custom_id = "custom-request-id-123"
        request = factory.get("/api/test/", HTTP_X_REQUEST_ID=custom_id)

        response = middleware(request)

        assert request.request_id == custom_id
        assert response["X-Request-ID"] == custom_id


@pytest.mark.integration
class TestMiddlewareOrder:
    """Test that middleware order doesn't break functionality."""

    def test_middleware_chain_works(self, user):
        """Test that all middleware work together correctly."""
        from apps.analytics.models import AuditLog

        # Create middleware chain
        def view(request):
            return JsonResponse({"ok": True, "request_id": request.request_id})

        request_id_middleware = RequestIDMiddleware(view)
        fingerprint_middleware = FingerprintMiddleware(request_id_middleware)
        audit_middleware = AuditLogMiddleware(fingerprint_middleware)
        rate_limit_middleware = RateLimitMiddleware(audit_middleware)

        factory = RequestFactory()
        request = factory.get("/api/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        request.user = user

        cache.clear()
        AuditLog.objects.all().delete()

        response = rate_limit_middleware(request)

        # Check all middleware worked
        assert response.status_code == 200
        assert hasattr(request, "request_id")
        assert hasattr(request, "fingerprint")
        assert AuditLog.objects.count() == 1
        assert "X-Request-ID" in response

        # Check audit log has all fields
        log = AuditLog.objects.first()
        # The request_id should be set by RequestIDMiddleware before AuditLogMiddleware reads it
        # RequestIDMiddleware is the innermost, so it runs first and sets request.request_id
        # AuditLogMiddleware now reads request_id after get_response(), so it should capture it
        assert log.request_id == request.request_id, f"Expected request_id '{request.request_id}', got '{log.request_id}'"
        assert log.user == user

    def test_rate_limit_with_forwarded_for_header(self):
        """Test rate limiting with X-Forwarded-For header."""
        from django.conf import settings
        
        # Skip test if rate limiting is disabled or cache is dummy backend
        if getattr(settings, 'DISABLE_RATE_LIMITING', False):
            pytest.skip("Rate limiting is disabled in test environment")
        
        cache_backend = getattr(settings, 'CACHES', {}).get('default', {}).get('BACKEND', '')
        if 'dummy' in cache_backend.lower():
            pytest.skip("Rate limiting requires a functional cache backend (Redis or locmem), not DummyCache")
        
        middleware = RateLimitMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        request = factory.get(
            "/api/test/",
            HTTP_X_FORWARDED_FOR="192.168.1.100, 10.0.0.1",
        )

        cache.clear()

        # Make requests up to limit
        for i in range(RateLimitMiddleware.RATE_LIMIT_PER_IP):
            response = middleware(request)
            assert response.status_code == 200

        # Next request should be blocked
        response = middleware(request)
        assert response.status_code == 429

    @pytest.mark.django_db
    def test_audit_log_includes_response_time(self):
        """Test that audit log includes response time."""
        import time
        from apps.analytics.models import AuditLog

        def slow_view(request):
            time.sleep(0.1)  # Simulate slow response
            return JsonResponse({"ok": True})

        middleware = AuditLogMiddleware(slow_view)
        factory = RequestFactory()

        request = factory.get("/api/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        AuditLog.objects.all().delete()

        middleware(request)

        log = AuditLog.objects.first()
        assert log.response_time > 0
        assert log.response_time >= 0.1  # Should be at least the sleep time

    def test_fingerprint_with_missing_headers(self):
        """Test fingerprint extraction with missing headers."""
        middleware = FingerprintMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        # Request with no headers
        request = factory.get("/api/test/")

        middleware(request)

        # Should still generate fingerprint (even if empty)
        assert hasattr(request, "fingerprint")
        assert isinstance(request.fingerprint, str)

    def test_request_id_uniqueness(self):
        """Test that request IDs are unique when generated."""
        middleware = RequestIDMiddleware(lambda req: JsonResponse({"ok": True}))
        factory = RequestFactory()

        request_ids = set()
        for _ in range(100):
            request = factory.get("/api/test/")
            middleware(request)
            request_ids.add(request.request_id)

        # All request IDs should be unique
        assert len(request_ids) == 100

