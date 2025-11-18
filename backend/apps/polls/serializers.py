"""
Serializers for Polls app with nested option creation and advanced validation.
"""

from django.db import models
from django.utils import timezone
from rest_framework import serializers

from core.utils.language import get_request_language, get_translated_field

from .models import Poll, PollOption

# Validation constants
MIN_OPTIONS = 2
MAX_OPTIONS = 100


class PollOptionSerializer(serializers.ModelSerializer):
    """Serializer for PollOption model with language support."""

    vote_count = serializers.ReadOnlyField()
    cached_vote_count = serializers.ReadOnlyField()

    class Meta:
        model = PollOption
        fields = ["id", "text", "order", "vote_count", "cached_vote_count", "created_at"]
        read_only_fields = ["id", "vote_count", "cached_vote_count", "created_at"]

    def to_representation(self, instance):
        """Override to return translated text based on request language."""
        data = super().to_representation(instance)
        
        # Get language from request context
        request = self.context.get("request")
        if request:
            language_code = get_request_language(request)
            # Get translated text
            data["text"] = get_translated_field(instance, "text", language_code)
        
        return data


class PollOptionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating PollOption with translation support."""

    class Meta:
        model = PollOption
        fields = [
            "text",
            "text_en",
            "text_es",
            "text_fr",
            "text_de",
            "text_sw",
            "order",
        ]
        # Translation fields are optional - if not provided, will use the default language field


class PollSerializer(serializers.ModelSerializer):
    """Serializer for Poll model with options and language support."""

    options = PollOptionSerializer(many=True, read_only=True)
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
            "is_draft",
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

    def to_representation(self, instance):
        """Override to return translated fields based on request language."""
        data = super().to_representation(instance)
        
        # Get language from request context
        request = self.context.get("request")
        if request:
            language_code = get_request_language(request)
            # Get translated title and description
            data["title"] = get_translated_field(instance, "title", language_code)
            data["description"] = get_translated_field(instance, "description", language_code)
        
        return data


class PollCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a Poll with nested options, validation, and translation support."""

    options = PollOptionCreateSerializer(many=True, required=False, allow_empty=True)

    class Meta:
        model = Poll
        fields = [
            "id",
            "title",
            "title_en",
            "title_es",
            "title_fr",
            "title_de",
            "title_sw",
            "description",
            "description_en",
            "description_es",
            "description_fr",
            "description_de",
            "description_sw",
            "starts_at",
            "ends_at",
            "is_active",
            "is_draft",
            "settings",
            "security_rules",
            "options",
        ]
        read_only_fields = ["id"]
        # Translation fields are optional - if not provided, will use the default language field

    def validate_options(self, value):
        """Validate options count."""
        # Allow drafts to be created without options (for auto-save)
        # Check if this is a draft poll
        is_draft = self.initial_data.get("is_draft", False)
        
        if not is_draft and len(value) < MIN_OPTIONS:
            raise serializers.ValidationError(
                f"A poll must have at least {MIN_OPTIONS} options. Provided: {len(value)}"
            )
        if len(value) > MAX_OPTIONS:
            raise serializers.ValidationError(
                f"A poll cannot have more than {MAX_OPTIONS} options. Provided: {len(value)}"
            )
        return value

    def validate_ends_at(self, value):
        """Validate that expiry date is in the future."""
        if value:
            now = timezone.now()
            if value <= now:
                raise serializers.ValidationError(
                    "Expiry date must be in the future."
                )
        return value

    def validate(self, attrs):
        """Validate poll data."""
        starts_at = attrs.get("starts_at")
        ends_at = attrs.get("ends_at")

        # Validate start date is before expiry date
        if starts_at and ends_at:
            if starts_at >= ends_at:
                raise serializers.ValidationError(
                    {
                        "ends_at": "Expiry date must be after start date.",
                        "starts_at": "Start date must be before expiry date.",
                    }
                )

        # Validate options count (check both in options field and after creation)
        # Allow drafts to be created without options (for auto-save)
        is_draft = attrs.get("is_draft", False)
        options_data = attrs.get("options", [])
        
        if not is_draft and len(options_data) < MIN_OPTIONS:
            raise serializers.ValidationError(
                {
                    "options": f"A poll must have at least {MIN_OPTIONS} options. Provided: {len(options_data)}"
                }
            )
        if len(options_data) > MAX_OPTIONS:
            raise serializers.ValidationError(
                {
                    "options": f"A poll cannot have more than {MAX_OPTIONS} options. Provided: {len(options_data)}"
                }
            )

        return attrs

    def create(self, validated_data):
        """Create poll with nested options and translations."""
        options_data = validated_data.pop("options", [])
        
        # Handle default language: if 'title' is provided but 'title_en' is not,
        # modeltranslation will handle it, but we ensure consistency
        if "title" in validated_data and "title_en" not in validated_data:
            validated_data["title_en"] = validated_data["title"]
        if "description" in validated_data and "description_en" not in validated_data:
            validated_data["description_en"] = validated_data["description"]
        
        poll = Poll.objects.create(**validated_data)

        # Create options in order
        for order, option_data in enumerate(options_data, start=0):
            # Remove 'order' from option_data if present, since we're setting it explicitly
            option_data_clean = {k: v for k, v in option_data.items() if k != 'order'}
            # Handle default language for option text
            if "text" in option_data_clean and "text_en" not in option_data_clean:
                option_data_clean["text_en"] = option_data_clean["text"]
            PollOption.objects.create(poll=poll, order=order, **option_data_clean)

        return poll


class PollUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a Poll (limited fields) with validation."""

    class Meta:
        model = Poll
        fields = [
            "title",
            "description",
            "starts_at",
            "ends_at",
            "is_active",
            "is_draft",
            "settings",
            "security_rules",
        ]

    def validate_ends_at(self, value):
        """Validate that expiry date is in the future."""
        if value:
            now = timezone.now()
            if value <= now:
                raise serializers.ValidationError(
                    "Expiry date must be in the future."
                )
        return value

    def validate(self, attrs):
        """Validate that poll can be modified."""
        poll = self.instance
        now = timezone.now()

        # Check if poll has votes
        has_votes = poll.votes.exists()
        allow_option_modification = poll.settings.get("allow_option_modification_after_votes", False)

        if has_votes and not allow_option_modification:
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

        # Validate dates
        starts_at = attrs.get("starts_at", poll.starts_at)
        ends_at = attrs.get("ends_at", poll.ends_at)

        # Validate start date is before expiry date
        if starts_at and ends_at:
            if starts_at >= ends_at:
                raise serializers.ValidationError(
                    {
                        "ends_at": "Expiry date must be after start date.",
                        "starts_at": "Start date must be before expiry date.",
                    }
                )

        # Validate can't activate expired poll
        is_active = attrs.get("is_active", poll.is_active)
        if is_active and ends_at and ends_at < now:
            raise serializers.ValidationError(
                {
                    "is_active": "Cannot activate a poll that has already expired.",
                    "ends_at": f"Poll expired at {ends_at}. Current time: {now}",
                }
            )

        return attrs


class BulkPollOptionCreateSerializer(serializers.Serializer):
    """Serializer for bulk creating poll options with validation."""

    options = PollOptionCreateSerializer(many=True, min_length=1)

    def validate_options(self, value):
        """Validate options count."""
        poll = self.context.get("poll")
        if poll:
            current_count = poll.options.count()
            new_count = len(value)
            total_count = current_count + new_count

            if total_count > MAX_OPTIONS:
                raise serializers.ValidationError(
                    f"Cannot add {new_count} options. Poll already has {current_count} options. "
                    f"Maximum allowed: {MAX_OPTIONS}. Total would be: {total_count}"
                )

            # Check minimum after addition
            if total_count < MIN_OPTIONS:
                raise serializers.ValidationError(
                    f"After adding these options, poll would have {total_count} options. "
                    f"Minimum required: {MIN_OPTIONS}"
                )

        return value

    def validate(self, attrs):
        """Validate that options can be added."""
        poll = self.context.get("poll")
        if not poll:
            return attrs

        # Check if poll has votes and option modification is not allowed
        has_votes = poll.votes.exists()
        allow_option_modification = poll.settings.get("allow_option_modification_after_votes", False)

        if has_votes and not allow_option_modification:
            raise serializers.ValidationError(
                {
                    "options": "Cannot modify options after votes have been cast. "
                    "Set 'allow_option_modification_after_votes' to true in poll settings to allow."
                }
            )

        return attrs

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


class PollTemplateCreateSerializer(serializers.Serializer):
    """Serializer for creating a poll from a template."""

    template_id = serializers.CharField(required=True, help_text="Template ID (yes_no, multiple_choice, etc.)")
    title = serializers.CharField(required=True, max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    custom_options = PollOptionCreateSerializer(many=True, required=False, allow_null=True)
    custom_settings = serializers.DictField(required=False, allow_null=True)
    starts_at = serializers.DateTimeField(required=False, allow_null=True)
    ends_at = serializers.DateTimeField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_template_id(self, value):
        """Validate that template ID exists."""
        from .templates import get_template, list_templates

        template = get_template(value)
        if not template:
            available = list(list_templates().keys())
            raise serializers.ValidationError(
                f"Invalid template ID: {value}. Available templates: {', '.join(available)}"
            )
        return value

    def validate(self, attrs):
        """Validate template data."""
        from .templates import create_poll_from_template, validate_template_options

        template_id = attrs.get("template_id")
        custom_options = attrs.get("custom_options")

        # If custom options provided, validate them
        if custom_options:
            try:
                validate_template_options(custom_options)
            except ValueError as e:
                raise serializers.ValidationError({"custom_options": str(e)})

        return attrs

    def create(self, validated_data):
        """Create poll from template."""
        from .templates import create_poll_from_template

        template_id = validated_data.pop("template_id")
        custom_options = validated_data.pop("custom_options", None)
        custom_settings = validated_data.pop("custom_settings", None)

        # Get poll data from template
        poll_data = create_poll_from_template(
            template_id=template_id,
            title=validated_data.pop("title"),
            description=validated_data.pop("description", ""),
            custom_options=custom_options,
            custom_settings=custom_settings,
            starts_at=validated_data.pop("starts_at", None),
            ends_at=validated_data.pop("ends_at", None),
            is_active=validated_data.pop("is_active", True),
        )

        # Create poll using PollCreateSerializer (avoid circular import)
        serializer = PollCreateSerializer(data=poll_data, context=self.context)
        serializer.is_valid(raise_exception=True)
        poll = serializer.save(created_by=self.context["request"].user)

        return poll
