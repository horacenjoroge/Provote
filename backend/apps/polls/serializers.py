"""
Serializers for Polls app.
"""

from rest_framework import serializers
from .models import Poll, Choice


class ChoiceSerializer(serializers.ModelSerializer):
    """Serializer for Choice model."""

    vote_count = serializers.ReadOnlyField()

    class Meta:
        model = Choice
        fields = ["id", "text", "vote_count", "created_at"]


class PollSerializer(serializers.ModelSerializer):
    """Serializer for Poll model."""

    choices = ChoiceSerializer(many=True, read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)
    is_open = serializers.ReadOnlyField()

    class Meta:
        model = Poll
        fields = [
            "id",
            "title",
            "description",
            "created_by",
            "created_at",
            "updated_at",
            "starts_at",
            "ends_at",
            "is_active",
            "is_open",
            "choices",
        ]


class PollCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a Poll."""

    class Meta:
        model = Poll
        fields = ["title", "description", "starts_at", "ends_at", "is_active"]
