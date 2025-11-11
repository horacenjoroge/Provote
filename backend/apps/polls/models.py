"""
Poll models for Provote.
"""

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class Poll(models.Model):
    """Model representing a poll."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="polls")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

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


class Choice(models.Model):
    """Model representing a choice in a poll."""

    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.poll.title} - {self.text}"

    @property
    def vote_count(self):
        """Get the number of votes for this choice."""
        return self.votes.count()
