"""
Serializers for Polls app with nested option creation.
"""

from django.db import models
from rest_framework import serializers

from .models import Poll, PollOption


class PollOptionSerializer(serializers.ModelSerializer):
    """Serializer for PollOption model."""

    vote_count = serializers.ReadOnlyField(source="vote_count")
    cached_vote_count = serializers.ReadOnlyField()

    class Meta:
        model = PollOption
        fields = ["id", "text", "order", "vote_count", "cached_vote_count", "created_at"]
        read_only_fields = ["id", "vote_count", "cached_vote_count", "created_at"]


class PollOptionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating PollOption."""

    class Meta:
        model = PollOption
        fields = ["text", "order"]


class PollSerializer(serializers.ModelSerializer):
    """Serializer for Poll model with options."""

    options = PollOptionSerializer(many=True, read_only=True, source="options")
    created_by = serializers.StringRelatedField(read_only=True)
    created_by_id = serializers.IntegerField(source="created_by.id", read_only=True)
    is_open = serializers.ReadOnlyField()
    total_votes = serializers.IntegerField(source="cached_total_votes", read_only=True)
    unique_voters = serializers.IntegerField(source="cached_unique_voters", read_only=True)

    class Meta:
        model = Poll
        fields = [
            "id",
            "title",
            "description",
            "created_by",
            "created_by_id",
            "created_at",
            "updated_at",
            "starts_at",
            "ends_at",
            "is_active",
            "is_open",
            "settings",
            "security_rules",
            "total_votes",
            "unique_voters",
            "options",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "created_by_id",
            "created_at",
            "updated_at",
            "is_open",
            "total_votes",
            "unique_voters",
        ]


class PollCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a Poll with nested options."""

    options = PollOptionCreateSerializer(many=True, required=False, allow_empty=True)

    class Meta:
        model = Poll
        fields = [
            "title",
            "description",
            "starts_at",
            "ends_at",
            "is_active",
            "settings",
            "security_rules",
            "options",
        ]

    def create(self, validated_data):
        """Create poll with nested options."""
        options_data = validated_data.pop("options", [])
        poll = Poll.objects.create(**validated_data)

        # Create options in order
        for order, option_data in enumerate(options_data, start=0):
            PollOption.objects.create(poll=poll, order=order, **option_data)

        return poll


class PollUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a Poll (limited fields)."""

    class Meta:
        model = Poll
        fields = [
            "title",
            "description",
            "starts_at",
            "ends_at",
            "is_active",
            "settings",
            "security_rules",
        ]

    def validate(self, attrs):
        """Validate that poll can be modified."""
        poll = self.instance

        # Check if poll has votes
        if poll.votes.exists():
            # Only allow limited modifications
            allowed_fields = {"is_active", "ends_at", "settings", "security_rules"}
            provided_fields = set(attrs.keys())

            # Check if trying to modify restricted fields
            restricted_fields = provided_fields - allowed_fields
            if restricted_fields:
                raise serializers.ValidationError(
                    {
                        "error": f"Cannot modify {', '.join(restricted_fields)} after votes have been cast. "
                        f"Only allowed to modify: is_active, ends_at, settings, security_rules"
                    }
                )

        return attrs


class BulkPollOptionCreateSerializer(serializers.Serializer):
    """Serializer for bulk creating poll options."""

    options = PollOptionCreateSerializer(many=True, min_length=1)

    def create(self, validated_data):
        """Create multiple options for a poll."""
        poll = self.context["poll"]
        options_data = validated_data["options"]

        # Get current max order
        max_order = poll.options.aggregate(max_order=models.Max("order"))["max_order"] or -1

        # Create options
        created_options = []
        for order, option_data in enumerate(options_data, start=max_order + 1):
            option = PollOption.objects.create(poll=poll, order=order, **option_data)
            created_options.append(option)

        return {"options": created_options}
