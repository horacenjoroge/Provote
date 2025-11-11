"""
Admin configuration for Users app.
"""

from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin interface for UserProfile model."""

    list_display = ["user", "created_at"]
    search_fields = ["user__username"]
