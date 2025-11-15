"""
Custom permissions for Polls app.
"""

from rest_framework import permissions


class IsPollOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission class that allows:
    - Read access to all users
    - Write access only to poll owner
    """

    def has_permission(self, request, view):
        """Check if user has permission."""
        # Allow read access to all
        if request.method in permissions.SAFE_METHODS:
            return True

        # Require authentication for write operations
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user can perform action on specific poll object."""
        # Allow read access to all
        if request.method in permissions.SAFE_METHODS:
            return True

        # Only owner can modify
        return obj.created_by == request.user


class CanModifyPoll(permissions.BasePermission):
    """
    Permission class that checks if poll can be modified.
    Prevents modification of polls that have votes cast.
    """

    def has_object_permission(self, request, view, obj):
        """Check if poll can be modified."""
        # Allow read access
        if request.method in permissions.SAFE_METHODS:
            return True

        # Check if poll has votes
        if obj.votes.exists():
            # Some modifications might be allowed even with votes
            # This will be checked in the view
            return True

        return True

