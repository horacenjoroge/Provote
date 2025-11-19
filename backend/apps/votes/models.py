"""
Vote models for Provote with idempotency and audit logging.
"""

from apps.polls.models import Poll, PollOption
from django.contrib.auth.models import User
from django.db import models


class Vote(models.Model):
    """Model representing a vote on a poll option with idempotency and tracking."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="votes", null=True, blank=True)
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name="votes")
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes")
    # Voter identification
    voter_token = models.CharField(max_length=64, db_index=True, help_text="Token for anonymous/guest voting")
    # Idempotency
    idempotency_key = models.CharField(max_length=64, unique=True, db_index=True, help_text="Unique key for idempotent operations")
    # Tracking fields
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True, help_text="IP address of voter")
    user_agent = models.TextField(blank=True, help_text="User agent string")
    fingerprint = models.CharField(max_length=128, blank=True, db_index=True, help_text="Browser/device fingerprint")
    # Fraud detection
    is_valid = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this vote is valid (False if fraud detected)",
    )
    fraud_reasons = models.TextField(
        blank=True,
        help_text="Comma-separated list of fraud detection reasons (if is_valid=False)",
    )
    risk_score = models.IntegerField(
        default=0,
        help_text="Risk score (0-100) from fraud detection",
    )
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Note: unique_together with nullable user field requires special handling
        # For anonymous votes (user=None), uniqueness is enforced by idempotency_key
        # For authenticated votes, uniqueness is enforced by user+poll
        constraints = [
            models.UniqueConstraint(fields=["user", "poll"], condition=models.Q(user__isnull=False), name="unique_user_poll"),
        ]
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["poll", "voter_token"]),  # For poll + voter_token lookups
            models.Index(fields=["idempotency_key"]),  # Already unique, but explicit index
            models.Index(fields=["ip_address", "created_at"]),  # For IP + timestamp queries
            models.Index(fields=["user", "poll"]),  # For user poll lookups
            models.Index(fields=["poll", "created_at"]),  # For poll vote history
            models.Index(fields=["fingerprint", "created_at"]),  # For fingerprint tracking
            models.Index(fields=["is_valid", "poll"]),  # For filtering valid votes
        ]

    def __str__(self):
        return f"{self.user.username} voted for {self.option.text} in {self.poll.title}"


class VoteAttempt(models.Model):
    """
    Immutable audit log of ALL vote attempts (success/failure).
    This table tracks every attempt to vote, regardless of outcome.
    """

    # Vote attempt details
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="vote_attempts")
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="vote_attempts")
    option = models.ForeignKey(PollOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="vote_attempts")
    # Voter identification
    voter_token = models.CharField(max_length=64, db_index=True, blank=True, help_text="Token for anonymous/guest voting")
    # Idempotency
    idempotency_key = models.CharField(max_length=64, db_index=True, help_text="Idempotency key used in attempt")
    # Tracking fields
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.TextField(blank=True)
    fingerprint = models.CharField(max_length=128, blank=True, db_index=True)
    # Outcome
    success = models.BooleanField(default=False, help_text="Whether the vote attempt was successful")
    error_message = models.TextField(blank=True, help_text="Error message if attempt failed")
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["poll", "voter_token"]),
            models.Index(fields=["idempotency_key"]),
            models.Index(fields=["ip_address", "created_at"]),
            models.Index(fields=["success", "created_at"]),
            models.Index(fields=["poll", "created_at"]),
        ]

    def __str__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return f"Vote attempt {status} - Poll: {self.poll.title} at {self.created_at}"


# Backward compatibility alias
Choice = PollOption
