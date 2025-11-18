"""
Admin configuration for Users app.
"""

from django.contrib import admin

from .models import Follow, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin interface for UserProfile model."""

    list_display = ["user", "created_at"]
    search_fields = ["user__username"]


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    """Admin interface for Follow model."""

    list_display = ["follower", "following", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["follower__username", "following__username"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"
