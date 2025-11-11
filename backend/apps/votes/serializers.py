"""
Serializers for Votes app.
"""

from rest_framework import serializers

from .models import Vote


class VoteSerializer(serializers.ModelSerializer):
    """Serializer for Vote model."""

    user = serializers.StringRelatedField(read_only=True)
    choice = serializers.StringRelatedField(read_only=True)
    poll = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Vote
        fields = ["id", "user", "choice", "poll", "created_at"]


class VoteCreateSerializer(serializers.Serializer):
    """Serializer for creating a Vote."""

    poll_id = serializers.IntegerField()
    choice_id = serializers.IntegerField()
    idempotency_key = serializers.CharField(required=False, allow_blank=True)
