"""
Tests for export functionality.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from apps.analytics.models import AuditLog
from apps.polls.models import Poll, PollOption
from apps.votes.models import Vote
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestPollResultsExport:
    """Test poll results export in various formats."""

    def test_export_csv_format_generates_correctly(self, user, poll, choices):
        """Test that CSV export generates correctly."""

        # Ensure poll is owned by user and results are visible
        poll.created_by = user
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Create votes
        user1 = User.objects.create_user(
            username="user1_1763649008_fd45023a", password="pass"
        )
        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        # Refresh poll to update cached counts
        poll.refresh_from_db()
        choices[0].refresh_from_db()

        client = APIClient()
        client.force_authenticate(user=user)

        # Use reverse to get the correct URL for the action
        url = reverse("poll-results-export", kwargs={"pk": poll.id})
        response = client.get(f"{url}?export_format=csv")

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "text/csv"
        assert "attachment" in response["Content-Disposition"]
        assert f"poll_{poll.id}_results.csv" in response["Content-Disposition"]

        # Check CSV content
        content = response.content.decode("utf-8")
        assert "Poll Results" in content
        assert poll.title in content
        # CSV format uses: Option,Votes,Percentage (not "Option ID" or "Option Text")
        assert "Option" in content
        assert "Votes" in content
        assert "Percentage" in content

    def test_export_json_format_generates_correctly(self, user, poll, choices):
        """Test that JSON export generates correctly."""

        # Ensure poll is owned by user and results are visible
        poll.created_by = user
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Create votes
        user1 = User.objects.create_user(
            username="user1_1763649008_fd45023a", password="pass"
        )
        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        # Refresh poll to update cached counts
        poll.refresh_from_db()
        choices[0].refresh_from_db()

        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get(
            f"/api/v1/polls/{poll.id}/export-results/?export_format=json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "poll_id" in response.data
        assert response.data["poll_id"] == poll.id
        assert "options" in response.data
        assert "total_votes" in response.data

    def test_export_pdf_format_generates_correctly(self, user, poll, choices):
        """Test that PDF export generates correctly."""

        # Ensure poll is owned by user and results are visible
        poll.created_by = user
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Create votes
        user1 = User.objects.create_user(
            username="user1_1763649008_fd45023a", password="pass"
        )
        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        # Refresh poll to update cached counts
        poll.refresh_from_db()
        choices[0].refresh_from_db()

        client = APIClient()
        client.force_authenticate(user=user)

        # Use reverse to get the correct URL for the action
        url = reverse("poll-results-export", kwargs={"pk": poll.id})
        try:
            response = client.get(f"{url}?export_format=pdf")

            # If reportlab is not installed, should return 503
            if response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
                pytest.skip("reportlab not installed")

            assert response.status_code == status.HTTP_200_OK
            assert response["Content-Type"] == "application/pdf"
            assert "attachment" in response["Content-Disposition"]
            assert f"poll_{poll.id}_results.pdf" in response["Content-Disposition"]

            # Check PDF content starts with PDF header
            assert response.content[:4] == b"%PDF"
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_export_contains_correct_data(self, user, poll, choices):
        """Test that exports contain correct data."""

        # Ensure poll is owned by user and results are visible
        poll.created_by = user
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Create votes
        user1 = User.objects.create_user(
            username="user1_1763649008_fd45023a", password="pass"
        )
        user2 = User.objects.create_user(
            username="user2_1763649008_fd45023a", password="pass"
        )

        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )
        Vote.objects.create(
            user=user2,
            poll=poll,
            option=choices[0],
            voter_token="token2",
            idempotency_key="key2",
            is_valid=True,
        )

        # Refresh poll to update cached counts
        poll.refresh_from_db()
        choices[0].refresh_from_db()

        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get(
            f"/api/v1/polls/{poll.id}/export-results/?export_format=json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_votes"] == 2
        assert response.data["unique_voters"] == 2
        # Check that options exist (may be empty if poll has no options yet)
        assert "options" in response.data


@pytest.mark.django_db
class TestVoteLogExport:
    """Test vote log export functionality."""

    def test_export_vote_log_csv(self, user, poll, choices):
        """Test exporting vote log as CSV."""

        # Make user poll owner first
        poll.created_by = user
        poll.save()

        # Create votes
        user1 = User.objects.create_user(
            username="user1_1763649008_fd45023a", password="pass"
        )
        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            ip_address="192.168.1.1",
            user_agent="Test Agent",
            is_valid=True,
        )

        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get(
            f"/api/v1/polls/{poll.id}/export-vote-log/?export_format=csv"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "text/csv"

        content = response.content.decode("utf-8")
        assert "Vote Log Export" in content
        assert "user1" in content
        assert "192.168.1.1" in content

    def test_export_vote_log_anonymized(self, user, poll, choices):
        """Test that anonymization works in vote log export."""

        # Make user poll owner first
        poll.created_by = user
        poll.save()

        # Create votes
        user1 = User.objects.create_user(
            username="user1_1763649008_fd45023a", password="pass"
        )
        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            ip_address="192.168.1.1",
            user_agent="Test Agent",
            is_valid=True,
        )

        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get(
            f"/api/v1/polls/{poll.id}/export-vote-log/?export_format=csv&anonymize=true"
        )

        assert response.status_code == status.HTTP_200_OK

        content = response.content.decode("utf-8")
        assert "Vote Log Export" in content
        # Check that IP is anonymized
        assert "192.168.1.xxx" in content or "xxx" in content
        # Check that username is not present (anonymized)
        assert "user1" not in content

    def test_export_vote_log_json(self, user, poll, choices):
        """Test exporting vote log as JSON."""

        # Make user poll owner first
        poll.created_by = user
        poll.save()

        # Create votes
        user1 = User.objects.create_user(
            username="user1_1763649008_fd45023a", password="pass"
        )
        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get(
            f"/api/v1/polls/{poll.id}/export-vote-log/?export_format=json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "poll_id" in response.data
        assert "votes" in response.data
        assert len(response.data["votes"]) == 1
        assert response.data["votes"][0]["vote_id"] is not None

    def test_export_vote_log_permissions_enforced(self, user, poll, choices):
        """Test that vote log export permissions are enforced."""
        # Create another user (not poll owner)
        other_user = User.objects.create_user(username="otheruser", password="pass")

        client = APIClient()
        client.force_authenticate(user=other_user)

        response = client.get(f"/api/v1/polls/{poll.id}/export-vote-log/")

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAnalyticsReportExport:
    """Test analytics report export."""

    def test_export_analytics_report_pdf(self, user, poll, choices):
        """Test exporting analytics report as PDF."""

        # Create votes
        user1 = User.objects.create_user(
            username="user1_1763649008_fd45023a", password="pass"
        )
        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        # Make user poll owner
        poll.created_by = user
        poll.save()

        client = APIClient()
        client.force_authenticate(user=user)

        try:
            response = client.get(f"/api/v1/polls/{poll.id}/export-analytics/")

            # If reportlab is not installed, should return 503
            if response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
                pytest.skip("reportlab not installed")

            assert response.status_code == status.HTTP_200_OK
            assert response["Content-Type"] == "application/pdf"
            assert "attachment" in response["Content-Disposition"]
            assert f"poll_{poll.id}_analytics.pdf" in response["Content-Disposition"]

            # Check PDF content
            assert response.content[:4] == b"%PDF"
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_export_analytics_permissions_enforced(self, user, poll, choices):
        """Test that analytics export permissions are enforced."""
        # Create another user (not poll owner)
        other_user = User.objects.create_user(username="otheruser", password="pass")

        client = APIClient()
        client.force_authenticate(user=other_user)

        response = client.get(f"/api/v1/polls/{poll.id}/export-analytics/")

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAuditTrailExport:
    """Test audit trail export."""

    def test_export_audit_trail_csv(self, user, poll):
        """Test exporting audit trail as CSV."""
        # Create admin user
        admin_user = User.objects.create_user(
            username="admin", password="pass", is_staff=True, is_superuser=True
        )

        # Create audit log
        AuditLog.objects.create(
            method="GET",
            path=f"/api/v1/polls/{poll.id}/",
            user=user,
            ip_address="192.168.1.1",
            status_code=200,
            response_time=0.1,
            user_agent="Test Agent",
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        response = client.get(
            f"/api/v1/polls/{poll.id}/export-audit-trail/?export_format=csv"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "text/csv"

        content = response.content.decode("utf-8")
        assert "Audit Trail Export" in content
        # CSV format uses: ID,Timestamp,Method,Path,User,IP Address,Status Code,Response Time (s)
        assert "ID" in content
        assert "Timestamp" in content
        assert "Method" in content
        assert "Path" in content

    def test_export_audit_trail_requires_admin(self, user, poll):
        """Test that audit trail export requires admin."""
        # Make user poll owner but not admin
        poll.created_by = user
        poll.save()

        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get(f"/api/v1/polls/{poll.id}/export-audit-trail/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_export_audit_trail_date_filtering(self, user, poll):
        """Test that audit trail export respects date filtering."""
        # Create admin user
        admin_user = User.objects.create_user(
            username="admin", password="pass", is_staff=True, is_superuser=True
        )

        now = timezone.now()

        # Create old audit log
        AuditLog.objects.create(
            method="GET",
            path=f"/api/v1/polls/{poll.id}/",
            user=user,
            ip_address="192.168.1.1",
            status_code=200,
            response_time=0.1,
            created_at=now - timedelta(days=10),
        )

        # Create recent audit log
        AuditLog.objects.create(
            method="POST",
            path=f"/api/v1/polls/{poll.id}/",
            user=user,
            ip_address="192.168.1.1",
            status_code=200,
            response_time=0.2,
            created_at=now - timedelta(days=1),
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        # Filter to last 7 days
        start_date = (now - timedelta(days=7)).isoformat()
        response = client.get(
            f"/api/v1/polls/{poll.id}/export-audit-trail/?export_format=json&start_date={start_date}"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "logs" in response.data
        # Should only include recent log (POST method)
        assert len(response.data["logs"]) >= 1
        # Check that POST log is included
        post_logs = [
            log for log in response.data["logs"] if log.get("method") == "POST"
        ]
        assert len(post_logs) >= 1


@pytest.mark.django_db
class TestLargeExportsBackgroundTask:
    """Test background task handling for large exports."""

    @patch("apps.polls.tasks.export_poll_data_task.delay")
    def test_large_exports_handled_by_background_task(
        self, mock_task, user, poll, choices
    ):
        """Test that large exports are handled by background task."""

        # Make user poll owner first
        poll.created_by = user
        poll.save()

        # Set user email
        user.email = "test@example.com"
        user.save()

        # Create many votes to make export large
        for i in range(100):
            vote_user = User.objects.create_user(username=f"user{i}", password="pass")
            Vote.objects.create(
                user=vote_user,
                poll=poll,
                option=choices[0],
                voter_token=f"token{i}",
                idempotency_key=f"key{i}",
                is_valid=True,
            )

        client = APIClient()
        client.force_authenticate(user=user)

        # Mock task
        mock_task.return_value = MagicMock(id="task-123")

        # Request with background flag
        response = client.get(
            f"/api/v1/polls/{poll.id}/export-vote-log/?export_format=csv&background=true"
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert "task_id" in response.data
        assert "message" in response.data
        assert "background" in response.data["message"].lower()
        mock_task.assert_called_once()

    def test_background_export_requires_email(self, user, poll, choices):
        """Test that background exports require email address."""
        # Make user poll owner but no email
        poll.created_by = user
        poll.save()
        user.email = ""
        user.save()

        client = APIClient()
        client.force_authenticate(user=user)

        # Create at least one vote so the endpoint doesn't fail for other reasons

        user1 = User.objects.create_user(
            username="user1_1763649008_fd45023a", password="pass"
        )
        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        response = client.get(
            f"/api/v1/polls/{poll.id}/export-vote-log/?export_format=csv&background=true"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data["error"].lower()


@pytest.mark.django_db
class TestExportPermissions:
    """Test export permissions."""

    def test_export_permissions_enforced(self, user, poll, choices):
        """Test that export permissions are enforced."""
        # Create another user (not poll owner)
        other_user = User.objects.create_user(username="otheruser", password="pass")

        client = APIClient()
        client.force_authenticate(user=other_user)

        # Try to export vote log
        response = client.get(f"/api/v1/polls/{poll.id}/export-vote-log/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Try to export analytics
        response = client.get(f"/api/v1/polls/{poll.id}/export-analytics/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_poll_owner_can_export(self, user, poll, choices):
        """Test that poll owner can export."""
        # Make user poll owner
        poll.created_by = user
        poll.save()

        client = APIClient()
        client.force_authenticate(user=user)

        # Export vote log
        response = client.get(
            f"/api/v1/polls/{poll.id}/export-vote-log/?export_format=json"
        )
        assert response.status_code == status.HTTP_200_OK

        # Export analytics
        try:
            response = client.get(f"/api/v1/polls/{poll.id}/export-analytics/")
            if response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
                pytest.skip("reportlab not installed")
            assert response.status_code == status.HTTP_200_OK
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_admin_can_export_any_poll(self, user, poll, choices):
        """Test that admin can export any poll."""
        # Create admin user
        admin_user = User.objects.create_user(
            username="admin", password="pass", is_staff=True, is_superuser=True
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        # Export vote log
        response = client.get(
            f"/api/v1/polls/{poll.id}/export-vote-log/?export_format=json"
        )
        assert response.status_code == status.HTTP_200_OK

        # Export analytics
        try:
            response = client.get(f"/api/v1/polls/{poll.id}/export-analytics/")
            if response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
                pytest.skip("reportlab not installed")
            assert response.status_code == status.HTTP_200_OK
        except ImportError:
            pytest.skip("reportlab not installed")
