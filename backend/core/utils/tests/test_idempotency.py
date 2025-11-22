"""
Comprehensive tests for idempotency and voter token utilities.
"""

import pytest
from core.utils.idempotency import (
    check_duplicate_vote_by_idempotency,
    check_idempotency,
    extract_ip_address,
    generate_idempotency_key,
    generate_voter_token,
    store_idempotency_result,
    validate_idempotency_key,
)
from django.conf import settings
from django.test import RequestFactory


@pytest.mark.unit
class TestIdempotencyKeyGeneration:
    """Test idempotency key generation."""

    def test_same_inputs_generate_same_key(self):
        """Test that same inputs generate the same idempotency key."""
        key1 = generate_idempotency_key(user_id=1, poll_id=2, choice_id=3)
        key2 = generate_idempotency_key(user_id=1, poll_id=2, choice_id=3)

        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex digest length

    def test_different_inputs_generate_different_keys(self):
        """Test that different inputs generate different keys."""
        key1 = generate_idempotency_key(user_id=1, poll_id=2, choice_id=3)
        key2 = generate_idempotency_key(user_id=1, poll_id=2, choice_id=4)
        key3 = generate_idempotency_key(user_id=2, poll_id=2, choice_id=3)
        key4 = generate_idempotency_key(user_id=1, poll_id=3, choice_id=3)

        # All keys should be different
        assert key1 != key2
        assert key1 != key3
        assert key1 != key4
        assert key2 != key3
        assert key2 != key4
        assert key3 != key4

    def test_key_is_deterministic(self):
        """Test that key generation is deterministic."""
        key1 = generate_idempotency_key(user_id=100, poll_id=200, choice_id=300)
        key2 = generate_idempotency_key(user_id=100, poll_id=200, choice_id=300)
        key3 = generate_idempotency_key(user_id=100, poll_id=200, choice_id=300)

        assert key1 == key2 == key3

    def test_key_format(self):
        """Test that generated key has correct format."""
        key = generate_idempotency_key(user_id=1, poll_id=2, choice_id=3)

        # Should be 64-character hex string
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


@pytest.mark.unit
class TestIdempotencyKeyValidation:
    """Test idempotency key validation."""

    def test_valid_key_passes_validation(self):
        """Test that valid idempotency key passes validation."""
        key = generate_idempotency_key(user_id=1, poll_id=2, choice_id=3)
        assert validate_idempotency_key(key) is True

    def test_invalid_key_fails_validation(self):
        """Test that invalid keys fail validation."""
        # Empty string
        assert validate_idempotency_key("") is False

        # Too short
        assert validate_idempotency_key("abc123") is False

        # Too long
        assert validate_idempotency_key("a" * 65) is False

        # Invalid hex characters
        assert validate_idempotency_key("g" * 64) is False
        assert validate_idempotency_key("Z" * 64) is False

    def test_none_key_fails_validation(self):
        """Test that None key fails validation."""
        assert validate_idempotency_key(None) is False


@pytest.mark.unit
class TestIdempotencyCheck:
    """Test idempotency checking."""

    def test_check_idempotency_returns_false_for_new_key(self):
        """Test that new idempotency key returns False."""
        from django.core.cache import cache

        cache.clear()
        key = generate_idempotency_key(user_id=1, poll_id=2, choice_id=3)

        is_duplicate, result = check_idempotency(key)

        assert is_duplicate is False
        assert result is None

    def test_check_idempotency_returns_true_for_cached_key(self):
        """Test that cached idempotency key returns True."""
        from django.conf import settings
        from django.core.cache import cache

        # Skip if cache backend is dummy (doesn't store anything)
        cache_backend = (
            getattr(settings, "CACHES", {}).get("default", {}).get("BACKEND", "")
        )
        if "dummy" in cache_backend.lower():
            pytest.skip(
                "Idempotency cache tests require a functional cache backend (Redis or locmem)"
            )

        cache.clear()
        key = generate_idempotency_key(user_id=1, poll_id=2, choice_id=3)
        cached_result = {"vote_id": 123, "status": "created"}

        store_idempotency_result(key, cached_result)

        # Verify it was stored
        cache_key = f"idempotency:{key}"
        stored_value = cache.get(cache_key)
        assert stored_value is not None, "Cache should store the value"

        is_duplicate, result = check_idempotency(key)

        assert is_duplicate is True
        assert result == cached_result

    def test_duplicate_idempotency_keys_are_detected(self):
        """Test that duplicate idempotency keys are detected."""
        from django.conf import settings
        from django.core.cache import cache

        # Skip if cache backend is dummy (doesn't store anything)
        cache_backend = (
            getattr(settings, "CACHES", {}).get("default", {}).get("BACKEND", "")
        )
        if "dummy" in cache_backend.lower():
            pytest.skip(
                "Idempotency cache tests require a functional cache backend (Redis or locmem)"
            )

        cache.clear()
        key = generate_idempotency_key(user_id=1, poll_id=2, choice_id=3)

        # First check - should not be duplicate
        is_duplicate1, _ = check_idempotency(key)
        assert is_duplicate1 is False

        # Store result
        store_idempotency_result(key, {"vote_id": 123})

        # Verify it was stored
        cache_key = f"idempotency:{key}"
        stored_value = cache.get(cache_key)
        assert stored_value is not None, "Cache should store the value"

        # Second check - should be duplicate
        is_duplicate2, result = check_idempotency(key)
        assert is_duplicate2 is True
        assert result is not None


@pytest.mark.django_db
class TestDuplicateVoteCheck:
    """Test duplicate vote checking by idempotency key."""

    def test_check_duplicate_vote_by_idempotency(self, user):
        """Test checking for duplicate votes using idempotency key."""
        from apps.polls.models import Poll, PollOption
        from apps.votes.models import Vote

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        option = PollOption.objects.create(poll=poll, text="Option 1")

        key = generate_idempotency_key(user.id, poll.id, option.id)

        # First check - should not be duplicate
        is_duplicate1, vote_id1 = check_duplicate_vote_by_idempotency(key)
        assert is_duplicate1 is False
        assert vote_id1 is None

        # Create vote
        vote = Vote.objects.create(
            user=user,
            poll=poll,
            option=option,
            idempotency_key=key,
            voter_token="token1",
        )

        # Second check - should be duplicate
        is_duplicate2, vote_id2 = check_duplicate_vote_by_idempotency(key)
        assert is_duplicate2 is True
        assert vote_id2 == vote.id


@pytest.mark.unit
class TestVoterTokenGeneration:
    """Test voter token generation."""

    def test_voter_token_for_authenticated_user(self):
        """Test voter token generation for authenticated users."""
        token1 = generate_voter_token(user_id=123)
        token2 = generate_voter_token(user_id=123)

        # Same user ID should generate same token
        assert token1 == token2
        assert len(token1) == 64

        # Different user IDs should generate different tokens
        token3 = generate_voter_token(user_id=456)
        assert token1 != token3

    def test_voter_token_for_anonymous_user(self):
        """Test voter token generation for anonymous users."""
        token1 = generate_voter_token(
            user_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            fingerprint="fp123",
        )
        token2 = generate_voter_token(
            user_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            fingerprint="fp123",
        )

        # Same inputs should generate same token
        assert token1 == token2
        assert len(token1) == 64

    def test_voter_token_different_for_different_ips(self):
        """Test that different IPs generate different tokens for anonymous users."""
        token1 = generate_voter_token(
            user_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            fingerprint="fp123",
        )
        token2 = generate_voter_token(
            user_id=None,
            ip_address="192.168.1.2",
            user_agent="Mozilla/5.0",
            fingerprint="fp123",
        )

        assert token1 != token2

    def test_voter_token_different_for_different_user_agents(self):
        """Test that different user agents generate different tokens."""
        token1 = generate_voter_token(
            user_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            fingerprint="fp123",
        )
        token2 = generate_voter_token(
            user_id=None,
            ip_address="192.168.1.1",
            user_agent="Chrome/91.0",
            fingerprint="fp123",
        )

        assert token1 != token2

    def test_voter_token_different_for_different_fingerprints(self):
        """Test that different fingerprints generate different tokens."""
        token1 = generate_voter_token(
            user_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            fingerprint="fp123",
        )
        token2 = generate_voter_token(
            user_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            fingerprint="fp456",
        )

        assert token1 != token2

    def test_voter_token_handles_missing_data(self):
        """Test that voter token generation handles missing data."""
        # Anonymous user with no data
        token1 = generate_voter_token(user_id=None)
        assert len(token1) == 64

        # Anonymous user with partial data
        token2 = generate_voter_token(user_id=None, ip_address="192.168.1.1")
        assert len(token2) == 64
        assert token1 != token2


@pytest.mark.unit
class TestIPExtraction:
    """Test IP address extraction from requests."""

    def test_extract_ip_from_remote_addr(self):
        """Test IP extraction from REMOTE_ADDR."""
        factory = RequestFactory()
        request = factory.get("/api/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        ip = extract_ip_address(request)

        assert ip == "192.168.1.100"

    def test_extract_ip_from_x_forwarded_for(self):
        """Test IP extraction from X-Forwarded-For header."""
        factory = RequestFactory()
        request = factory.get(
            "/api/test/", HTTP_X_FORWARDED_FOR="203.0.113.1, 198.51.100.1"
        )

        ip = extract_ip_address(request)

        # Should return first IP (original client)
        assert ip == "203.0.113.1"

    def test_extract_ip_from_x_real_ip(self):
        """Test IP extraction from X-Real-IP header."""
        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_X_REAL_IP="203.0.113.2")

        ip = extract_ip_address(request)

        assert ip == "203.0.113.2"

    def test_extract_ip_priority_order(self):
        """Test that X-Forwarded-For takes priority over X-Real-IP and REMOTE_ADDR."""
        factory = RequestFactory()
        request = factory.get(
            "/api/test/",
            HTTP_X_FORWARDED_FOR="203.0.113.1",
            HTTP_X_REAL_IP="203.0.113.2",
        )
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        ip = extract_ip_address(request)

        # X-Forwarded-For should take priority
        assert ip == "203.0.113.1"

    def test_extract_ip_x_real_ip_over_remote_addr(self):
        """Test that X-Real-IP takes priority over REMOTE_ADDR."""
        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_X_REAL_IP="203.0.113.2")
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        ip = extract_ip_address(request)

        # X-Real-IP should take priority
        assert ip == "203.0.113.2"

    def test_extract_ip_handles_missing_headers(self):
        """Test IP extraction when headers are missing."""
        factory = RequestFactory()
        request = factory.get("/api/test/")
        # Remove REMOTE_ADDR if it exists (RequestFactory sets it to 127.0.0.1 by default)
        if "REMOTE_ADDR" in request.META:
            del request.META["REMOTE_ADDR"]
        # No IP headers set

        ip = extract_ip_address(request)

        # Should return None if no IP found
        assert ip is None

    def test_extract_ip_handles_empty_x_forwarded_for(self):
        """Test IP extraction with empty X-Forwarded-For."""
        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_X_FORWARDED_FOR="")
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        ip = extract_ip_address(request)

        # Should fallback to REMOTE_ADDR
        assert ip == "192.168.1.100"

    def test_extract_ip_handles_multiple_ips_in_x_forwarded_for(self):
        """Test IP extraction with multiple IPs in X-Forwarded-For."""
        factory = RequestFactory()
        request = factory.get(
            "/api/test/",
            HTTP_X_FORWARDED_FOR="203.0.113.1, 198.51.100.1, 192.0.2.1",
        )

        ip = extract_ip_address(request)

        # Should return first IP
        assert ip == "203.0.113.1"

    def test_extract_ip_handles_whitespace_in_x_forwarded_for(self):
        """Test IP extraction with whitespace in X-Forwarded-For."""
        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_X_FORWARDED_FOR="  203.0.113.1  ")

        ip = extract_ip_address(request)

        # Should strip whitespace
        assert ip == "203.0.113.1"


@pytest.mark.integration
class TestIdempotencyServiceIntegration:
    """Integration tests for idempotency service."""

    @pytest.mark.skipif(
        lambda: settings.CACHES["default"]["BACKEND"]
        == "django.core.cache.backends.dummy.DummyCache",
        reason="Idempotency tests require a functional cache backend (not DummyCache)",
    )
    def test_full_idempotency_flow(self, user):
        """Test complete idempotency flow."""
        from django.conf import settings
        from django.core.cache import cache

        cache.clear()

        # Generate key
        key = generate_idempotency_key(user.id, poll_id=1, choice_id=2)

        # Validate key
        assert validate_idempotency_key(key) is True

        # Check idempotency (should be new)
        is_duplicate1, _ = check_idempotency(key)
        assert is_duplicate1 is False

        # Store result
        store_idempotency_result(key, {"vote_id": 123, "status": "created"})

        # Check idempotency again (should be duplicate)
        is_duplicate2, result = check_idempotency(key)
        assert is_duplicate2 is True
        assert result["vote_id"] == 123

    def test_voter_token_and_idempotency_together(self, user):
        """Test voter token and idempotency key generation together."""
        # Generate voter token for authenticated user
        voter_token = generate_voter_token(user_id=user.id)

        # Generate idempotency key
        idempotency_key = generate_idempotency_key(user.id, poll_id=1, choice_id=2)

        # Both should be valid
        assert len(voter_token) == 64
        assert len(idempotency_key) == 64
        assert validate_idempotency_key(idempotency_key) is True

        # They should be different
        assert voter_token != idempotency_key
