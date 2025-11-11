"""
Admin configuration for Votes app.
"""

from django.contrib import admin

from .models import Vote, VoteAttempt


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    """Admin interface for Vote model."""

    list_display = ["user", "poll", "option", "voter_token", "ip_address", "created_at"]
    list_filter = ["poll", "created_at"]
    search_fields = ["user__username", "poll__title", "option__text", "voter_token", "idempotency_key", "ip_address"]
    readonly_fields = ["created_at", "idempotency_key"]
    fieldsets = (
        ("Vote Details", {"fields": ("user", "poll", "option")}),
        ("Identification", {"fields": ("voter_token", "idempotency_key")}),
        ("Tracking", {"fields": ("ip_address", "user_agent", "fingerprint")}),
        ("Timestamp", {"fields": ("created_at",)}),
    )


@admin.register(VoteAttempt)
class VoteAttemptAdmin(admin.ModelAdmin):
    """Admin interface for VoteAttempt model (audit log)."""

    list_display = ["poll", "user", "option", "success", "ip_address", "created_at"]
    list_filter = ["success", "poll", "created_at"]
    search_fields = ["user__username", "poll__title", "option__text", "voter_token", "idempotency_key", "ip_address", "error_message"]
    readonly_fields = ["created_at"]
    fieldsets = (
        ("Attempt Details", {"fields": ("user", "poll", "option")}),
        ("Identification", {"fields": ("voter_token", "idempotency_key")}),
        ("Tracking", {"fields": ("ip_address", "user_agent", "fingerprint")}),
        ("Outcome", {"fields": ("success", "error_message")}),
        ("Timestamp", {"fields": ("created_at",)}),
    )
