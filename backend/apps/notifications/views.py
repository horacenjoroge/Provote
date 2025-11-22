"""
Views for notifications app.
"""

from django.contrib.auth import get_user_model
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification, NotificationPreference
from .serializers import (
    NotificationMarkReadSerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer,
)
from .services import get_or_create_preferences


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for notifications."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return notifications for the authenticated user."""
        return Notification.objects.filter(user=self.request.user).select_related(
            "poll", "vote", "user"
        )

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        """Mark a notification as read."""
        notification = self.get_object()
        notification.mark_as_read()
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def mark_read_multiple(self, request):
        """Mark multiple notifications as read."""
        serializer = NotificationMarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        notification_ids = serializer.validated_data["notification_ids"]
        notifications = Notification.objects.filter(
            id__in=notification_ids, user=request.user
        )

        updated_count = 0
        for notification in notifications:
            if not notification.is_read:
                notification.mark_as_read()
                updated_count += 1

        return Response(
            {
                "message": f"Marked {updated_count} notification(s) as read",
                "updated_count": updated_count,
            }
        )

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        """Get count of unread notifications."""
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread_count": count})

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        """Mark all notifications as read."""
        updated_count = Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True)

        return Response(
            {
                "message": f"Marked {updated_count} notification(s) as read",
                "updated_count": updated_count,
            }
        )


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """ViewSet for notification preferences."""

    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return preferences for the authenticated user."""
        return NotificationPreference.objects.filter(user=self.request.user)

    def get_object(self):
        """Get or create preferences for the authenticated user."""
        from .services import get_or_create_preferences

        return get_or_create_preferences(self.request.user)

    @action(detail=False, methods=["post"])
    def unsubscribe(self, request):
        """Unsubscribe user from all notifications."""
        preferences = self.get_object()
        preferences.unsubscribe()
        serializer = self.get_serializer(preferences)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def resubscribe(self, request):
        """Resubscribe user to notifications."""
        preferences = self.get_object()
        preferences.resubscribe()
        serializer = self.get_serializer(preferences)
        return Response(serializer.data)

User = get_user_model()


@method_decorator(csrf_exempt, name="dispatch")
class UnsubscribeView(APIView):
    """View for unsubscribing via email link (no authentication required)."""

    permission_classes = []  # No authentication required

    def post(self, request):
        """Unsubscribe user by email or token."""
        email = request.data.get("email")
        _token = request.data.get("token")  # Could implement token-based unsubscribe

        if not email:
            return Response(
                {"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)
            preferences = get_or_create_preferences(user)
            preferences.unsubscribe()
            return Response(
                {"message": "Successfully unsubscribed from all notifications"}
            )
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
