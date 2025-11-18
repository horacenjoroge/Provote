"""
URLs for Analytics app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminDashboardViewSet, PollAnalyticsViewSet

router = DefaultRouter()
router.register(r"analytics", PollAnalyticsViewSet, basename="analytics")
router.register(r"admin-dashboard", AdminDashboardViewSet, basename="admin-dashboard")

urlpatterns = [
    path("", include(router.urls)),
]
