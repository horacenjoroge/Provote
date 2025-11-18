"""
URLs for Polls app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, PollViewSet, TagViewSet

router = DefaultRouter()
router.register(r"polls", PollViewSet, basename="poll")
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"tags", TagViewSet, basename="tag")

urlpatterns = [
    path("", include(router.urls)),
]
