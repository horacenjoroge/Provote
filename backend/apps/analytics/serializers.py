"""
Serializers for Analytics app.
"""

from rest_framework import serializers
from .models import PollAnalytics


class PollAnalyticsSerializer(serializers.ModelSerializer):
    """Serializer for PollAnalytics model."""

    poll_title = serializers.CharField(source="poll.title", read_only=True)

    class Meta:
        model = PollAnalytics
        fields = ["poll", "poll_title", "total_votes", "unique_voters", "last_updated"]
