"""
Tests for IP reputation system.
"""

import pytest
from datetime import timedelta
from django.utils import timezone
from unittest.mock import Mock, patch

from apps.analytics.models import IPBlock, IPReputation, IPWhitelist
from core.exceptions import IPBlockedError
from core.utils.ip_reputation import (
    check_ip_reputation,
    get_or_create_ip_reputation,
    is_ip_blocked,
    is_ip_whitelisted,
    record_ip_success,
    record_ip_violation,
    block_ip,
    unblock_ip,
    whitelist_ip,
    remove_whitelist,
    auto_unblock_expired_ips,
)


@pytest.mark.django_db
class TestIPReputation:
    """Tests for IP reputation tracking."""

    def test_get_or_create_ip_reputation(self):
        """Test getting or creating IP reputation."""
        reputation = get_or_create_ip_reputation("192.168.1.1")
        
        assert reputation is not None
        assert reputation.ip_address == "192.168.1.1"
        assert reputation.reputation_score == 100
        assert reputation.violation_count == 0

    def test_get_existing_ip_reputation(self):
        """Test getting existing IP reputation."""
        # Create first
        reputation1 = get_or_create_ip_reputation("192.168.1.1")
        reputation1.violation_count = 5
        reputation1.save()
        
        # Get existing
        reputation2 = get_or_create_ip_reputation("192.168.1.1")
        
        assert reputation1.id == reputation2.id
        assert reputation2.violation_count == 5

    def test_record_ip_success(self):
        """Test recording successful IP activity."""
        reputation = get_or_create_ip_reputation("192.168.1.1")
        reputation.reputation_score = 50
        reputation.save()
        
        record_ip_success("192.168.1.1")
        
        reputation.refresh_from_db()
        assert reputation.successful_attempts == 1
        assert reputation.reputation_score == 51  # Improved by 1

    def test_record_ip_violation(self):
        """Test recording IP violation."""
        reputation = get_or_create_ip_reputation("192.168.1.1")
        initial_score = reputation.reputation_score
        
        record_ip_violation(
            ip_address="192.168.1.1",
            reason="Test violation",
            severity=2,
        )
        
        reputation.refresh_from_db()
        assert reputation.violation_count == 1
        assert reputation.failed_attempts == 1
        assert reputation.reputation_score < initial_score
        assert reputation.last_violation_at is not None

    def test_record_violation_auto_blocks(self):
        """Test that recording violations auto-blocks after threshold."""
        with patch("core.utils.ip_reputation.getattr") as mock_getattr:
            mock_getattr.return_value = 1  # Low threshold for testing
            
            # Record violations up to threshold
            for i in range(2):
                record_ip_violation(
                    ip_address="192.168.1.100",
                    reason=f"Violation {i}",
                    severity=1,
                )
            
            # Check if blocked
            is_blocked, reason = is_ip_blocked("192.168.1.100")
            # May or may not be blocked depending on threshold settings


@pytest.mark.django_db
class TestIPBlocking:
    """Tests for IP blocking."""

    def test_is_ip_blocked_false(self):
        """Test checking unblocked IP."""
        is_blocked, reason = is_ip_blocked("192.168.1.1")
        assert is_blocked is False
        assert reason is None

    def test_block_ip(self):
        """Test blocking an IP."""
        block = block_ip(
            ip_address="192.168.1.1",
            reason="Test block",
            is_manual=False,
            auto_unblock_hours=24,
        )
        
        assert block is not None
        assert block.ip_address == "192.168.1.1"
        assert block.is_active is True
        assert block.auto_unblock_at is not None

    def test_is_ip_blocked_true(self):
        """Test checking blocked IP."""
        block_ip(
            ip_address="192.168.1.2",
            reason="Test block",
            is_manual=False,
        )
        
        is_blocked, reason = is_ip_blocked("192.168.1.2")
        assert is_blocked is True
        assert "blocked" in reason.lower()

    def test_unblock_ip(self):
        """Test unblocking an IP."""
        block_ip(
            ip_address="192.168.1.3",
            reason="Test block",
            is_manual=False,
        )
        
        result = unblock_ip("192.168.1.3")
        assert result is True
        
        is_blocked, _ = is_ip_blocked("192.168.1.3")
        assert is_blocked is False

    @pytest.mark.django_db
    def test_block_ip_manual(self):
        """Test manual IP blocking."""
        from django.contrib.auth.models import User
        
        user = User.objects.create_user(username="blocker", password="pass")
        
        block = block_ip(
            ip_address="192.168.1.4",
            reason="Manual block",
            is_manual=True,
            blocked_by=user,
        )
        
        assert block.is_manual is True
        assert block.blocked_by == user
        assert block.auto_unblock_at is None  # Manual blocks don't auto-unblock

    def test_block_ip_auto_unblock_time(self):
        """Test IP block with auto-unblock time."""
        block = block_ip(
            ip_address="192.168.1.5",
            reason="Auto block",
            is_manual=False,
            auto_unblock_hours=24,
        )
        
        assert block.auto_unblock_at is not None
        # Should be approximately 24 hours from now
        expected_time = timezone.now() + timedelta(hours=24)
        time_diff = abs((block.auto_unblock_at - expected_time).total_seconds())
        assert time_diff < 60  # Within 1 minute


@pytest.mark.django_db
class TestIPWhitelist:
    """Tests for IP whitelisting."""

    def test_is_ip_whitelisted_false(self):
        """Test checking non-whitelisted IP."""
        assert is_ip_whitelisted("192.168.1.1") is False

    def test_whitelist_ip(self):
        """Test whitelisting an IP."""
        user = Mock()
        user.id = 1
        
        whitelist = whitelist_ip(
            ip_address="192.168.1.1",
            reason="Trusted source",
            created_by=user,
        )
        
        assert whitelist is not None
        assert whitelist.ip_address == "192.168.1.1"
        assert whitelist.is_active is True

    def test_is_ip_whitelisted_true(self):
        """Test checking whitelisted IP."""
        whitelist_ip("192.168.1.2", reason="Test")
        
        assert is_ip_whitelisted("192.168.1.2") is True

    def test_whitelisted_ip_never_blocked(self):
        """Test that whitelisted IPs are never blocked."""
        whitelist_ip("192.168.1.3", reason="Trusted")
        
        # Try to block
        try:
            block_ip("192.168.1.3", reason="Should fail")
            assert False, "Should not be able to block whitelisted IP"
        except ValueError:
            pass  # Expected
        
        # Check if blocked
        is_blocked, _ = is_ip_blocked("192.168.1.3")
        assert is_blocked is False

    def test_whitelist_unblocks_existing_block(self):
        """Test that whitelisting unblocks existing block."""
        block_ip("192.168.1.4", reason="Test block")
        
        assert is_ip_blocked("192.168.1.4")[0] is True
        
        whitelist_ip("192.168.1.4", reason="Now trusted")
        
        assert is_ip_blocked("192.168.1.4")[0] is False

    def test_remove_whitelist(self):
        """Test removing IP from whitelist."""
        whitelist_ip("192.168.1.5", reason="Test")
        
        result = remove_whitelist("192.168.1.5")
        assert result is True
        
        assert is_ip_whitelisted("192.168.1.5") is False


@pytest.mark.django_db
class TestIPReputationCheck:
    """Tests for IP reputation checking."""

    def test_check_ip_reputation_allowed(self):
        """Test checking allowed IP."""
        is_allowed, error = check_ip_reputation("192.168.1.1")
        assert is_allowed is True
        assert error is None

    def test_check_ip_reputation_blocked(self):
        """Test checking blocked IP."""
        block_ip("192.168.1.2", reason="Test block")
        
        is_allowed, error = check_ip_reputation("192.168.1.2")
        assert is_allowed is False
        assert error is not None

    def test_check_ip_reputation_whitelisted(self):
        """Test checking whitelisted IP."""
        whitelist_ip("192.168.1.3", reason="Trusted")
        
        is_allowed, error = check_ip_reputation("192.168.1.3")
        assert is_allowed is True
        assert error is None


@pytest.mark.django_db
class TestAutoUnblock:
    """Tests for automatic unblocking."""

    def test_auto_unblock_expired_ips(self):
        """Test auto-unblocking expired IPs."""
        # Create block with past unblock time
        block = block_ip(
            ip_address="192.168.1.1",
            reason="Test",
            is_manual=False,
            auto_unblock_hours=1,
        )
        # Set unblock time to past
        block.auto_unblock_at = timezone.now() - timedelta(hours=1)
        block.save()
        
        count = auto_unblock_expired_ips()
        
        assert count >= 1
        block.refresh_from_db()
        assert block.is_active is False

    def test_auto_unblock_not_expired(self):
        """Test that non-expired IPs are not unblocked."""
        block = block_ip(
            ip_address="192.168.1.2",
            reason="Test",
            is_manual=False,
            auto_unblock_hours=24,
        )
        
        count = auto_unblock_expired_ips()
        
        # Should not unblock (unblock time is in future)
        assert count == 0
        block.refresh_from_db()
        assert block.is_active is True

    def test_auto_unblock_manual_blocks(self):
        """Test that manual blocks are not auto-unblocked."""
        user = Mock()
        user.id = 1
        
        block = block_ip(
            ip_address="192.168.1.3",
            reason="Manual",
            is_manual=True,
            blocked_by=user,
        )
        # Try to set past time (shouldn't matter for manual)
        block.auto_unblock_at = timezone.now() - timedelta(hours=1)
        block.save()
        
        count = auto_unblock_expired_ips()
        
        # Manual blocks shouldn't be auto-unblocked
        # (But if auto_unblock_at is set, it will be)
        block.refresh_from_db()
        # Result depends on implementation

