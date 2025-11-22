"""
Tests for admin dashboard API endpoints.
"""

import time
from datetime import timedelta

import pytest
from apps.analytics.models import FraudAlert, IPBlock
from apps.polls.models import Poll, PollOption
from apps.votes.models import Vote
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient


def get_unique_username(prefix="user"):
    """Generate a unique username for tests."""
    return f"{prefix}_{int(time.time() * 1000000)}"


@pytest.mark.django_db
class TestAdminDashboardStatistics:
    """Test system statistics endpoint."""

    def test_statistics_requires_admin(self, user):
        """Test that statistics endpoint requires admin authentication."""
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get("/api/v1/admin-dashboard/statistics/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_statistics_accurate(self, user):
        """Test that statistics are calculated accurately."""

        # Create admin user with unique username
        admin_user = User.objects.create_user(
            username=get_unique_username("admin"),
            password="pass",
            is_staff=True,
            is_superuser=True,
        )

        # Create test data
        poll1 = Poll.objects.create(
            title="Test Poll 1",
            created_by=admin_user,
            is_active=True,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=1),
        )
        _poll2 = Poll.objects.create(
            title="Test Poll 2",
            created_by=admin_user,
            is_active=False,
        )

        option1 = PollOption.objects.create(poll=poll1, text="Option 1")
        option2 = PollOption.objects.create(poll=poll1, text="Option 2")

        # Create votes with unique usernames
        user1 = User.objects.create_user(
            username=get_unique_username("user1"), password="pass"
        )
        user2 = User.objects.create_user(
            username=get_unique_username("user2"), password="pass"
        )

        Vote.objects.create(
            user=user1,
            poll=poll1,
            option=option1,
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )
        Vote.objects.create(
            user=user2,
            poll=poll1,
            option=option2,
            voter_token="token2",
            idempotency_key="key2",
            is_valid=True,
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        response = client.get("/api/v1/admin-dashboard/statistics/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_polls"] == 2
        assert response.data["active_polls"] == 1
        assert response.data["total_votes"] == 2
        assert response.data["total_users"] >= 3  # admin_user, user1, user2

    def test_statistics_includes_fraud_alerts(self, user):
        """Test that statistics include fraud alert counts."""

        # Create admin user with unique username
        admin_user = User.objects.create_user(
            username=get_unique_username("admin"),
            password="pass",
            is_staff=True,
            is_superuser=True,
        )

        poll = Poll.objects.create(title="Test Poll", created_by=admin_user)
        option = PollOption.objects.create(poll=poll, text="Option 1")
        test_user = User.objects.create_user(
            username=get_unique_username("user"), password="pass"
        )

        vote = Vote.objects.create(
            user=test_user,
            poll=poll,
            option=option,
            voter_token="token1",
            idempotency_key="key1",
        )

        FraudAlert.objects.create(
            vote=vote,
            poll=poll,
            user=test_user,
            reasons="Test fraud",
            risk_score=80,
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        response = client.get("/api/v1/admin-dashboard/statistics/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_fraud_alerts"] == 1


@pytest.mark.django_db
class TestAdminDashboardActivity:
    """Test activity feed endpoint."""

    def test_activity_requires_admin(self, user):
        """Test that activity endpoint requires admin authentication."""
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get("/api/v1/admin-dashboard/activity/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_activity_feed_shows_recent_events(self, user):
        """Test that activity feed shows recent events."""

        # Create admin user with unique username
        admin_user = User.objects.create_user(
            username=get_unique_username("admin"),
            password="pass",
            is_staff=True,
            is_superuser=True,
        )

        # Create recent poll
        poll = Poll.objects.create(
            title="Recent Poll",
            created_by=admin_user,
        )
        option = PollOption.objects.create(poll=poll, text="Option 1")

        test_user = User.objects.create_user(
            username=get_unique_username("user"), password="pass"
        )

        # Create recent vote
        Vote.objects.create(
            user=test_user,
            poll=poll,
            option=option,
            voter_token="token1",
            idempotency_key="key1",
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        response = client.get("/api/v1/admin-dashboard/activity/")

        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert len(response.data["results"]) > 0

        # Check that recent events are included
        activities = response.data["results"]
        activity_types = [a["type"] for a in activities]
        assert "vote" in activity_types or "poll_created" in activity_types

    def test_activity_feed_respects_limit(self, user):
        """Test that activity feed respects limit parameter."""
        from apps.polls.models import Poll

        # Create admin user with unique username
        admin_user = User.objects.create_user(
            username=get_unique_username("admin"),
            password="pass",
            is_staff=True,
            is_superuser=True,
        )

        # Create multiple polls
        for i in range(15):
            Poll.objects.create(
                title=f"Poll {i}",
                created_by=admin_user,
            )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        response = client.get("/api/v1/admin-dashboard/activity/?limit=5")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) <= 5


@pytest.mark.django_db
class TestAdminDashboardFraudAlerts:
    """Test fraud alerts endpoint."""

    def test_fraud_alerts_requires_admin(self, user):
        """Test that fraud alerts endpoint requires admin authentication."""
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get("/api/v1/admin-dashboard/fraud-alerts/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_fraud_alerts_appear(self, user):
        """Test that fraud alerts appear in the response."""

        # Create admin user with unique username
        admin_user = User.objects.create_user(
            username=get_unique_username("admin"),
            password="pass",
            is_staff=True,
            is_superuser=True,
        )

        poll = Poll.objects.create(title="Test Poll", created_by=admin_user)
        option = PollOption.objects.create(poll=poll, text="Option 1")
        test_user = User.objects.create_user(
            username=get_unique_username("user"), password="pass"
        )

        vote = Vote.objects.create(
            user=test_user,
            poll=poll,
            option=option,
            voter_token="token1",
            idempotency_key="key1",
        )

        FraudAlert.objects.create(
            vote=vote,
            poll=poll,
            user=test_user,
            ip_address="192.168.1.1",
            reasons="Suspicious voting pattern",
            risk_score=85,
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        response = client.get("/api/v1/admin-dashboard/fraud-alerts/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] == 1
        assert len(response.data["recent"]) > 0
        assert response.data["recent"][0]["risk_score"] == 85
        assert "Suspicious voting pattern" in response.data["recent"][0]["reasons"]

    def test_fraud_alerts_by_risk_score(self, user):
        """Test that fraud alerts are categorized by risk score."""

        # Create admin user with unique username
        admin_user = User.objects.create_user(
            username=get_unique_username("admin"),
            password="pass",
            is_staff=True,
            is_superuser=True,
        )

        poll = Poll.objects.create(title="Test Poll", created_by=admin_user)
        option = PollOption.objects.create(poll=poll, text="Option 1")
        user1 = User.objects.create_user(
            username=get_unique_username("user1"), password="pass"
        )
        user2 = User.objects.create_user(
            username=get_unique_username("user2"), password="pass"
        )

        vote1 = Vote.objects.create(
            user=user1,
            poll=poll,
            option=option,
            voter_token="token1",
            idempotency_key="key1",
        )
        vote2 = Vote.objects.create(
            user=user2,
            poll=poll,
            option=option,
            voter_token="token2",
            idempotency_key="key2",
        )

        # Create alerts with different risk scores
        FraudAlert.objects.create(
            vote=vote1,
            poll=poll,
            user=user1,
            reasons="Critical fraud",
            risk_score=90,
        )
        FraudAlert.objects.create(
            vote=vote2,
            poll=poll,
            user=user2,
            reasons="Low risk",
            risk_score=30,
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        response = client.get("/api/v1/admin-dashboard/fraud-alerts/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["by_risk_score"]["critical"] >= 1
        assert response.data["by_risk_score"]["low"] >= 1


@pytest.mark.django_db
class TestAdminDashboardPerformance:
    """Test performance metrics endpoint."""

    def test_performance_requires_admin(self, user):
        """Test that performance endpoint requires admin authentication."""
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get("/api/v1/admin-dashboard/performance/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_performance_metrics_tracked(self, user):
        """Test that performance metrics endpoint returns data structure."""
        # Create admin user with unique username
        admin_user = User.objects.create_user(
            username=get_unique_username("admin"),
            password="pass",
            is_staff=True,
            is_superuser=True,
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        response = client.get("/api/v1/admin-dashboard/performance/")

        assert response.status_code == status.HTTP_200_OK
        assert "api_latency" in response.data
        assert "db_queries" in response.data
        assert "cache_hit_rate" in response.data
        assert "error_rate" in response.data
        assert "note" in response.data  # Placeholder note


@pytest.mark.django_db
class TestAdminDashboardActivePolls:
    """Test active polls and voters endpoint."""

    def test_active_polls_requires_admin(self, user):
        """Test that active polls endpoint requires admin authentication."""
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get("/api/v1/admin-dashboard/active-polls/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_active_polls_and_voters(self, user):
        """Test that active polls and voters are returned."""

        # Create admin user with unique username
        admin_user = User.objects.create_user(
            username=get_unique_username("admin"),
            password="pass",
            is_staff=True,
            is_superuser=True,
        )

        now = timezone.now()

        # Create active poll
        active_poll = Poll.objects.create(
            title="Active Poll",
            created_by=admin_user,
            is_active=True,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
        )
        option = PollOption.objects.create(poll=active_poll, text="Option 1")

        # Create inactive poll
        inactive_poll = Poll.objects.create(
            title="Inactive Poll",
            created_by=admin_user,
            is_active=False,
        )

        user1 = User.objects.create_user(
            username=get_unique_username("user1"), password="pass"
        )
        user2 = User.objects.create_user(
            username=get_unique_username("user2"), password="pass"
        )

        # Create recent votes
        Vote.objects.create(
            user=user1,
            poll=active_poll,
            option=option,
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )
        Vote.objects.create(
            user=user2,
            poll=active_poll,
            option=option,
            voter_token="token2",
            idempotency_key="key2",
            is_valid=True,
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        response = client.get("/api/v1/admin-dashboard/active-polls/")

        assert response.status_code == status.HTTP_200_OK
        assert "active_polls" in response.data
        assert "recent_voters" in response.data
        assert "top_polls" in response.data

        # Check that active poll is in the list
        active_poll_ids = [p["id"] for p in response.data["active_polls"]]
        assert active_poll.id in active_poll_ids

        # Check that inactive poll is not in active list
        assert inactive_poll.id not in active_poll_ids


@pytest.mark.django_db
class TestAdminDashboardSummary:
    """Test complete dashboard summary endpoint."""

    def test_summary_requires_admin(self, user):
        """Test that summary endpoint requires admin authentication."""
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get("/api/v1/admin-dashboard/summary/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_summary_returns_all_data(self, user):
        """Test that summary returns all dashboard data."""

        # Create admin user with unique username
        admin_user = User.objects.create_user(
            username=get_unique_username("admin"),
            password="pass",
            is_staff=True,
            is_superuser=True,
        )

        poll = Poll.objects.create(title="Test Poll", created_by=admin_user)
        option = PollOption.objects.create(poll=poll, text="Option 1")
        test_user = User.objects.create_user(
            username=get_unique_username("user"), password="pass"
        )

        vote = Vote.objects.create(
            user=test_user,
            poll=poll,
            option=option,
            voter_token="token1",
            idempotency_key="key1",
        )

        FraudAlert.objects.create(
            vote=vote,
            poll=poll,
            user=test_user,
            reasons="Test fraud",
            risk_score=70,
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        response = client.get("/api/v1/admin-dashboard/summary/")

        assert response.status_code == status.HTTP_200_OK
        assert "statistics" in response.data
        assert "recent_activity" in response.data
        assert "fraud_alerts" in response.data
        assert "performance_metrics" in response.data
        assert "active_polls_and_voters" in response.data
        assert "timestamp" in response.data
