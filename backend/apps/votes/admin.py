"""
Admin configuration for Votes app.
"""

from django.contrib import admin

from .models import Vote


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    """Admin interface for Vote model."""

    list_display = ["user", "poll", "choice", "created_at"]
    list_filter = ["poll", "created_at"]
    search_fields = ["user__username", "poll__title", "choice__text"]
    readonly_fields = ["created_at", "idempotency_key"]
