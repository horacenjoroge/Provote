"""
User models for Provote.
"""

from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """Extended user profile."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile for {self.user.username}"
