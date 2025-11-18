"""
Views for Users app.
"""

from django.contrib.auth.models import User
from django.db import IntegrityError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Follow
from .serializers import FollowSerializer, UserSerializer


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for User model."""

    queryset = User.objects.all()
    serializer_class = UserSerializer

    @action(detail=True, methods=["get"])
    def followers(self, request, pk=None):
        """Get list of users following this user."""
        user = self.get_object()
        follows = Follow.objects.filter(following=user).select_related("follower")
        serializer = FollowSerializer(follows, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def following(self, request, pk=None):
        """Get list of users this user is following."""
        user = self.get_object()
        follows = Follow.objects.filter(follower=user).select_related("following")
        serializer = FollowSerializer(follows, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def follow(self, request, pk=None):
        """Follow a user."""
        user_to_follow = self.get_object()

        if user_to_follow == request.user:
            return Response(
                {"error": "You cannot follow yourself."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            follow, created = Follow.objects.get_or_create(
                follower=request.user, following=user_to_follow
            )
            if created:
                serializer = FollowSerializer(follow, context={"request": request})
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response(
                    {"message": "You are already following this user."},
                    status=status.HTTP_200_OK,
                )
        except IntegrityError:
            return Response(
                {"error": "You are already following this user."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def unfollow(self, request, pk=None):
        """Unfollow a user."""
        user_to_unfollow = self.get_object()

        try:
            follow = Follow.objects.get(follower=request.user, following=user_to_unfollow)
            follow.delete()
            return Response(
                {"message": "Successfully unfollowed user."},
                status=status.HTTP_200_OK,
            )
        except Follow.DoesNotExist:
            return Response(
                {"error": "You are not following this user."},
                status=status.HTTP_404_NOT_FOUND,
            )


class FollowViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Follow model."""

    serializer_class = FollowSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return follows for the authenticated user."""
        # By default, show who the user is following
        return Follow.objects.filter(follower=self.request.user).select_related(
            "follower", "following"
        )

    @action(detail=False, methods=["get"])
    def my_followers(self, request):
        """Get list of users following the current user."""
        follows = Follow.objects.filter(following=request.user).select_related("follower")
        serializer = self.get_serializer(follows, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def my_following(self, request):
        """Get list of users the current user is following."""
        follows = Follow.objects.filter(follower=request.user).select_related("following")
        serializer = self.get_serializer(follows, many=True)
        return Response(serializer.data)
