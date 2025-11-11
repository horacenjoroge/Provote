"""
Poll models for Provote.
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Poll(models.Model):
    """Model representing a poll with settings, security rules, and cached totals."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="polls")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # Settings: JSON field for flexible poll configuration
    settings = models.JSONField(default=dict, blank=True, help_text="Poll settings (e.g., allow_multiple_votes, show_results)")
    # Security rules: JSON field for security configuration
    security_rules = models.JSONField(default=dict, blank=True, help_text="Security rules (e.g., require_authentication, ip_whitelist)")
    # Cached totals for performance
    cached_total_votes = models.IntegerField(default=0, help_text="Cached total vote count")
    cached_unique_voters = models.IntegerField(default=0, help_text="Cached unique voter count")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
        ]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        """Check if the poll is currently open for voting."""
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at > now:
            return False
        if self.ends_at and self.ends_at < now:
            return False
        return True

    def update_cached_totals(self):
        """Update cached vote totals from actual vote counts."""
        self.cached_total_votes = self.votes.count()
        self.cached_unique_voters = self.votes.values("user").distinct().count()
        self.save(update_fields=["cached_total_votes", "cached_unique_voters"])


class PollOption(models.Model):
    """Model representing a voting option in a poll with order and cached vote count."""

    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=200)
    order = models.IntegerField(default=0, help_text="Display order for options")
    cached_vote_count = models.IntegerField(default=0, help_text="Cached vote count for performance")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        indexes = [
            models.Index(fields=["poll", "order"]),
        ]

    def __str__(self):
        return f"{self.poll.title} - {self.text}"

    @property
    def vote_count(self):
        """Get the number of votes for this option."""
        return self.votes.count()

    def update_cached_vote_count(self):
        """Update cached vote count from actual vote count."""
        self.cached_vote_count = self.votes.count()
        self.save(update_fields=["cached_vote_count"])


# Backward compatibility alias
Choice = PollOption
