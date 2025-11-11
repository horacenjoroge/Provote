"""
Admin configuration for Polls app.
"""

from django.contrib import admin

from .models import Choice, Poll


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    """Admin interface for Poll model."""

    list_display = ["title", "created_by", "created_at", "is_active", "is_open"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["title", "description"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    """Admin interface for Choice model."""

    list_display = ["text", "poll", "vote_count", "created_at"]
    list_filter = ["poll", "created_at"]
    search_fields = ["text", "poll__title"]
