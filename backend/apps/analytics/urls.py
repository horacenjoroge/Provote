"""
URLs for Analytics app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PollAnalyticsViewSet

router = DefaultRouter()
router.register(r"analytics", PollAnalyticsViewSet, basename="analytics")

urlpatterns = [
    path("", include(router.urls)),
]
