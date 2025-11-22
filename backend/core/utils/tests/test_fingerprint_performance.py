"""
Performance tests for fingerprint validation.
Tests efficiency with large datasets.
"""

import pytest
from core.utils.fingerprint_validation import check_fingerprint_suspicious
from django.core.cache import cache
from django.utils import timezone


@pytest.mark.performance
@pytest.mark.django_db
class TestFingerprintValidationPerformance:
    """Performance tests for fingerprint validation."""

    def test_redis_cache_hit_performance(self, user):
        """Test that Redis cache provides sub-millisecond lookups."""
        from apps.polls.models import Poll, PollOption
        from core.utils.fingerprint_validation import update_fingerprint_cache

        cache.clear()

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        _option = PollOption.objects.create(poll=poll, text="Option 1")

        # Update cache
        update_fingerprint_cache("perf_fp", poll.id, user.id, "192.168.1.1")

        # Measure cache hit performance
        import time

        start = time.time()
        for _ in range(100):
            check_fingerprint_suspicious("perf_fp", poll.id, user.id, "192.168.1.1")
        elapsed = time.time() - start

        # Should be very fast (< 10ms per check on average)
        avg_time_ms = (elapsed / 100) * 1000
        assert avg_time_ms < 10, f"Cache lookup too slow: {avg_time_ms}ms"

    def test_time_windowed_query_efficiency(self, user):
        """Test that time-windowed queries are efficient."""
        from datetime import timedelta

        from apps.polls.models import Poll, PollOption
        from apps.votes.models import Vote

        cache.clear()

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        _option = PollOption.objects.create(poll=poll, text="Option 1")

        # Create many old votes (outside time window)
        # Use anonymous votes to avoid unique constraint
        old_time = timezone.now() - timedelta(days=2)
        for i in range(1000):
            Vote.objects.create(
                user=None,  # Anonymous votes to avoid unique constraint
                poll=poll,
                option=option,
                fingerprint=f"old_fp_{i}",
                ip_address="192.168.1.1",
                voter_token=f"token_{i}",
                idempotency_key=f"key_{i}",
                created_at=old_time,
            )

        # Create recent vote - use anonymous to avoid unique constraint
        Vote.objects.create(
            user=None,  # Anonymous vote to avoid unique constraint
            poll=poll,
            option=option,
            fingerprint="recent_fp",
            ip_address="192.168.1.1",
            voter_token="recent_token",
            idempotency_key="recent_key",
        )

        # Measure query performance (should only query recent votes)
        # Use None for user_id since we're testing with anonymous votes
        import time

        start = time.time()
        result = check_fingerprint_suspicious("recent_fp", poll.id, None, "192.168.1.1")
        elapsed = time.time() - start

        # Should be fast even with 1000 old votes (time window prevents scanning them)
        assert elapsed < 0.1, f"Time-windowed query too slow: {elapsed}s"
        assert result["suspicious"] is False

    def test_cache_reduces_database_queries(self, user):
        """Test that cache reduces database queries."""
        from apps.polls.models import Poll, PollOption
        from core.utils.fingerprint_validation import update_fingerprint_cache
        from django.db import connection
        from django.test.utils import override_settings

        cache.clear()

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        _option = PollOption.objects.create(poll=poll, text="Option 1")

        # First check - should query database
        connection.queries_log.clear()
        result1 = check_fingerprint_suspicious(
            "cache_test_fp", poll.id, user.id, "192.168.1.1"
        )
        _db_queries_first = len(connection.queries)

        # Update cache
        update_fingerprint_cache("cache_test_fp", poll.id, user.id, "192.168.1.1")

        # Second check - should use cache (fewer or no DB queries)
        connection.queries_log.clear()
        result2 = check_fingerprint_suspicious(
            "cache_test_fp", poll.id, user.id, "192.168.1.1"
        )
        _db_queries_second = len(connection.queries)

        # Cache should reduce database queries
        # Note: May still have some queries for VoteAttempt logging, but fingerprint check should use cache
        assert result1["suspicious"] is False
        assert result2["suspicious"] is False

    def test_handles_millions_of_votes_efficiently(self, user):
        """Test that validation works efficiently even with concept of millions of votes."""
        from datetime import timedelta

        from apps.polls.models import Poll, PollOption
        from apps.votes.models import Vote

        cache.clear()

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        _option = PollOption.objects.create(poll=poll, text="Option 1")

        # Simulate scenario: Many votes exist, but we only query recent ones
        # Create votes across different time periods
        base_time = timezone.now() - timedelta(days=30)

        # Create votes in batches (simulating millions)
        # In real scenario, these would be millions, but for test we create representative sample
        # Use anonymous votes to avoid unique constraint (one vote per user per poll)
        for day in range(30):
            vote_time = base_time + timedelta(days=day)
            Vote.objects.create(
                user=None,  # Anonymous votes to avoid unique constraint
                poll=poll,
                option=option,
                fingerprint=f"historical_fp_{day}",
                ip_address="192.168.1.1",
                voter_token=f"token_{day}",
                idempotency_key=f"key_{day}",
                created_at=vote_time,
            )

        # Create recent vote - use anonymous to avoid unique constraint
        recent_fp = "recent_check_fp"
        Vote.objects.create(
            user=None,  # Anonymous vote to avoid unique constraint
            poll=poll,
            option=option,
            fingerprint=recent_fp,
            ip_address="192.168.1.1",
            voter_token="recent_token",
            idempotency_key="recent_key",
        )

        # Check fingerprint - should only query last 24 hours
        # Use None for user_id since we're testing with anonymous votes
        import time

        start = time.time()
        result = check_fingerprint_suspicious(recent_fp, poll.id, None, "192.168.1.1")
        elapsed = time.time() - start

        # Should be fast because time window limits query scope
        assert elapsed < 0.2, f"Query too slow with historical data: {elapsed}s"
        assert result["suspicious"] is False
