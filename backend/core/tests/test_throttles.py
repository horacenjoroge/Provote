"""
Tests for advanced rate limiting throttles.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from django.contrib.auth.models import AnonymousUser

from rest_framework.exceptions import Throttled
from rest_framework.test import APIRequestFactory

from core.throttles import (
    AdvancedRateThrottle,
    VoteCastRateThrottle,
    PollCreateRateThrottle,
    PollReadRateThrottle,
)


@pytest.fixture
def request_factory():
    """Request factory for testing."""
    return APIRequestFactory()


class TestAdvancedRateThrottle:
    """Tests for AdvancedRateThrottle."""

    def test_get_ip_address(self, request_factory):
        """Test IP address extraction."""
        throttle = AdvancedRateThrottle()
        request = request_factory.get("/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        
        ip = throttle.get_ip_address(request)
        assert ip == "192.168.1.1"

    def test_get_ip_address_x_forwarded_for(self, request_factory):
        """Test IP extraction from X-Forwarded-For header."""
        throttle = AdvancedRateThrottle()
        request = request_factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 192.168.1.1"
        
        ip = throttle.get_ip_address(request)
        assert ip == "10.0.0.1"

    def test_get_ident_anonymous(self, request_factory):
        """Test identifier for anonymous user."""
        throttle = AdvancedRateThrottle()
        request = request_factory.get("/")
        request.user = AnonymousUser()
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        
        ident = throttle.get_ident(request)
        assert ident.startswith("ip:")

    def test_get_ident_authenticated(self, request_factory):
        """Test identifier for authenticated user."""
        throttle = AdvancedRateThrottle()
        request = request_factory.get("/")
        user = Mock()
        user.id = 123
        user.is_authenticated = True
        request.user = user
        
        ident = throttle.get_ident(request)
        assert ident == "user:123"

    def test_get_rate_limit_anonymous(self, request_factory):
        """Test rate limit for anonymous user."""
        throttle = AdvancedRateThrottle()
        throttle.rate_limit_anon = 10
        throttle.rate_limit_user = 100
        
        request = request_factory.get("/")
        request.user = AnonymousUser()
        
        limit = throttle.get_rate_limit(request)
        assert limit == 10

    def test_get_rate_limit_authenticated(self, request_factory):
        """Test rate limit for authenticated user."""
        throttle = AdvancedRateThrottle()
        throttle.rate_limit_anon = 10
        throttle.rate_limit_user = 100
        
        request = request_factory.get("/")
        user = Mock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        request.user = user
        
        limit = throttle.get_rate_limit(request)
        assert limit == 100

    def test_get_rate_limit_admin(self, request_factory):
        """Test rate limit bypass for admin."""
        throttle = AdvancedRateThrottle()
        throttle.rate_limit_anon = 10
        throttle.rate_limit_user = 100
        
        request = request_factory.get("/")
        user = Mock()
        user.is_authenticated = True
        user.is_staff = True
        user.is_superuser = False
        request.user = user
        
        limit = throttle.get_rate_limit(request)
        assert limit is None  # No limit for admin

    @patch("core.throttles.get_rate_limiter")
    def test_allow_request_within_limit(self, mock_get_limiter, request_factory):
        """Test allowing request within rate limit."""
        mock_limiter = MagicMock()
        mock_get_limiter.return_value = mock_limiter
        mock_limiter.check_rate_limit.return_value = (True, {
            "remaining": 5,
            "reset": int(time.time()) + 60,
            "limit": 10,
        })
        
        throttle = AdvancedRateThrottle()
        throttle.rate_limit_anon = 10
        throttle.window_seconds = 60
        
        request = request_factory.get("/")
        request.user = AnonymousUser()
        
        result = throttle.allow_request(request, None)
        assert result is True
        assert hasattr(request, "rate_limit_info")

    @patch("core.throttles.get_rate_limiter")
    def test_allow_request_exceeds_limit(self, mock_get_limiter, request_factory):
        """Test blocking request that exceeds rate limit."""
        mock_limiter = MagicMock()
        mock_get_limiter.return_value = mock_limiter
        mock_limiter.check_rate_limit.return_value = (False, {
            "remaining": 0,
            "reset": int(time.time()) + 30,
            "limit": 10,
        })
        
        throttle = AdvancedRateThrottle()
        throttle.rate_limit_anon = 10
        throttle.window_seconds = 60
        
        request = request_factory.get("/")
        request.user = AnonymousUser()
        
        with pytest.raises(Throttled) as exc_info:
            throttle.allow_request(request, None)
        
        assert exc_info.value.detail["limit"] == 10
        assert "retry_after" in exc_info.value.detail


class TestVoteCastRateThrottle:
    """Tests for VoteCastRateThrottle."""

    def test_vote_cast_throttle_config(self):
        """Test vote cast throttle configuration."""
        throttle = VoteCastRateThrottle()
        assert throttle.scope == "vote_cast"
        assert throttle.rate_limit_anon == 10
        assert throttle.rate_limit_user == 100
        assert throttle.window_seconds == 60


class TestPollCreateRateThrottle:
    """Tests for PollCreateRateThrottle."""

    def test_poll_create_throttle_config(self):
        """Test poll create throttle configuration."""
        throttle = PollCreateRateThrottle()
        assert throttle.scope == "poll_create"
        assert throttle.rate_limit_user == 20
        assert throttle.window_seconds == 60


class TestPollReadRateThrottle:
    """Tests for PollReadRateThrottle."""

    def test_poll_read_throttle_config(self):
        """Test poll read throttle configuration."""
        throttle = PollReadRateThrottle()
        assert throttle.scope == "poll_read"
        assert throttle.rate_limit_anon == 100
        assert throttle.rate_limit_user == 1000
        assert throttle.window_seconds == 60

