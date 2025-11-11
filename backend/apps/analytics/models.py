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
