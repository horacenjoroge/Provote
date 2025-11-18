"""
Admin configuration for Polls app.
"""

from django.contrib import admin

from .models import Category, Poll, PollOption, Tag

# Backward compatibility
Choice = PollOption


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    """Admin interface for Poll model."""

    list_display = ["title", "category", "created_by", "created_at", "is_active", "is_open", "cached_total_votes", "cached_unique_voters"]
    list_filter = ["is_active", "category", "created_at", "tags"]
    search_fields = ["title", "description", "tags__name"]
    readonly_fields = ["created_at", "updated_at", "cached_total_votes", "cached_unique_voters"]
    filter_horizontal = ["tags"]
    fieldsets = (
        ("Basic Information", {"fields": ("title", "description", "created_by", "category", "tags")}),
        ("Timing", {"fields": ("starts_at", "ends_at", "is_active", "is_draft")}),
        ("Configuration", {"fields": ("settings", "security_rules")}),
        ("Cached Totals", {"fields": ("cached_total_votes", "cached_unique_voters")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(PollOption)
class PollOptionAdmin(admin.ModelAdmin):
    """Admin interface for PollOption model."""

    list_display = ["text", "poll", "order", "cached_vote_count", "vote_count", "created_at"]
    list_filter = ["poll", "created_at"]
    search_fields = ["text", "poll__title"]
    readonly_fields = ["created_at", "cached_vote_count"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin interface for Category model."""

    list_display = ["name", "slug", "poll_count", "created_at"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["created_at"]

    def poll_count(self, obj):
        """Get count of polls in this category."""
        return obj.polls.count()

    poll_count.short_description = "Polls"


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """Admin interface for Tag model."""

    list_display = ["name", "slug", "poll_count", "created_at"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["created_at"]

    def poll_count(self, obj):
        """Get count of polls with this tag."""
        return obj.polls.count()

    poll_count.short_description = "Polls"

# Note: Choice is an alias for PollOption, so no need to register separately
