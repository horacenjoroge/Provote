"""
URLs for Votes app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import VoteViewSet

router = DefaultRouter()
router.register(r"votes", VoteViewSet, basename="vote")

urlpatterns = [
    path("", include(router.urls)),
]
