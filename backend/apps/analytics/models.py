"""
Analytics models for Provote.
"""

from apps.polls.models import Poll
from django.contrib.auth.models import User
from django.db import models


class PollAnalytics(models.Model):
    """Analytics data for polls."""

    poll = models.OneToOneField(
        Poll, on_delete=models.CASCADE, related_name="analytics"
    )
    total_votes = models.IntegerField(default=0)
    unique_voters = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Poll Analytics"

    def __str__(self):
        return f"Analytics for {self.poll.title}"


class AuditLog(models.Model):
    """Audit log for all API requests."""

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    method = models.CharField(max_length=10, help_text="HTTP method (GET, POST, etc.)")
    path = models.CharField(max_length=500, help_text="Request path")
    query_params = models.TextField(
        null=True, blank=True, help_text="Query parameters as JSON string"
    )
    request_body = models.TextField(
        null=True, blank=True, help_text="Request body (truncated to 1000 chars)"
    )
    status_code = models.IntegerField(help_text="HTTP response status code")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    request_id = models.CharField(
        max_length=64, db_index=True, blank=True, help_text="Request ID for tracing"
    )
    response_time = models.FloatField(help_text="Response time in seconds")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["ip_address", "created_at"]),
            models.Index(fields=["request_id"]),
            models.Index(fields=["method", "path", "created_at"]),
        ]

    def __str__(self):
        return f"{self.method} {self.path} - {self.status_code} at {self.created_at}"


class FingerprintBlock(models.Model):
    """
    Permanently blocked fingerprints due to suspicious activity.
    Once a fingerprint is blocked, it cannot be used for voting until manually unblocked.
    """

    fingerprint = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="Blocked browser/device fingerprint hash",
    )
    reason = models.TextField(help_text="Reason for blocking (e.g., 'Used by multiple users')")
    blocked_at = models.DateTimeField(auto_now_add=True, help_text="When the fingerprint was blocked")
    blocked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blocked_fingerprints",
        help_text="User/admin who blocked this fingerprint (null if auto-blocked)",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this block is currently active (can be unblocked by admin)",
    )
    unblocked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the fingerprint was unblocked (if applicable)",
    )
    unblocked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="unblocked_fingerprints",
        help_text="User/admin who unblocked this fingerprint",
    )
    # Metadata
    first_seen_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="first_seen_fingerprints",
        help_text="First user who used this fingerprint",
    )
    total_users = models.IntegerField(
        default=0,
        help_text="Total number of different users who used this fingerprint before blocking",
    )
    total_votes = models.IntegerField(
        default=0,
        help_text="Total number of votes from this fingerprint before blocking",
    )

    class Meta:
        ordering = ["-blocked_at"]
        indexes = [
            models.Index(fields=["fingerprint", "is_active"]),
            models.Index(fields=["is_active", "blocked_at"]),
        ]
        verbose_name = "Blocked Fingerprint"
        verbose_name_plural = "Blocked Fingerprints"

    def __str__(self):
        status = "ACTIVE" if self.is_active else "INACTIVE"
        return f"Blocked fingerprint {self.fingerprint[:16]}... ({status})"

    def unblock(self, user=None):
        """Unblock this fingerprint."""
        self.is_active = False
        from django.utils import timezone

        self.unblocked_at = timezone.now()
        if user:
            self.unblocked_by = user
        self.save()


class FraudAlert(models.Model):
    """
    Fraud alerts for suspicious votes.
    Logs fraud detection events for investigation and analysis.
    """

    vote = models.ForeignKey(
        "votes.Vote",
        on_delete=models.CASCADE,
        related_name="fraud_alerts",
        help_text="Vote that triggered the fraud alert",
    )
    poll = models.ForeignKey(
        Poll,
        on_delete=models.CASCADE,
        related_name="fraud_alerts",
        help_text="Poll where fraud was detected",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fraud_alerts",
        help_text="User who made the suspicious vote",
    )
    ip_address = models.GenericIPAddressField(
        null=True, blank=True, help_text="IP address of suspicious vote"
    )
    reasons = models.TextField(help_text="Comma-separated list of fraud detection reasons")
    risk_score = models.IntegerField(
        help_text="Risk score (0-100) indicating severity of fraud"
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When fraud was detected")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["poll", "created_at"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["ip_address", "created_at"]),
            models.Index(fields=["risk_score", "created_at"]),
        ]
        verbose_name = "Fraud Alert"
        verbose_name_plural = "Fraud Alerts"

    def __str__(self):
        return f"Fraud alert for vote {self.vote.id} (risk: {self.risk_score})"
