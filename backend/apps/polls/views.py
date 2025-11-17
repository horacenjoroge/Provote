"""
Views for Polls app with comprehensive CRUD operations.
"""

import logging
from django.db import models, transaction
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.mixins import RateLimitHeadersMixin
from core.throttles import PollCreateRateThrottle, PollReadRateThrottle

from .models import Poll, PollOption
from .permissions import CanModifyPoll, IsPollOwnerOrReadOnly
from .services import (
    calculate_poll_results,
    can_view_results,
    export_results_to_csv,
    export_results_to_json,
)
from .serializers import (
    BulkPollOptionCreateSerializer,
    PollCreateSerializer,
    PollOptionSerializer,
    PollSerializer,
    PollTemplateCreateSerializer,
    PollUpdateSerializer,
)
from .templates import get_template, list_templates

logger = logging.getLogger(__name__)


class PollViewSet(RateLimitHeadersMixin, viewsets.ModelViewSet):
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
    
    def get_throttles(self):
        """Return throttles based on action."""
        if self.action == "create":
            return [PollCreateRateThrottle()]
        elif self.action in ["list", "retrieve"]:
            return [PollReadRateThrottle()]
        return []

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

        # Check if poll has votes and option modification is not allowed
        # This is also validated in serializer, but we check here for early return
        has_votes = poll.votes.exists()
        allow_option_modification = poll.settings.get("allow_option_modification_after_votes", False)

        if has_votes and not allow_option_modification:
            return Response(
                {
                    "error": "Cannot add options to poll with existing votes. "
                    "Set 'allow_option_modification_after_votes' to true in poll settings to allow."
                },
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
        """
        Get poll results with comprehensive calculations.
        
        GET /api/v1/polls/{id}/results/
        
        Visibility Rules:
        - Private polls: Only owner can view results
        - Public polls: Anyone can view (if allowed by timing)
        - show_results_during_voting=False: Results only shown after poll closes
        - show_results_during_voting=True: Results shown anytime
        
        Returns:
        - 200 OK: Poll results with vote counts, percentages, winners, statistics
        - 403 Forbidden: User not authorized to view results
        - 404 Not Found: Poll not found
        """
        poll = self.get_object()
        
        # Check visibility rules
        if not can_view_results(poll, request.user):
            return Response(
                {
                    "error": "You are not authorized to view results for this poll",
                    "reason": "Results are private or poll is still open",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Use results calculation service
        try:
            results = calculate_poll_results(poll.id, use_cache=True)
            return Response(results, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=["get"], url_path="results/live")
    def results_live(self, request, pk=None):
        """
        Get live poll results (for polling/SSE, not WebSocket).
        
        GET /api/v1/polls/{id}/results/live/
        
        This endpoint is designed for client-side polling to get real-time updates.
        For true WebSocket support, you would need Django Channels.
        
        Query Parameters:
        - last_update: ISO timestamp of last known update (optional)
        
        Returns:
        - 200 OK: Poll results with has_updates flag
        - 403 Forbidden: User not authorized to view results
        - 404 Not Found: Poll not found
        """
        poll = self.get_object()
        
        # Check visibility rules
        if not can_view_results(poll, request.user):
            return Response(
                {
                    "error": "You are not authorized to view results for this poll",
                    "reason": "Results are private or poll is still open",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Get last update timestamp from query params
        last_update = request.query_params.get("last_update", None)
        
        try:
            results = calculate_poll_results(poll.id, use_cache=False)  # Don't use cache for live updates
            
            # Check if results have changed since last_update
            has_updates = True
            if last_update:
                try:
                    from django.utils.dateparse import parse_datetime
                    last_update_dt = parse_datetime(last_update)
                    calculated_dt = parse_datetime(results["calculated_at"])
                    if last_update_dt and calculated_dt:
                        has_updates = calculated_dt > last_update_dt
                except (ValueError, TypeError):
                    has_updates = True
            
            response_data = {
                **results,
                "has_updates": has_updates,
                "poll_status": {
                    "is_open": poll.is_open,
                    "is_active": poll.is_active,
                    "ends_at": poll.ends_at.isoformat() if poll.ends_at else None,
                },
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=["get"], url_path="results/export")
    def results_export(self, request, pk=None):
        """
        Export poll results in various formats.
        
        GET /api/v1/polls/{id}/results/export/?format=csv|json
        
        Query Parameters:
        - format: Export format (csv or json, default: json)
        
        Returns:
        - 200 OK: Exported results
        - 403 Forbidden: User not authorized to view results
        - 404 Not Found: Poll not found
        - 400 Bad Request: Invalid format
        """
        poll = self.get_object()
        
        # Check visibility rules
        if not can_view_results(poll, request.user):
            return Response(
                {
                    "error": "You are not authorized to view results for this poll",
                    "reason": "Results are private or poll is still open",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Get format from query params
        export_format = request.query_params.get("format", "json").lower()
        
        try:
            if export_format == "csv":
                csv_content = export_results_to_csv(poll.id)
                from django.http import HttpResponse
                
                response = HttpResponse(csv_content, content_type="text/csv")
                response["Content-Disposition"] = f'attachment; filename="poll_{poll.id}_results.csv"'
                return response
                
            elif export_format == "json":
                json_data = export_results_to_json(poll.id)
                return Response(json_data, status=status.HTTP_200_OK)
                
            else:
                return Response(
                    {"error": f"Invalid format '{export_format}'. Supported formats: csv, json"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
                
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=False, methods=["get"], url_path="templates")
    def list_templates(self, request):
        """
        List all available poll templates.
        
        GET /api/v1/polls/templates/
        """
        templates = list_templates()
        return Response(templates, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="templates/(?P<template_id>[^/.]+)")
    def get_template(self, request, template_id=None):
        """
        Get specific poll template details.
        
        GET /api/v1/polls/templates/{template_id}/
        """
        template = get_template(template_id)
        if not template:
            return Response(
                {"error": f"Template '{template_id}' not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "id": template_id,
                "name": template["name"],
                "description": template["description"],
                "default_options": template["default_options"],
                "settings": template["settings"],
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="from-template")
    def create_from_template(self, request):
        """
        Create a poll from a template.
        
        POST /api/v1/polls/from-template/
        
        Request Body:
        {
            "template_id": "yes_no",
            "title": "Do you like pizza?",
            "description": "Optional description",
            "custom_options": [{"text": "Yes"}, {"text": "No"}],  # Optional
            "custom_settings": {"show_results": false},  # Optional
            "starts_at": "2024-01-01T00:00:00Z",  # Optional
            "ends_at": "2024-01-31T23:59:59Z",  # Optional
            "is_active": true  # Optional
        }
        """
        serializer = PollTemplateCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        poll = serializer.save()

        return Response(
            PollSerializer(poll).data,
            status=status.HTTP_201_CREATED,
        )
