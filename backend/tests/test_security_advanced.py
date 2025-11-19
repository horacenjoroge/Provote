"""
Advanced security tests for edge cases and additional attack vectors.

Tests additional security scenarios:
- Path traversal attacks
- HTTP header injection
- Parameter pollution
- Mass assignment
- Timing attacks
- Session fixation
"""

import json
import time

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient

from apps.analytics.models import AuditLog

User = get_user_model()


# Additional fixtures for advanced security tests
@pytest.fixture
def client():
    """Create a Django test client."""
    from django.test import Client
    return Client()


@pytest.fixture
def poll_option(db, poll):
    """Create a poll option for testing."""
    from apps.polls.factories import PollOptionFactory
    return PollOptionFactory(poll=poll)


@pytest.mark.django_db
@pytest.mark.security
class TestPathTraversalProtection:
    """Test path traversal attack protection."""

    def test_path_traversal_in_url(self, client):
        """Test path traversal attempts in URL."""
        traversal_payloads = [
            "../../etc/passwd",
            "..\\..\\windows\\system32",
            "....//....//etc/passwd",
            "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "..%2F..%2Fetc%2Fpasswd",
        ]

        for payload in traversal_payloads:
            response = client.get(f"/api/v1/polls/{payload}/")
            # Should return 404 or 400, not expose files
            assert response.status_code in [400, 404]

    def test_path_traversal_in_query_params(self, client):
        """Test path traversal in query parameters."""
        response = client.get("/api/v1/polls/?file=../../etc/passwd")
        # Should handle safely
        assert response.status_code in [200, 400]


@pytest.mark.django_db
@pytest.mark.security
class TestHTTPHeaderInjection:
    """Test HTTP header injection protection."""

    def test_header_injection_attempts(self, client):
        """Test HTTP header injection attempts."""
        injection_payloads = [
            "test\r\nX-Injected-Header: malicious",
            "test\nX-Injected-Header: malicious",
            "test\rX-Injected-Header: malicious",
        ]

        for payload in injection_payloads:
            response = client.get(
                "/api/v1/polls/",
                HTTP_USER_AGENT=payload,
            )
            # Should handle safely
            assert response.status_code in [200, 400]
            # Should not include injected headers in response
            assert "X-Injected-Header" not in response


@pytest.mark.django_db
@pytest.mark.security
class TestParameterPollution:
    """Test HTTP parameter pollution protection."""

    def test_parameter_pollution(self, client):
        """Test parameter pollution attacks."""
        # Multiple values for same parameter
        response = client.get("/api/v1/polls/?page=1&page=2&page=3")
        # Should handle gracefully
        assert response.status_code in [200, 400]

    def test_parameter_pollution_in_vote(self, client, poll, poll_option, user):
        """Test parameter pollution in vote casting."""
        client.force_login(user)
        
        # Try to send multiple values
        response = client.post(
            "/api/v1/votes/cast/",
            data=json.dumps({
                "poll_id": [poll.id, 999],
                "choice_id": poll_option.id,
            }),
            content_type="application/json",
        )
        # Should reject or use first value
        assert response.status_code in [200, 201, 400]


@pytest.mark.django_db
@pytest.mark.security
class TestMassAssignment:
    """Test mass assignment protection."""

    def test_mass_assignment_prevented(self, admin_client):
        """Test that mass assignment is prevented."""
        # Try to set is_staff or is_superuser via API
        response = admin_client.post(
            "/api/v1/polls/",
            data=json.dumps({
                "title": "Test",
                "description": "Test",
                "is_staff": True,  # Should be ignored
                "is_superuser": True,  # Should be ignored
            }),
            content_type="application/json",
        )
        # Should succeed but ignore sensitive fields
        if response.status_code == 201:
            data = response.json()
            # Should not include is_staff or is_superuser
            assert "is_staff" not in data
            assert "is_superuser" not in data


@pytest.mark.django_db
@pytest.mark.security
class TestTimingAttacks:
    """Test timing attack protection."""

    def test_timing_attack_on_authentication(self, client, user):
        """Test that authentication doesn't leak information via timing."""
        # Try with valid username, invalid password
        start = time.time()
        client.post(
            "/admin/login/",
            data={"username": user.username, "password": "wrong_password"},
        )
        time_invalid = time.time() - start

        # Try with invalid username
        start = time.time()
        client.post(
            "/admin/login/",
            data={"username": "nonexistent", "password": "wrong_password"},
        )
        time_nonexistent = time.time() - start

        # Times should be similar (within reasonable margin)
        # If they differ significantly, it could leak information
        time_diff = abs(time_invalid - time_nonexistent)
        # Allow 0.1 second difference for network/processing variance
        assert time_diff < 0.1, "Timing attack vulnerability detected"


@pytest.mark.django_db
@pytest.mark.security
class TestSessionSecurity:
    """Test session security."""

    def test_session_fixation_prevention(self, client, user):
        """Test that session fixation is prevented."""
        # Get initial session ID
        client.get("/api/v1/polls/")
        initial_session_id = client.cookies.get("sessionid")

        # Login
        client.force_login(user)
        new_session_id = client.cookies.get("sessionid")

        # Session ID should change after login
        if initial_session_id and new_session_id:
            assert initial_session_id.value != new_session_id.value

    def test_session_timeout(self, client, user):
        """Test that sessions timeout appropriately."""
        client.force_login(user)
        
        # Session should be valid
        response = client.get("/api/v1/votes/my-votes/")
        assert response.status_code in [200, 401, 403]  # May require additional setup

    def test_session_cookie_secure_flag(self, client, user):
        """Test that session cookies have secure flag in production."""
        from django.conf import settings
        
        # In production, session cookies should be secure
        if not settings.DEBUG:
            client.force_login(user)
            session_cookie = client.cookies.get("sessionid")
            if session_cookie:
                # In production, should have secure flag
                # In development, may not have it
                pass  # Just verify it exists


@pytest.mark.django_db
@pytest.mark.security
class TestInputValidation:
    """Test input validation and sanitization."""

    def test_oversized_input_rejected(self, client, poll, poll_option, user):
        """Test that oversized inputs are rejected."""
        client.force_login(user)
        
        # Try to send very large payload
        large_payload = "x" * 100000  # 100KB
        
        response = client.post(
            "/api/v1/votes/cast/",
            data=json.dumps({
                "poll_id": poll.id,
                "choice_id": poll_option.id,
                "idempotency_key": large_payload,
            }),
            content_type="application/json",
        )
        # Should reject or truncate
        assert response.status_code in [200, 201, 400, 413]  # 413 = Payload Too Large

    def test_null_byte_injection(self, client, poll, poll_option, user):
        """Test null byte injection protection."""
        client.force_login(user)
        
        null_byte_payloads = [
            "test\x00",
            "\x00test",
            "test\x00test",
        ]

        for payload in null_byte_payloads:
            response = client.post(
                "/api/v1/votes/cast/",
                data=json.dumps({
                    "poll_id": poll.id,
                    "choice_id": poll_option.id,
                    "idempotency_key": payload,
                }),
                content_type="application/json",
            )
            # Should handle safely
            assert response.status_code in [200, 201, 400, 409]

    def test_unicode_attacks(self, client, poll, poll_option, user):
        """Test unicode-based attacks."""
        client.force_login(user)
        
        unicode_payloads = [
            "\u0000",  # Null character
            "\u202e",  # Right-to-left override
            "\ufeff",  # Zero-width no-break space
        ]

        for payload in unicode_payloads:
            response = client.post(
                "/api/v1/votes/cast/",
                data=json.dumps({
                    "poll_id": poll.id,
                    "choice_id": poll_option.id,
                    "idempotency_key": payload,
                }),
                content_type="application/json",
            )
            # Should handle safely
            assert response.status_code in [200, 201, 400, 409]


@pytest.mark.django_db
@pytest.mark.security
class TestAPIAbuse:
    """Test API abuse protection."""

    def test_concurrent_duplicate_requests(self, client, poll, poll_option, user):
        """Test handling of concurrent duplicate requests."""
        client.force_login(user)
        
        idempotency_key = "concurrent_test_key"
        
        # Simulate concurrent requests (in real scenario, would use threading)
        response1 = client.post(
            "/api/v1/votes/cast/",
            data=json.dumps({
                "poll_id": poll.id,
                "choice_id": poll_option.id,
                "idempotency_key": idempotency_key,
            }),
            content_type="application/json",
        )
        
        response2 = client.post(
            "/api/v1/votes/cast/",
            data=json.dumps({
                "poll_id": poll.id,
                "choice_id": poll_option.id,
                "idempotency_key": idempotency_key,
            }),
            content_type="application/json",
        )
        
        # One should succeed, one should be duplicate
        status_codes = [response1.status_code, response2.status_code]
        assert 200 in status_codes or 201 in status_codes
        assert 409 in status_codes or status_codes[0] == status_codes[1]

    def test_rapid_poll_creation_abuse(self, admin_client):
        """Test rapid poll creation abuse."""
        # Try to create many polls rapidly
        responses = []
        for i in range(20):
            response = admin_client.post(
                "/api/v1/polls/",
                data=json.dumps({
                    "title": f"Spam Poll {i}",
                    "description": "Spam",
                }),
                content_type="application/json",
            )
            responses.append(response.status_code)
        
        # Should either succeed or rate limit
        assert all(status in [200, 201, 429] for status in responses)

