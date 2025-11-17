"""
Serializers for Votes app.
"""

from rest_framework import serializers

from .models import Vote


class VoteSerializer(serializers.ModelSerializer):
    """Serializer for Vote model with detailed information."""

    user = serializers.StringRelatedField(read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    option = serializers.StringRelatedField(read_only=True)
    option_id = serializers.IntegerField(source="option.id", read_only=True)
    poll = serializers.StringRelatedField(read_only=True)
    poll_id = serializers.IntegerField(source="poll.id", read_only=True)
    poll_title = serializers.CharField(source="poll.title", read_only=True)
    option_text = serializers.CharField(source="option.text", read_only=True)

    class Meta:
        model = Vote
        fields = [
            "id",
            "user",
            "user_id",
            "option",
            "option_id",
            "option_text",
            "poll",
            "poll_id",
            "poll_title",
            "voter_token",
            "idempotency_key",
            "ip_address",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "user_id",
            "option",
            "option_id",
            "option_text",
            "poll",
            "poll_id",
            "poll_title",
            "voter_token",
            "idempotency_key",
            "ip_address",
            "created_at",
        ]


class VoteCastSerializer(serializers.Serializer):
    """Serializer for casting a vote."""

    poll_id = serializers.IntegerField(required=True, help_text="ID of the poll to vote on")
    choice_id = serializers.IntegerField(required=True, help_text="ID of the choice/option to vote for")
    idempotency_key = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=64,
        help_text="Optional idempotency key for retry safety",
    )
    captcha_token = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="reCAPTCHA v3 token (required if poll has enable_captcha enabled)",
    )

    def validate_poll_id(self, value):
        """Validate that poll exists."""
        from apps.polls.models import Poll

        try:
            Poll.objects.get(id=value)
        except Poll.DoesNotExist:
            raise serializers.ValidationError(f"Poll with id {value} does not exist")
        return value

    def validate_choice_id(self, value):
        """Validate that choice exists."""
        from apps.polls.models import PollOption

        try:
            PollOption.objects.get(id=value)
        except PollOption.DoesNotExist:
            raise serializers.ValidationError(f"Choice with id {value} does not exist")
        return value

    def validate(self, attrs):
        """Validate that choice belongs to poll."""
        from apps.polls.models import Poll, PollOption

        poll_id = attrs.get("poll_id")
        choice_id = attrs.get("choice_id")

        try:
            poll = Poll.objects.get(id=poll_id)
            choice = PollOption.objects.get(id=choice_id)
            if choice.poll != poll:
                raise serializers.ValidationError(
                    {"choice_id": f"Choice {choice_id} does not belong to poll {poll_id}"}
                )
        except (Poll.DoesNotExist, PollOption.DoesNotExist):
            # Individual validation errors will be raised by field validators
            pass

        return attrs
