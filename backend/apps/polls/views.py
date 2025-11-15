"""
Views for Polls app with comprehensive CRUD operations.
"""

import logging
from django.db import models, transaction
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Poll, PollOption
from .permissions import CanModifyPoll, IsPollOwnerOrReadOnly
from .serializers import (
    BulkPollOptionCreateSerializer,
    PollCreateSerializer,
    PollOptionSerializer,
    PollSerializer,
    PollUpdateSerializer,
)

logger = logging.getLogger(__name__)


class PollViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Poll model with comprehensive CRUD operations.
    
    Endpoints:
    - POST /api/v1/polls/ - Create poll
    - GET /api/v1/polls/ - List polls (pagination, filtering)
    - GET /api/v1/polls/{id}/ - Get poll detail
    - PATCH /api/v1/polls/{id}/ - Update poll (only creator)
    - DELETE /api/v1/polls/{id}/ - Delete poll (only creator)
    - POST /api/v1/polls/{id}/options/ - Add option(s) to poll
    - DELETE /api/v1/polls/{id}/options/{option_id}/ - Remove option
    """

    queryset = Poll.objects.all()
    serializer_class = PollSerializer
    permission_classes = [IsPollOwnerOrReadOnly, CanModifyPoll]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "starts_at", "ends_at", "cached_total_votes"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        """Return appropriate serializer class."""
        if self.action == "create":
            return PollCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return PollUpdateSerializer
        return PollSerializer

    def get_queryset(self):
        """Filter queryset based on query parameters."""
        queryset = Poll.objects.all()

        # Filter by creator
        creator = self.request.query_params.get("creator", None)
        if creator:
            queryset = queryset.filter(created_by__username=creator)

        # Filter by active status
        is_active = self.request.query_params.get("is_active", None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        # Filter by is_open (computed property, needs custom filtering)
        is_open = self.request.query_params.get("is_open", None)
        if is_open is not None:
            from django.utils import timezone

            now = timezone.now()
            if is_open.lower() == "true":
                queryset = queryset.filter(
                    is_active=True, starts_at__lte=now
                ).filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))
            else:
                queryset = queryset.filter(
                    models.Q(is_active=False)
                    | models.Q(starts_at__gt=now)
                    | models.Q(ends_at__lt=now)
                )

        return queryset

    def perform_create(self, serializer):
        """Set the created_by field to the current user."""
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        """Update poll with ownership and modification restrictions."""
        poll = self.get_object()

        # Check ownership
        if poll.created_by != request.user:
            return Response(
                {"error": "You can only update polls you created"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if poll has votes and what can be modified
        if poll.votes.exists():
            serializer = PollUpdateSerializer(poll, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

        # No votes, allow full update
        serializer = self.get_serializer(poll, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """Delete poll with ownership and vote checks."""
        poll = self.get_object()

        # Check ownership
        if poll.created_by != request.user:
            return Response(
                {"error": "You can only delete polls you created"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if poll has votes
        if poll.votes.exists():
            # Option 1: Prevent deletion
            return Response(
                {
                    "error": "Cannot delete poll with votes. Votes will be cascaded if you proceed.",
                    "vote_count": poll.votes.count(),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

            # Option 2: Allow deletion (cascade)
            # poll.delete()
            # return Response(status=status.HTTP_204_NO_CONTENT)

        # No votes, allow deletion
        poll.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="options")
    def add_options(self, request, pk=None):
        """
        Add option(s) to poll.
        
        POST /api/v1/polls/{id}/options/
        
        Request Body:
        {
            "options": [
                {"text": "Option 1", "order": 0},
                {"text": "Option 2", "order": 1}
            ]
        }
        """
        poll = self.get_object()

        # Check ownership
        if poll.created_by != request.user:
            return Response(
                {"error": "You can only add options to polls you created"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if poll has votes (might want to restrict adding options after votes)
        if poll.votes.exists():
            return Response(
                {"error": "Cannot add options to poll with existing votes"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = BulkPollOptionCreateSerializer(
            data=request.data, context={"poll": poll}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(
            PollOptionSerializer(result["options"], many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["delete"], url_path="options/(?P<option_id>[^/.]+)")
    def remove_option(self, request, pk=None, option_id=None):
        """
        Remove option from poll.
        
        DELETE /api/v1/polls/{id}/options/{option_id}/
        """
        poll = self.get_object()

        # Check ownership
        if poll.created_by != request.user:
            return Response(
                {"error": "You can only remove options from polls you created"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            option = PollOption.objects.get(id=option_id, poll=poll)
        except PollOption.DoesNotExist:
            return Response(
                {"error": f"Option {option_id} not found in poll {pk}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if option has votes
        if option.votes.exists():
            return Response(
                {
                    "error": f"Cannot delete option with {option.votes.count()} votes",
                    "vote_count": option.votes.count(),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        option.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        """Get poll results."""
        poll = self.get_object()
        options = poll.options.all()
        results = [
            {
                "option_id": option.id,
                "option_text": option.text,
                "votes": option.vote_count,
                "cached_votes": option.cached_vote_count,
            }
            for option in options
        ]
        return Response(
            {
                "poll_id": poll.id,
                "poll_title": poll.title,
                "total_votes": poll.cached_total_votes,
                "unique_voters": poll.cached_unique_voters,
                "results": results,
            }
        )
