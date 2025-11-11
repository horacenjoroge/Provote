"""
Admin configuration for Polls app.
"""

from django.contrib import admin

from .models import Poll, PollOption

# Backward compatibility
Choice = PollOption


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    """Admin interface for Poll model."""

    list_display = ["title", "created_by", "created_at", "is_active", "is_open", "cached_total_votes", "cached_unique_voters"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["title", "description"]
    readonly_fields = ["created_at", "updated_at", "cached_total_votes", "cached_unique_voters"]
    fieldsets = (
        ("Basic Information", {"fields": ("title", "description", "created_by")}),
        ("Timing", {"fields": ("starts_at", "ends_at", "is_active")}),
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


# Register backward compatibility alias
admin.site.register(Choice, PollOptionAdmin)
