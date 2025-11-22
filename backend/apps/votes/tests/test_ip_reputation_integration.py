"""
Integration tests for IP reputation system in vote casting.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from apps.analytics.models import IPWhitelist
from apps.polls.models import PollOption
from core.exceptions import IPBlockedError
from core.utils.ip_reputation import block_ip, record_ip_violation, whitelist_ip
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestIPReputationIntegration:
    """Integration tests for IP reputation in vote casting."""

    def test_blocked_ip_cant_vote(self, user, poll, choices):
        """Test that blocked IP cannot vote."""
        # Block IP
        block_ip(
            ip_address="192.168.1.100",
            reason="Test block",
            is_manual=False,
        )

        client = APIClient()
        client.force_authenticate(user=user)

        # Set IP address in request META
        response = client.post(
            "/api/v1/votes/cast/",
            {
                "poll_id": poll.id,
                "choice_id": choices[0].id,
            },
            format="json",
            REMOTE_ADDR="192.168.1.100",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["error_code"] == "IPBlockedError"
        assert "blocked" in response.data["error"].lower()

    def test_ip_blocked_after_threshold_violations(self, user, poll, choices):
        """Test that IP is blocked after threshold violations."""
        from django.conf import settings

        threshold = getattr(settings, "IP_VIOLATION_THRESHOLD", 5)

        # Record violations up to threshold
        for i in range(threshold):
            record_ip_violation(
                ip_address="192.168.1.101",
                reason=f"Violation {i}",
                severity=1,
            )

        # Check if blocked
        from core.utils.ip_reputation import is_ip_blocked

        is_blocked, _ = is_ip_blocked("192.168.1.101")

        # Should be blocked after threshold
        assert is_blocked is True

        # Try to vote
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(
            "/api/v1/votes/cast/",
            {
                "poll_id": poll.id,
                "choice_id": choices[0].id,
            },
            format="json",
            REMOTE_ADDR="192.168.1.101",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_ip_unblocked_after_time(self, user, poll, choices):
        """Test that IP is unblocked after time period."""
        # Block IP with auto-unblock
        block = block_ip(
            ip_address="192.168.1.102",
            reason="Test",
            is_manual=False,
            auto_unblock_hours=1,
        )

        # Set unblock time to past
        block.auto_unblock_at = timezone.now() - timedelta(minutes=1)
        block.save()

        # Auto-unblock
        from core.utils.ip_reputation import auto_unblock_expired_ips

        auto_unblock_expired_ips()

        # Check if unblocked
        from core.utils.ip_reputation import is_ip_blocked

        is_blocked, _ = is_ip_blocked("192.168.1.102")
        assert is_blocked is False

        # Should be able to vote now
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(
            "/api/v1/votes/cast/",
            {
                "poll_id": poll.id,
                "choice_id": choices[0].id,
            },
            format="json",
            REMOTE_ADDR="192.168.1.102",
        )

        # Should succeed (may be 201, 200, or 409 depending on vote status)
        assert response.status_code in [201, 200, 409]

    def test_whitelisted_ip_never_blocked(self, user, poll, choices):
        """Test that whitelisted IP is never blocked."""
        # Whitelist IP
        whitelist_ip("192.168.1.103", reason="Trusted source")

        # Try to record violations (should not block)
        for i in range(10):  # More than threshold
            record_ip_violation(
                ip_address="192.168.1.103",
                reason=f"Violation {i}",
                severity=1,
            )

        # Check if blocked (should not be)
        from core.utils.ip_reputation import is_ip_blocked

        is_blocked, _ = is_ip_blocked("192.168.1.103")
        assert is_blocked is False

        # Should be able to vote
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(
            "/api/v1/votes/cast/",
            {
                "poll_id": poll.id,
                "choice_id": choices[0].id,
            },
            format="json",
            REMOTE_ADDR="192.168.1.103",
        )

        # Should succeed
        assert response.status_code in [201, 200, 409]

    def test_manual_block_unblock(self, user, poll, choices):
        """Test manual block and unblock."""
        admin_user = User.objects.create_user(
            username="admin",
            password="adminpass",
            is_staff=True,
        )

        # Manually block IP
        block = block_ip(
            ip_address="192.168.1.104",
            reason="Manual block by admin",
            is_manual=True,
            blocked_by=admin_user,
        )

        # Check blocked
        from core.utils.ip_reputation import is_ip_blocked

        is_blocked, _ = is_ip_blocked("192.168.1.104")
        assert is_blocked is True

        # Try to vote (should fail)
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(
            "/api/v1/votes/cast/",
            {
                "poll_id": poll.id,
                "choice_id": choices[0].id,
            },
            format="json",
            REMOTE_ADDR="192.168.1.104",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Manually unblock
        from core.utils.ip_reputation import unblock_ip

        unblock_ip("192.168.1.104", unblocked_by=admin_user)

        # Check unblocked
        is_blocked, _ = is_ip_blocked("192.168.1.104")
        assert is_blocked is False

        # Should be able to vote now
        response = client.post(
            "/api/v1/votes/cast/",
            {
                "poll_id": poll.id,
                "choice_id": choices[0].id,
            },
            format="json",
            REMOTE_ADDR="192.168.1.104",
        )

        # Should succeed
        assert response.status_code in [201, 200, 409]

    def test_successful_vote_records_ip_success(self, user, poll, choices):
        """Test that successful vote records IP success."""
        from core.utils.ip_reputation import get_or_create_ip_reputation

        ip_address = "192.168.1.105"

        # Get initial reputation
        reputation = get_or_create_ip_reputation(ip_address)
        initial_successful = reputation.successful_attempts
        initial_score = reputation.reputation_score

        # Cast vote
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(
            "/api/v1/votes/cast/",
            {
                "poll_id": poll.id,
                "choice_id": choices[0].id,
            },
            format="json",
            REMOTE_ADDR=ip_address,
        )

        # Check reputation updated
        reputation.refresh_from_db()
        assert reputation.successful_attempts == initial_successful + 1
        # Score may have improved slightly
        assert reputation.reputation_score >= initial_score
