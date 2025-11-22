"""
Comprehensive tests for poll analytics service.
"""

from datetime import timedelta

import pytest
from core.services.poll_analytics import (
    get_analytics_summary,
    get_average_time_to_vote,
    get_comprehensive_analytics,
    get_drop_off_rate,
    get_participation_rate,
    get_total_votes_over_time,
    get_vote_distribution,
    get_voter_demographics,
    get_votes_by_day,
    get_votes_by_hour,
)
from django.utils import timezone
from freezegun import freeze_time


@pytest.mark.django_db
class TestTotalVotesOverTime:
    """Test time series vote data."""

    def test_get_total_votes_over_time_hourly(self, poll, choices):
        """Test hourly time series data."""
        import uuid
        from datetime import datetime
        from datetime import timezone as dt_timezone

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        # Set poll start date before votes are created
        poll.starts_at = datetime(2024, 1, 1, 0, 0, 0, tzinfo=dt_timezone.utc)
        poll.save()

        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass"
        )

        # Create votes at different hours
        with freeze_time("2024-01-01 10:00:00"):
            Vote.objects.create(
                user=user,
                poll=poll,
                option=choices[0],
                ip_address="192.168.1.1",
                voter_token="token1",
                idempotency_key="key1",
            )

        # Create second user for second vote (same user can only vote once per poll)
        user2 = User.objects.create_user(
            username=f"testuser2_{uuid.uuid4().hex[:8]}", password="pass"
        )
        with freeze_time("2024-01-01 11:00:00"):
            Vote.objects.create(
                user=user2,
                poll=poll,
                option=choices[1],
                ip_address="192.168.1.2",
                voter_token="token2",
                idempotency_key="key2",
            )

        time_series = get_total_votes_over_time(poll.id, interval="hour")

        assert len(time_series) == 2
        assert all("timestamp" in item and "count" in item for item in time_series)
        assert sum(item["count"] for item in time_series) == 2

    def test_get_total_votes_over_time_daily(self, poll, choices):
        """Test daily time series data."""
        import uuid
        from datetime import datetime
        from datetime import timezone as dt_timezone

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        # Set poll start date before votes are created
        poll.starts_at = datetime(2024, 1, 1, 0, 0, 0, tzinfo=dt_timezone.utc)
        poll.save()

        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass"
        )

        # Create votes on different days
        with freeze_time("2024-01-01 10:00:00"):
            Vote.objects.create(
                user=user,
                poll=poll,
                option=choices[0],
                ip_address="192.168.1.1",
                voter_token="token1",
                idempotency_key="key1",
            )

        # Use anonymous vote for second vote (same user can only vote once per poll)
        with freeze_time("2024-01-02 10:00:00"):
            Vote.objects.create(
                user=None,
                poll=poll,
                option=choices[1],
                ip_address="192.168.1.2",
                voter_token="token2",
                idempotency_key="key2",
            )

        time_series = get_total_votes_over_time(poll.id, interval="day")

        assert len(time_series) == 2
        assert sum(item["count"] for item in time_series) == 2

    def test_empty_poll_time_series(self, poll):
        """Test time series for poll with no votes."""
        time_series = get_total_votes_over_time(poll.id)

        assert time_series == []


@pytest.mark.django_db
class TestVotesByHour:
    """Test votes by hour analytics."""

    def test_get_votes_by_hour(self, poll, choices):
        """Test hourly vote distribution."""
        import uuid

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass"
        )

        # Create votes at different hours
        with freeze_time("2024-01-01 10:00:00"):
            Vote.objects.create(
                user=user,
                poll=poll,
                option=choices[0],
                ip_address="192.168.1.1",
                voter_token="token1",
                idempotency_key="key1",
            )

        # Create second user for second vote (same user can only vote once per poll)
        user2 = User.objects.create_user(
            username=f"testuser2_{uuid.uuid4().hex[:8]}", password="pass"
        )
        with freeze_time("2024-01-01 11:00:00"):
            Vote.objects.create(
                user=user2,
                poll=poll,
                option=choices[1],
                ip_address="192.168.1.2",
                voter_token="token2",
                idempotency_key="key2",
            )

        from datetime import timezone as dt_timezone

        hourly_data = get_votes_by_hour(
            poll.id, date=timezone.datetime(2024, 1, 1, tzinfo=dt_timezone.utc)
        )

        assert len(hourly_data) == 2
        assert all("hour" in item and "count" in item for item in hourly_data)
        hours = [item["hour"] for item in hourly_data]
        assert 10 in hours
        assert 11 in hours


@pytest.mark.django_db
class TestVotesByDay:
    """Test votes by day analytics."""

    def test_get_votes_by_day(self, poll, choices):
        """Test daily vote distribution."""
        import uuid
        from datetime import datetime
        from datetime import timezone as dt_timezone

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass"
        )

        # Create votes on different days
        with freeze_time("2024-01-01 10:00:00"):
            Vote.objects.create(
                user=user,
                poll=poll,
                option=choices[0],
                ip_address="192.168.1.1",
                voter_token="token1",
                idempotency_key="key1",
            )

        # Use anonymous vote for second vote (same user can only vote once per poll)
        with freeze_time("2024-01-02 10:00:00"):
            Vote.objects.create(
                user=None,
                poll=poll,
                option=choices[1],
                ip_address="192.168.1.2",
                voter_token="token2",
                idempotency_key="key2",
            )

        # get_votes_by_day uses timezone.now() which isn't frozen, so we need to freeze time
        # when calling the function to ensure it sees our votes
        with freeze_time("2024-01-02 12:00:00"):
            daily_data = get_votes_by_day(poll.id, days=30)

        assert len(daily_data) == 2
        assert all("date" in item and "count" in item for item in daily_data)
        assert sum(item["count"] for item in daily_data) == 2


@pytest.mark.django_db
class TestVoterDemographics:
    """Test voter demographics analytics."""

    def test_get_voter_demographics(self, poll, choices):
        """Test demographics calculation."""
        # Create authenticated and anonymous votes
        import time

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        timestamp = int(time.time() * 1000000)
        user1 = User.objects.create_user(username=f"user1_{timestamp}", password="pass")
        user2 = User.objects.create_user(username=f"user2_{timestamp}", password="pass")

        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            voter_token="token1",
            idempotency_key="key1",
        )

        Vote.objects.create(
            user=user2,
            poll=poll,
            option=choices[1],
            ip_address="192.168.1.2",
            user_agent="Mozilla/5.0",
            voter_token="token2",
            idempotency_key="key2",
        )

        demographics = get_voter_demographics(poll.id)

        assert demographics["authenticated_voters"] == 2
        assert demographics["unique_ip_addresses"] == 2
        assert "top_user_agents" in demographics


@pytest.mark.django_db
class TestParticipationRate:
    """Test participation rate calculation."""

    def test_get_participation_rate(self, poll, choices):
        """Test participation rate calculation."""
        import uuid

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass"
        )

        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            ip_address="192.168.1.1",
            voter_token="token1",
            idempotency_key="key1",
        )

        # Update cached totals since we created vote directly
        poll.update_cached_totals()
        poll.refresh_from_db()

        participation = get_participation_rate(poll.id)

        assert participation["unique_voters"] == 1
        assert participation["total_votes"] >= 1


@pytest.mark.django_db
class TestAverageTimeToVote:
    """Test average time to vote calculation."""

    def test_get_average_time_to_vote(self, poll, choices):
        """Test average time to vote calculation."""
        import uuid

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass"
        )

        # Create vote 1 hour after poll start
        vote_time = poll.starts_at + timedelta(hours=1)
        with freeze_time(vote_time):
            Vote.objects.create(
                user=user,
                poll=poll,
                option=choices[0],
                ip_address="192.168.1.1",
                voter_token="token1",
                idempotency_key="key1",
            )

        avg_time = get_average_time_to_vote(poll.id)

        assert avg_time is not None
        assert avg_time >= 3600  # At least 1 hour in seconds

    def test_empty_poll_average_time(self, poll):
        """Test average time for poll with no votes."""
        avg_time = get_average_time_to_vote(poll.id)

        assert avg_time is None


@pytest.mark.django_db
class TestDropOffRate:
    """Test drop-off rate calculation."""

    def test_get_drop_off_rate(self, poll, choices):
        """Test drop-off rate calculation."""
        import uuid

        from apps.votes.models import Vote, VoteAttempt
        from django.contrib.auth.models import User

        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass"
        )

        # Create successful vote
        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            ip_address="192.168.1.1",
            voter_token="token1",
            idempotency_key="key1",
        )

        # Create failed attempt
        VoteAttempt.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            success=False,
            error_message="Test error",
            voter_token="token2",
            idempotency_key="key2",
        )

        drop_off = get_drop_off_rate(poll.id)

        assert "drop_off_rate" in drop_off
        assert drop_off["total_attempts"] >= 1
        assert drop_off["successful_votes"] >= 1


@pytest.mark.django_db
class TestVoteDistribution:
    """Test vote distribution across options."""

    def test_get_vote_distribution(self, poll, choices):
        """Test vote distribution calculation."""
        import time

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        timestamp = int(time.time() * 1000000)
        user1 = User.objects.create_user(username=f"user1_{timestamp}", password="pass")
        user2 = User.objects.create_user(username=f"user2_{timestamp}", password="pass")

        # Create votes for different options
        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            ip_address="192.168.1.1",
            voter_token="token1",
            idempotency_key="key1",
        )

        Vote.objects.create(
            user=user2,
            poll=poll,
            option=choices[1],
            ip_address="192.168.1.2",
            voter_token="token2",
            idempotency_key="key2",
        )

        distribution = get_vote_distribution(poll.id)

        assert len(distribution) == len(choices)
        assert all(
            "option_id" in item
            and "option_text" in item
            and "vote_count" in item
            and "percentage" in item
            for item in distribution
        )

        # Check percentages sum to 100
        total_percentage = sum(item["percentage"] for item in distribution)
        assert abs(total_percentage - 100.0) < 0.01  # Allow for rounding

    def test_empty_poll_distribution(self, poll, choices):
        """Test distribution for poll with no votes."""
        distribution = get_vote_distribution(poll.id)

        assert len(distribution) == len(choices)
        assert all(item["vote_count"] == 0 for item in distribution)
        assert all(item["percentage"] == 0.0 for item in distribution)


@pytest.mark.django_db
class TestComprehensiveAnalytics:
    """Test comprehensive analytics."""

    def test_get_comprehensive_analytics(self, poll, choices):
        """Test comprehensive analytics calculation."""
        import uuid

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass"
        )

        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            ip_address="192.168.1.1",
            voter_token="token1",
            idempotency_key="key1",
        )

        analytics = get_comprehensive_analytics(poll.id)

        assert "poll_id" in analytics
        assert "poll_title" in analytics
        assert "total_votes" in analytics
        assert "time_series" in analytics
        assert "demographics" in analytics
        assert "participation" in analytics
        assert "vote_distribution" in analytics
        assert "drop_off_rate" in analytics

    def test_empty_poll_comprehensive_analytics(self, poll):
        """Test comprehensive analytics for empty poll."""
        analytics = get_comprehensive_analytics(poll.id)

        assert analytics["total_votes"] == 0
        assert analytics["unique_voters"] == 0
        assert len(analytics["vote_distribution"]) >= 0

    def test_nonexistent_poll_analytics(self):
        """Test analytics for non-existent poll."""
        analytics = get_comprehensive_analytics(99999)

        assert "error" in analytics


@pytest.mark.django_db
class TestAnalyticsSummary:
    """Test analytics summary."""

    def test_get_analytics_summary(self, poll, choices):
        """Test analytics summary calculation."""
        import uuid

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass"
        )

        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            ip_address="192.168.1.1",
            voter_token="token1",
            idempotency_key="key1",
        )

        summary = get_analytics_summary(poll.id)

        assert "poll_id" in summary
        assert "poll_title" in summary
        assert "total_votes" in summary
        assert "unique_voters" in summary
        assert "vote_distribution" in summary

    def test_empty_poll_summary(self, poll):
        """Test summary for empty poll."""
        summary = get_analytics_summary(poll.id)

        assert summary["total_votes"] == 0
        assert summary["unique_voters"] == 0


@pytest.mark.django_db
class TestAnalyticsWithVariousDataVolumes:
    """Test analytics with various data volumes."""

    def test_analytics_with_many_votes(self, poll, choices):
        """Test analytics calculation with many votes."""
        # Create 100 votes
        import time

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        timestamp = int(time.time() * 1000000)
        for i in range(100):
            user = User.objects.create_user(
                username=f"user_{timestamp}_{i}", password="pass"
            )
            Vote.objects.create(
                user=user,
                poll=poll,
                option=choices[i % len(choices)],
                ip_address=f"192.168.1.{i % 10}",
                voter_token=f"token_{timestamp}_{i}",
                idempotency_key=f"key_{timestamp}_{i}",
            )

        # Update cached totals since we created votes directly
        poll.update_cached_totals()
        poll.refresh_from_db()

        analytics = get_comprehensive_analytics(poll.id)

        assert analytics["total_votes"] == 100
        assert analytics["unique_voters"] == 100
        assert len(analytics["vote_distribution"]) == len(choices)

    def test_analytics_time_series_with_many_votes(self, poll, choices):
        """Test time series with many votes."""
        import uuid

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass"
        )

        # Set poll start date before votes are created
        from datetime import datetime
        from datetime import timezone as dt_timezone

        poll.starts_at = datetime(2024, 1, 1, 0, 0, 0, tzinfo=dt_timezone.utc)
        poll.save()

        # Create votes across multiple hours (use different users to avoid unique constraint)
        for hour in range(10):
            voteuser = User.objects.create_user(
                username=f"testuser_h{hour}_{uuid.uuid4().hex[:8]}", password="pass"
            )
            vote_time = poll.starts_at + timedelta(hours=hour)
            with freeze_time(vote_time):
                Vote.objects.create(
                    user=vote_user,
                    poll=poll,
                    option=choices[0],
                    ip_address=f"192.168.1.{hour % 10}",
                    voter_token=f"token_{hour}",
                    idempotency_key=f"key_{hour}",
                )

        # Update cached totals
        poll.update_cached_totals()
        poll.refresh_from_db()

        # Use freeze_time when calling the function to ensure it sees our votes
        with freeze_time(poll.starts_at + timedelta(hours=11)):
            time_series = get_total_votes_over_time(poll.id, interval="hour")

        assert len(time_series) == 10
        assert sum(item["count"] for item in time_series) == 10


@pytest.mark.django_db
@pytest.mark.performance
class TestAnalyticsPerformance:
    """Performance tests for analytics on large datasets."""

    def test_analytics_performance_large_dataset(self, poll, choices):
        """Test analytics performance with large number of votes."""
        import time

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        # Create 1000 votes (simulating large dataset)
        # In real performance test, this would be 10M votes
        timestamp = int(time.time() * 1000000)
        users = []
        for i in range(1000):
            user = User.objects.create_user(
                username=f"user_{timestamp}_{i}", password="pass"
            )
            users.append(user)

        # Create votes (each user votes once on this poll)
        for i, user in enumerate(users):
            Vote.objects.create(
                user=user,
                poll=poll,
                option=choices[i % len(choices)],
                ip_address=f"192.168.1.{i % 100}",
                user_agent=f"Mozilla/5.0 (User {i})",
                voter_token=f"token_{timestamp}_{i}",
                idempotency_key=f"key_{timestamp}_{i}",
            )

        # Update cached counts for analytics
        poll.update_cached_totals()
        poll.refresh_from_db()

        # Measure analytics calculation time
        start_time = time.time()
        analytics = get_comprehensive_analytics(poll.id)
        elapsed_time = time.time() - start_time

        # Verify results
        assert analytics["total_votes"] == 1000
        assert analytics["unique_voters"] == 1000

        # Performance assertion (should complete in reasonable time)
        # For 1000 votes, should be < 5 seconds
        # For 10M votes, would need more sophisticated optimization
        assert elapsed_time < 5.0, f"Analytics took {elapsed_time:.2f}s, expected < 5s"

    def test_time_series_performance_large_dataset(self, poll, choices):
        """Test time series performance with large dataset."""
        import time
        import uuid

        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        user = User.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}", password="pass"
        )

        # Ensure poll has starts_at set to a past date
        if not poll.starts_at:
            poll.starts_at = timezone.now() - timedelta(days=5)
            poll.save()

        # Create votes across many time buckets (use different users to avoid unique constraint)
        base_time = poll.starts_at
        for hour in range(100):
            voteuser = User.objects.create_user(
                username=f"testuser_h{hour}_{uuid.uuid4().hex[:8]}", password="pass"
            )
            vote_time = base_time + timedelta(hours=hour)
            with freeze_time(vote_time):
                Vote.objects.create(
                    user=vote_user,
                    poll=poll,
                    option=choices[0],
                    ip_address=f"192.168.1.{hour % 10}",
                    voter_token=f"token{hour}",
                    idempotency_key=f"key{hour}",
                )

        # Use freeze_time to ensure time_series query uses correct time context
        # Query should include all votes from starts_at to now
        with freeze_time(base_time + timedelta(hours=100)):
            start_time = time.time()
            time_series = get_total_votes_over_time(poll.id, interval="hour")
            elapsed_time = time.time() - start_time

        assert len(time_series) == 100
        assert (
            elapsed_time < 2.0
        ), f"Time series took {elapsed_time:.2f}s, expected < 2s"
