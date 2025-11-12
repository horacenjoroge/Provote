"""
Tests for fingerprint validation utilities.
"""

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone
from freezegun import freeze_time

from core.utils.fingerprint_validation import (
    check_fingerprint_suspicious,
    get_fingerprint_cache_key,
    update_fingerprint_cache,
)


@pytest.mark.unit
class TestFingerprintValidation:
    """Test fingerprint validation functions."""

    def test_get_fingerprint_cache_key(self):
        """Test cache key generation."""
        key = get_fingerprint_cache_key("abc123", 1)
        assert key == "fp:activity:abc123:1"

    def test_check_fingerprint_suspicious_no_fingerprint(self):
        """Test that empty fingerprint returns not suspicious."""
        result = check_fingerprint_suspicious("", 1, 1)
        assert result["suspicious"] is False
        assert result["risk_score"] == 0

    def test_check_fingerprint_suspicious_clean_fingerprint(self, db):
        """Test clean fingerprint passes validation."""
        cache.clear()
        result = check_fingerprint_suspicious("clean_fp_123", 1, 1)
        assert result["suspicious"] is False
        assert result["risk_score"] == 0
        assert result["block_vote"] is False

    def test_update_fingerprint_cache(self):
        """Test updating fingerprint cache."""
        cache.clear()
        update_fingerprint_cache("test_fp", 1, 1, "192.168.1.1")

        cache_key = get_fingerprint_cache_key("test_fp", 1)
        cached_data = cache.get(cache_key)

        assert cached_data is not None
        assert cached_data["count"] == 1
        assert cached_data["user_count"] == 1
        assert 1 in cached_data["users"]

    def test_update_fingerprint_cache_increments_count(self):
        """Test that cache increments count on multiple updates."""
        cache.clear()
        update_fingerprint_cache("test_fp", 1, 1, "192.168.1.1")
        update_fingerprint_cache("test_fp", 1, 1, "192.168.1.1")

        cache_key = get_fingerprint_cache_key("test_fp", 1)
        cached_data = cache.get(cache_key)

        assert cached_data["count"] == 2

    def test_update_fingerprint_cache_tracks_multiple_users(self):
        """Test that cache tracks multiple users."""
        cache.clear()
        update_fingerprint_cache("test_fp", 1, 1, "192.168.1.1")
        update_fingerprint_cache("test_fp", 1, 2, "192.168.1.2")

        cache_key = get_fingerprint_cache_key("test_fp", 1)
        cached_data = cache.get(cache_key)

        assert cached_data["user_count"] == 2
        assert set(cached_data["users"]) == {1, 2}

    def test_update_fingerprint_cache_tracks_multiple_ips(self):
        """Test that cache tracks multiple IPs."""
        cache.clear()
        update_fingerprint_cache("test_fp", 1, 1, "192.168.1.1")
        update_fingerprint_cache("test_fp", 1, 1, "192.168.1.2")

        cache_key = get_fingerprint_cache_key("test_fp", 1)
        cached_data = cache.get(cache_key)

        assert cached_data["ip_count"] == 2
        assert "192.168.1.1" in cached_data["ips"]
        assert "192.168.1.2" in cached_data["ips"]


@pytest.mark.django_db
class TestFingerprintSuspiciousDetection:
    """Test suspicious pattern detection."""

    def test_detect_different_users_from_cache(self, user):
        """Test detection of same fingerprint from different users via cache."""
        from apps.polls.models import Poll, PollOption
        from apps.votes.models import Vote

        cache.clear()

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        option = PollOption.objects.create(poll=poll, text="Option 1")

        user2 = type(user).objects.create_user(username="user2", password="pass")

        # Create votes with same fingerprint, different users
        Vote.objects.create(
            user=user,
            poll=poll,
            option=option,
            fingerprint="suspicious_fp",
            ip_address="192.168.1.1",
            voter_token="token1",
            idempotency_key="key1",
        )

        # Update cache
        update_fingerprint_cache("suspicious_fp", poll.id, user.id, "192.168.1.1")

        # Check with different user
        result = check_fingerprint_suspicious(
            "suspicious_fp", poll.id, user2.id, "192.168.1.2"
        )

        assert result["suspicious"] is True
        assert result["block_vote"] is True
        assert "different users" in " ".join(result["reasons"]).lower()

    def test_detect_rapid_votes_from_database(self, user):
        """Test detection of rapid votes from database query."""
        from apps.polls.models import Poll, PollOption
        from apps.votes.models import Vote

        cache.clear()

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        option = PollOption.objects.create(poll=poll, text="Option 1")

        # Create rapid votes
        with freeze_time("2024-01-01 10:00:00"):
            Vote.objects.create(
                user=user,
                poll=poll,
                option=option,
                fingerprint="rapid_fp",
                ip_address="192.168.1.1",
                voter_token="token1",
                idempotency_key="key1",
            )

        with freeze_time("2024-01-01 10:02:00"):
            Vote.objects.create(
                user=user,
                poll=poll,
                option=option,
                fingerprint="rapid_fp",
                ip_address="192.168.1.1",
                voter_token="token2",
                idempotency_key="key2",
            )

        with freeze_time("2024-01-01 10:04:00"):
            Vote.objects.create(
                user=user,
                poll=poll,
                option=option,
                fingerprint="rapid_fp",
                ip_address="192.168.1.1",
                voter_token="token3",
                idempotency_key="key3",
            )

        # Check fingerprint (should detect rapid votes)
        result = check_fingerprint_suspicious(
            "rapid_fp", poll.id, user.id, "192.168.1.1"
        )

        # Should detect rapid votes pattern
        assert result["suspicious"] is True
        assert any("rapid" in reason.lower() for reason in result["reasons"])

    def test_detect_different_ips_from_database(self, user):
        """Test detection of same fingerprint from different IPs."""
        from apps.polls.models import Poll, PollOption
        from apps.votes.models import Vote

        cache.clear()

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        option = PollOption.objects.create(poll=poll, text="Option 1")

        # Create votes with same fingerprint, different IPs
        Vote.objects.create(
            user=user,
            poll=poll,
            option=option,
            fingerprint="multi_ip_fp",
            ip_address="192.168.1.1",
            voter_token="token1",
            idempotency_key="key1",
        )

        Vote.objects.create(
            user=user,
            poll=poll,
            option=option,
            fingerprint="multi_ip_fp",
            ip_address="192.168.1.2",
            voter_token="token2",
            idempotency_key="key2",
        )

        # Check fingerprint
        result = check_fingerprint_suspicious(
            "multi_ip_fp", poll.id, user.id, "192.168.1.3"
        )

        assert result["suspicious"] is True
        assert any("different ip" in reason.lower() for reason in result["reasons"])

    def test_time_windowed_query_efficiency(self, user):
        """Test that only recent votes are queried."""
        from apps.polls.models import Poll, PollOption
        from apps.votes.models import Vote
        from datetime import timedelta

        cache.clear()

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        option = PollOption.objects.create(poll=poll, text="Option 1")

        # Create old vote (outside time window)
        old_time = timezone.now() - timedelta(days=2)
        Vote.objects.create(
            user=user,
            poll=poll,
            option=option,
            fingerprint="old_fp",
            ip_address="192.168.1.1",
            voter_token="token1",
            idempotency_key="key1",
            created_at=old_time,
        )

        # Create recent vote
        Vote.objects.create(
            user=user,
            poll=poll,
            option=option,
            fingerprint="recent_fp",
            ip_address="192.168.1.1",
            voter_token="token2",
            idempotency_key="key2",
        )

        # Check - should only query recent votes
        result = check_fingerprint_suspicious("recent_fp", poll.id, user.id, "192.168.1.1")

        # Should not be suspicious (only 1 recent vote)
        assert result["suspicious"] is False


@pytest.mark.django_db
class TestFingerprintValidationIntegration:
    """Integration tests for fingerprint validation."""

    def test_redis_cache_hit_performance(self, user):
        """Test that Redis cache provides fast lookups."""
        from apps.polls.models import Poll, PollOption

        cache.clear()

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        option = PollOption.objects.create(poll=poll, text="Option 1")

        # First check - cache miss, should query database
        result1 = check_fingerprint_suspicious("perf_fp", poll.id, user.id, "192.168.1.1")
        assert result1["suspicious"] is False

        # Update cache
        update_fingerprint_cache("perf_fp", poll.id, user.id, "192.168.1.1")

        # Second check - cache hit, should be fast
        result2 = check_fingerprint_suspicious("perf_fp", poll.id, user.id, "192.168.1.1")
        assert result2["suspicious"] is False

        # Verify cache was used (no database query needed)
        cache_key = get_fingerprint_cache_key("perf_fp", poll.id)
        cached_data = cache.get(cache_key)
        assert cached_data is not None
        assert cached_data["count"] >= 1

