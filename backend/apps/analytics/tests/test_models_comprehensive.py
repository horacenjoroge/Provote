"""
Comprehensive unit tests for Analytics models using factories.
Tests all edge cases, error paths, and model methods.
"""

from datetime import timedelta

import pytest
from apps.analytics.factories import (
    AuditLogFactory,
    FingerprintBlockFactory,
    FraudAlertFactory,
    IPBlockFactory,
    IPReputationFactory,
    IPWhitelistFactory,
    PollAnalyticsFactory,
)
from apps.analytics.models import (
    AuditLog,
    FraudAlert,
    PollAnalytics,
)
from django.db import IntegrityError
from django.utils import timezone


@pytest.mark.unit
@pytest.mark.django_db
class TestPollAnalyticsModel:
    """Comprehensive tests for PollAnalytics model."""

    def test_poll_analytics_creation(self, poll):
        """Test creating poll analytics."""
        analytics = PollAnalyticsFactory(poll=poll, total_votes=10, unique_voters=5)
        assert analytics.poll == poll
        assert analytics.total_votes == 10
        assert analytics.unique_voters == 5
        assert analytics.last_updated is not None

    def test_poll_analytics_one_to_one_relationship(self, poll):
        """Test that poll analytics has one-to-one relationship with poll."""
        analytics1 = PollAnalyticsFactory(poll=poll)
        with pytest.raises(IntegrityError):
            PollAnalyticsFactory(poll=poll)

    def test_poll_analytics_str_representation(self, poll):
        """Test poll analytics string representation."""
        analytics = PollAnalyticsFactory(poll=poll)
        assert poll.title in str(analytics)

    def test_poll_analytics_cascade_delete(self, poll):
        """Test that analytics are deleted when poll is deleted."""
        analytics = PollAnalyticsFactory(poll=poll)
        analytics_id = analytics.id
        poll.delete()
        assert not PollAnalytics.objects.filter(id=analytics_id).exists()


@pytest.mark.unit
@pytest.mark.django_db
class TestAuditLogModel:
    """Comprehensive tests for AuditLog model."""

    def test_audit_log_creation(self, user):
        """Test creating an audit log entry."""
        log = AuditLogFactory(
            user=user,
            method="POST",
            path="/api/votes/cast/",
            status_code=201,
            response_time=0.123,
        )
        assert log.user == user
        assert log.method == "POST"
        assert log.path == "/api/votes/cast/"
        assert log.status_code == 201
        assert log.response_time == 0.123
        assert log.created_at is not None

    def test_audit_log_without_user(self):
        """Test audit log can be created without user (anonymous)."""
        log = AuditLogFactory(user=None)
        assert log.user is None

    def test_audit_log_str_representation(self, user):
        """Test audit log string representation."""
        log = AuditLogFactory(
            user=user, method="GET", path="/api/polls/", status_code=200
        )
        assert "GET" in str(log)
        assert "/api/polls/" in str(log)
        assert "200" in str(log)

    def test_audit_log_ordering(self, user):
        """Test that audit logs are ordered by created_at descending."""
        log1 = AuditLogFactory(
            user=user, created_at=timezone.now() - timedelta(hours=1)
        )
        log2 = AuditLogFactory(user=user, created_at=timezone.now())
        logs = list(AuditLog.objects.all())
        assert logs[0] == log2  # Most recent first
        assert logs[1] == log1

    @pytest.mark.skip(
        reason="get_indexes method not available in Django 5.x - use database-specific introspection"
    )
    def test_audit_log_indexes(self, user):
        """Test that audit log has proper indexes."""
        from django.db import connection

        AuditLogFactory(user=user)
        indexes = connection.introspection.get_indexes(
            connection.cursor(), "analytics_auditlog"
        )
        index_fields = [idx["columns"] for idx in indexes.values()]
        assert any("user_id" in fields for fields in index_fields)
        assert any("request_id" in fields for fields in index_fields)


@pytest.mark.unit
@pytest.mark.django_db
class TestIPReputationModel:
    """Comprehensive tests for IPReputation model."""

    def test_ip_reputation_creation(self):
        """Test creating IP reputation."""
        reputation = IPReputationFactory(
            ip_address="192.168.1.1", reputation_score=75, violation_count=2
        )
        assert reputation.ip_address == "192.168.1.1"
        assert reputation.reputation_score == 75
        assert reputation.violation_count == 2
        assert reputation.successful_attempts == 0
        assert reputation.failed_attempts == 0

    def test_ip_reputation_unique_ip(self):
        """Test that IP address must be unique."""
        IPReputationFactory(ip_address="192.168.1.1")
        with pytest.raises(IntegrityError):
            IPReputationFactory(ip_address="192.168.1.1")

    def test_ip_reputation_record_success(self):
        """Test recording a successful attempt."""
        reputation = IPReputationFactory(reputation_score=50)
        initial_score = reputation.reputation_score
        reputation.record_success()
        reputation.refresh_from_db()
        assert reputation.successful_attempts == 1
        assert reputation.reputation_score >= initial_score
        assert reputation.reputation_score <= 100

    def test_ip_reputation_record_violation(self):
        """Test recording a violation."""
        reputation = IPReputationFactory(reputation_score=100, violation_count=0)
        reputation.record_violation(severity=2)
        reputation.refresh_from_db()
        assert reputation.violation_count == 1
        assert reputation.failed_attempts == 1
        assert reputation.reputation_score < 100
        assert reputation.last_violation_at is not None

    def test_ip_reputation_record_violation_severity(self):
        """Test that violation severity affects reputation score."""
        reputation1 = IPReputationFactory(reputation_score=100)
        reputation2 = IPReputationFactory(reputation_score=100)

        reputation1.record_violation(severity=1)
        reputation2.record_violation(severity=5)

        reputation1.refresh_from_db()
        reputation2.refresh_from_db()

        # Higher severity should decrease score more
        assert reputation2.reputation_score < reputation1.reputation_score

    def test_ip_reputation_str_representation(self):
        """Test IP reputation string representation."""
        reputation = IPReputationFactory(
            ip_address="192.168.1.1", reputation_score=75, violation_count=2
        )
        assert "192.168.1.1" in str(reputation)
        assert "75" in str(reputation)
        assert "2" in str(reputation)


@pytest.mark.unit
@pytest.mark.django_db
class TestIPBlockModel:
    """Comprehensive tests for IPBlock model."""

    def test_ip_block_creation(self, user):
        """Test creating an IP block."""
        block = IPBlockFactory(
            ip_address="192.168.1.1",
            reason="Multiple fraud attempts",
            is_manual=True,
            blocked_by=user,
        )
        assert block.ip_address == "192.168.1.1"
        assert block.reason == "Multiple fraud attempts"
        assert block.is_manual is True
        assert block.blocked_by == user
        assert block.is_active is True

    def test_ip_block_unique_ip(self):
        """Test that IP address must be unique."""
        IPBlockFactory(ip_address="192.168.1.1")
        with pytest.raises(IntegrityError):
            IPBlockFactory(ip_address="192.168.1.1")

    def test_ip_block_unblock(self, user):
        """Test unblocking an IP."""
        block = IPBlockFactory(is_active=True)
        unblock_user = user
        block.unblock(unblock_user)
        block.refresh_from_db()
        assert block.is_active is False
        assert block.unblocked_at is not None
        assert block.unblocked_by == unblock_user

    def test_ip_block_unblock_without_user(self):
        """Test unblocking an IP without specifying user."""
        block = IPBlockFactory(is_active=True)
        block.unblock()
        block.refresh_from_db()
        assert block.is_active is False
        assert block.unblocked_at is not None
        assert block.unblocked_by is None

    def test_ip_block_str_representation(self):
        """Test IP block string representation."""
        block = IPBlockFactory(ip_address="192.168.1.1", is_manual=True, is_active=True)
        assert "192.168.1.1" in str(block)
        assert "MANUAL" in str(block)
        assert "ACTIVE" in str(block)


@pytest.mark.unit
@pytest.mark.django_db
class TestIPWhitelistModel:
    """Comprehensive tests for IPWhitelist model."""

    def test_ip_whitelist_creation(self, user):
        """Test creating an IP whitelist entry."""
        whitelist = IPWhitelistFactory(
            ip_address="192.168.1.1", reason="Trusted internal network", created_by=user
        )
        assert whitelist.ip_address == "192.168.1.1"
        assert whitelist.reason == "Trusted internal network"
        assert whitelist.created_by == user
        assert whitelist.is_active is True

    def test_ip_whitelist_unique_ip(self):
        """Test that IP address must be unique."""
        IPWhitelistFactory(ip_address="192.168.1.1")
        with pytest.raises(IntegrityError):
            IPWhitelistFactory(ip_address="192.168.1.1")

    def test_ip_whitelist_str_representation(self):
        """Test IP whitelist string representation."""
        whitelist = IPWhitelistFactory(ip_address="192.168.1.1", is_active=True)
        assert "192.168.1.1" in str(whitelist)
        assert "ACTIVE" in str(whitelist)


@pytest.mark.unit
@pytest.mark.django_db
class TestFingerprintBlockModel:
    """Comprehensive tests for FingerprintBlock model."""

    def test_fingerprint_block_creation(self, user):
        """Test creating a fingerprint block."""
        fingerprint = "a" * 64
        block = FingerprintBlockFactory(
            fingerprint=fingerprint,
            reason="Used by multiple users",
            blocked_by=user,
            is_active=True,
        )
        assert block.fingerprint == fingerprint
        assert block.reason == "Used by multiple users"
        assert block.blocked_by == user
        assert block.is_active is True

    def test_fingerprint_block_unique(self):
        """Test that fingerprint must be unique."""
        fingerprint = "a" * 64
        FingerprintBlockFactory(fingerprint=fingerprint)
        with pytest.raises(IntegrityError):
            FingerprintBlockFactory(fingerprint=fingerprint)

    def test_fingerprint_block_unblock(self, user):
        """Test unblocking a fingerprint."""
        block = FingerprintBlockFactory(is_active=True)
        unblock_user = user
        block.unblock(unblock_user)
        block.refresh_from_db()
        assert block.is_active is False
        assert block.unblocked_at is not None
        assert block.unblocked_by == unblock_user

    def test_fingerprint_block_str_representation(self):
        """Test fingerprint block string representation."""
        fingerprint = "a" * 64
        block = FingerprintBlockFactory(fingerprint=fingerprint, is_active=True)
        assert fingerprint[:16] in str(block)
        assert "ACTIVE" in str(block)


@pytest.mark.unit
@pytest.mark.django_db
class TestFraudAlertModel:
    """Comprehensive tests for FraudAlert model."""

    def test_fraud_alert_creation(self, vote):
        """Test creating a fraud alert."""
        alert = FraudAlertFactory(
            vote=vote, reasons="Suspicious pattern detected", risk_score=85
        )
        assert alert.vote == vote
        assert alert.poll == vote.poll
        assert alert.user == vote.user
        assert alert.reasons == "Suspicious pattern detected"
        assert alert.risk_score == 85
        assert alert.created_at is not None

    def test_fraud_alert_str_representation(self, vote):
        """Test fraud alert string representation."""
        alert = FraudAlertFactory(vote=vote, risk_score=75)
        assert str(vote.id) in str(alert)
        assert "75" in str(alert)

    def test_fraud_alert_ordering(self, vote):
        """Test that fraud alerts are ordered by created_at descending."""
        alert1 = FraudAlertFactory(
            vote=vote, created_at=timezone.now() - timedelta(hours=1)
        )
        alert2 = FraudAlertFactory(vote=vote, created_at=timezone.now())
        alerts = list(FraudAlert.objects.all())
        assert alerts[0] == alert2  # Most recent first
        assert alerts[1] == alert1

    @pytest.mark.skip(
        reason="get_indexes method not available in Django 5.x - use database-specific introspection"
    )
    def test_fraud_alert_indexes(self, vote):
        """Test that fraud alert has proper indexes."""
        from django.db import connection

        FraudAlertFactory(vote=vote)
        indexes = connection.introspection.get_indexes(
            connection.cursor(), "analytics_fraudalert"
        )
        index_fields = [idx["columns"] for idx in indexes.values()]
        assert any("poll_id" in fields for fields in index_fields)
        assert any("risk_score" in fields for fields in index_fields)
