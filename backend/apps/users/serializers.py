"""
Serializers for Users app.
"""

from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Follow


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""

    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    is_followed_by = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "date_joined",
            "followers_count",
            "following_count",
            "is_following",
            "is_followed_by",
        ]

    def get_followers_count(self, obj):
        """Get number of followers."""
        return obj.followers.count()

    def get_following_count(self, obj):
        """Get number of users being followed."""
        return obj.following.count()

    def get_is_following(self, obj):
        """Check if current user is following this user."""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return Follow.objects.filter(follower=request.user, following=obj).exists()
        return False

    def get_is_followed_by(self, obj):
        """Check if this user is following the current user."""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return Follow.objects.filter(follower=obj, following=request.user).exists()
        return False


class FollowSerializer(serializers.ModelSerializer):
    """Serializer for Follow model."""

    follower_username = serializers.CharField(source="follower.username", read_only=True)
    following_username = serializers.CharField(source="following.username", read_only=True)

    class Meta:
        model = Follow
        fields = ["id", "follower", "follower_username", "following", "following_username", "created_at"]
        read_only_fields = ["id", "follower_username", "following_username", "created_at"]
