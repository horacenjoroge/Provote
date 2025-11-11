"""
Vote models for Provote.
"""

from apps.polls.models import Choice, Poll
from django.contrib.auth.models import User
from django.db import models


class Vote(models.Model):
    """Model representing a vote on a poll choice."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="votes")
    choice = models.ForeignKey(Choice, on_delete=models.CASCADE, related_name="votes")
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes")
    created_at = models.DateTimeField(auto_now_add=True)
    idempotency_key = models.CharField(max_length=64, unique=True, db_index=True)

    class Meta:
        unique_together = [["user", "poll"]]
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "poll"]),
            models.Index(fields=["poll", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} voted for {self.choice.text} in {self.poll.title}"
