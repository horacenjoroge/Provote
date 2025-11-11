"""
Admin configuration for Analytics app.
"""

from django.contrib import admin
from .models import PollAnalytics


@admin.register(PollAnalytics)
class PollAnalyticsAdmin(admin.ModelAdmin):
    """Admin interface for PollAnalytics model."""

    list_display = ["poll", "total_votes", "unique_voters", "last_updated"]
    list_filter = ["last_updated"]
    search_fields = ["poll__title"]
