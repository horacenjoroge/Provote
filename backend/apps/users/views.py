"""
Views for Users app.
"""

from rest_framework import viewsets
from django.contrib.auth.models import User
from .serializers import UserSerializer


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for User model."""

    queryset = User.objects.all()
    serializer_class = UserSerializer
