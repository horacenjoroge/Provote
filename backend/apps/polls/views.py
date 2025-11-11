"""
Views for Polls app.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Poll, Choice
from .serializers import PollSerializer, PollCreateSerializer


class PollViewSet(viewsets.ModelViewSet):
    """ViewSet for Poll model."""

    queryset = Poll.objects.all()
    serializer_class = PollSerializer

    def get_serializer_class(self):
        """Return appropriate serializer class."""
        if self.action == "create":
            return PollCreateSerializer
        return PollSerializer

    def perform_create(self, serializer):
        """Set the created_by field to the current user."""
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        """Get poll results."""
        poll = self.get_object()
        choices = poll.choices.all()
        results = [
            {
                "choice_id": choice.id,
                "choice_text": choice.text,
                "votes": choice.vote_count,
            }
            for choice in choices
        ]
        return Response(
            {"poll_id": poll.id, "poll_title": poll.title, "results": results}
        )
