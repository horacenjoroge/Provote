"""
Views for Analytics app.
"""

from rest_framework import viewsets

from .models import PollAnalytics
from .serializers import PollAnalyticsSerializer


class PollAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for PollAnalytics model."""

    queryset = PollAnalytics.objects.all()
    serializer_class = PollAnalyticsSerializer
