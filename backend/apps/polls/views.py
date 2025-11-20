"""
Views for Polls app with comprehensive CRUD operations.
"""

import json
import logging
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models, transaction
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer, BaseRenderer
from rest_framework.response import Response

from core.mixins import RateLimitHeadersMixin
from core.throttles import PollCreateRateThrottle, PollReadRateThrottle
from core.services.export_service import (
    estimate_export_size,
    export_analytics_report_pdf,
    export_audit_trail,
    export_poll_results_pdf,
    export_vote_log,
)
from core.services.poll_analytics import (
    get_comprehensive_analytics,
    get_total_votes_over_time,
    get_voter_demographics,
    get_participation_rate,
)

from .models import Poll, PollOption, Category, Tag
from .permissions import CanModifyPoll, IsAdminOrPollOwner, IsPollOwnerOrReadOnly
from .services import (
    calculate_poll_results,
    can_view_results,
    clone_poll,
    export_results_to_csv,
    export_results_to_json,
)
from .serializers import (
    BulkPollOptionCreateSerializer,
    CategorySerializer,
    PollCreateSerializer,
    PollOptionSerializer,
    PollSerializer,
    PollTemplateCreateSerializer,
    PollUpdateSerializer,
    TagSerializer,
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
    search_fields = ["title", "description", "tags__name"]
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

        # Filter out drafts from public listings (unless user is owner or explicitly requesting drafts)
        user = self.request.user
        include_drafts = self.request.query_params.get("include_drafts", "false").lower() == "true"
        
        # If user is authenticated and requesting their own polls, or explicitly including drafts
        if not include_drafts:
            if user.is_authenticated:
                # Show user's own drafts, but not others' drafts
                queryset = queryset.filter(
                    models.Q(is_draft=False) | models.Q(is_draft=True, created_by=user)
                )
            else:
                # Anonymous users never see drafts
                queryset = queryset.filter(is_draft=False)

        # Filter by draft status (if explicitly requested)
        is_draft = self.request.query_params.get("is_draft", None)
        if is_draft is not None:
            queryset = queryset.filter(is_draft=is_draft.lower() == "true")

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
                    is_active=True, 
                    is_draft=False,  # Drafts are never open
                    starts_at__lte=now
                ).filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))
            else:
                queryset = queryset.filter(
                    models.Q(is_active=False)
                    | models.Q(is_draft=True)
                    | models.Q(starts_at__gt=now)
                    | models.Q(ends_at__lt=now)
                )

        # Filter by category (by slug or ID)
        category = self.request.query_params.get("category", None)
        if category:
            # Try to convert to int for ID lookup, otherwise use as slug
            try:
                category_id = int(category)
                queryset = queryset.filter(category__id=category_id)
            except ValueError:
                # Not a number, treat as slug
                queryset = queryset.filter(category__slug=category)

        # Filter by tags (comma-separated slugs or IDs)
        tags = self.request.query_params.get("tags", None)
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",")]
            # Separate IDs and slugs
            tag_ids = []
            tag_slugs = []
            for tag_val in tag_list:
                try:
                    tag_ids.append(int(tag_val))
                except ValueError:
                    tag_slugs.append(tag_val)
            
            # Build query
            tag_q = models.Q()
            if tag_ids:
                tag_q |= models.Q(tags__id__in=tag_ids)
            if tag_slugs:
                tag_q |= models.Q(tags__slug__in=tag_slugs)
            
            if tag_q:
                queryset = queryset.filter(tag_q).distinct()

        # Filter by tag search (search tag names)
        tag_search = self.request.query_params.get("tag_search", None)
        if tag_search:
            queryset = queryset.filter(tags__name__icontains=tag_search).distinct()

        return queryset

    def perform_create(self, serializer):
        """Set the created_by field to the current user."""
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        """Create a poll and return it with full nested objects."""
        response = super().create(request, *args, **kwargs)
        # Re-serialize with PollSerializer to include nested category and tags
        poll = Poll.objects.get(id=response.data["id"])
        
        # Notify followers about new poll (only if not a draft)
        if not poll.is_draft:
            try:
                from apps.users.models import Follow
                from apps.notifications.services import notify_new_poll_from_followed
                
                # Get followers of the poll creator (users who follow poll.created_by)
                follows = Follow.objects.filter(following=poll.created_by).select_related("follower")
                followers = [follow.follower for follow in follows]
                
                if followers:
                    notify_new_poll_from_followed(poll, followers)
            except Exception as e:
                logger.error(f"Error notifying followers about new poll {poll.id}: {e}")
        
        serializer = PollSerializer(poll, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Update poll with ownership and modification restrictions."""
        # Use base queryset to allow accessing drafts for permission checks
        try:
            poll = Poll.objects.get(pk=kwargs['pk'])
        except Poll.DoesNotExist:
            return Response(
                {"error": "Poll not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

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
        # Use base queryset to allow accessing drafts for permission checks
        try:
            poll = Poll.objects.get(pk=kwargs['pk'])
        except Poll.DoesNotExist:
            return Response(
                {"error": "Poll not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

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

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, pk=None):
        """
        Publish a draft poll (convert draft to active).
        
        POST /api/v1/polls/{id}/publish/
        
        This action:
        - Sets is_draft=False
        - Optionally sets is_active=True (if not already active)
        - Validates that poll has required options
        
        Returns:
        - 200 OK: Poll published successfully
        - 403 Forbidden: User not authorized
        - 400 Bad Request: Poll cannot be published (validation errors)
        """
        # Use base queryset to allow accessing drafts for permission checks
        try:
            poll = Poll.objects.get(pk=pk)
        except Poll.DoesNotExist:
            return Response(
                {"error": "Poll not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Check ownership
        if poll.created_by != request.user:
            return Response(
                {"error": "You can only publish polls you created"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Check if poll is a draft
        if not poll.is_draft:
            return Response(
                {"error": "Poll is not a draft. It is already published."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Validate poll has minimum required options
        from .serializers import MIN_OPTIONS
        option_count = poll.options.count()
        if option_count < MIN_OPTIONS:
            return Response(
                {
                    "error": f"Cannot publish poll. A poll must have at least {MIN_OPTIONS} options. "
                    f"Current options: {option_count}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Publish the poll
        poll.is_draft = False
        # If poll is not active, activate it (unless it has a future start time)
        if not poll.is_active:
            from django.utils import timezone
            if poll.starts_at <= timezone.now():
                poll.is_active = True
        poll.save(update_fields=["is_draft", "is_active"])
        
        logger.info(f"Poll {poll.id} published by user {request.user.id}")
        
        # Return updated poll data
        serializer = self.get_serializer(poll)
        return Response(
            {
                "message": "Poll published successfully",
                "poll": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request, pk=None):
        """
        Clone an existing poll with all options.
        
        POST /api/v1/polls/{id}/clone/
        
        Request Body (optional):
        {
            "clone_settings": true,  // Whether to clone settings (default: true)
            "clone_security_rules": true,  // Whether to clone security rules (default: true)
            "new_title": "Custom Title",  // Custom title (default: "Copy of {original_title}")
            "is_draft": true  // Whether cloned poll should be a draft (default: true)
        }
        
        Returns:
        - 201 Created: Cloned poll created successfully
        - 404 Not Found: Poll not found
        - 400 Bad Request: Poll cannot be cloned (e.g., no options)
        """
        try:
            poll = self.get_object()
        except Poll.DoesNotExist:
            return Response(
                {"error": "Poll not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Get optional parameters from request
        clone_settings = request.data.get("clone_settings", True)
        clone_security_rules = request.data.get("clone_security_rules", True)
        new_title = request.data.get("new_title", None)
        is_draft = request.data.get("is_draft", True)
        
        # Validate boolean parameters
        if isinstance(clone_settings, str):
            clone_settings = clone_settings.lower() == "true"
        if isinstance(clone_security_rules, str):
            clone_security_rules = clone_security_rules.lower() == "true"
        if isinstance(is_draft, str):
            is_draft = is_draft.lower() == "true"
        
        try:
            # Clone the poll
            cloned_poll = clone_poll(
                poll=poll,
                user=request.user,
                clone_settings=clone_settings,
                clone_security_rules=clone_security_rules,
                new_title=new_title,
                is_draft=is_draft,
            )
            
            logger.info(f"Poll {poll.id} cloned to poll {cloned_poll.id} by user {request.user.id}")
            
            # Return cloned poll data
            serializer = self.get_serializer(cloned_poll)
            return Response(
                {
                    "message": "Poll cloned successfully",
                    "poll": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )
            
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Error cloning poll {poll.id}: {e}", exc_info=True)
            return Response(
                {"error": "An error occurred while cloning the poll"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

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

    @action(
        detail=True,
        methods=["get"],
        url_path="export-results",
        url_name="results-export",
        permission_classes=[IsPollOwnerOrReadOnly],
        renderer_classes=[JSONRenderer, BrowsableAPIRenderer],  # Explicitly register renderers
    )
    def results_export(self, request, pk=None):
        """
        Export poll results in various formats.
        
        GET /api/v1/polls/{id}/export-results/?format=csv|json|pdf
        
        Query Parameters:
        - format: Export format (csv or json, default: json)
        
        Returns:
        - 200 OK: Exported results
        - 403 Forbidden: User not authorized to view results
        - 404 Not Found: Poll not found
        - 400 Bad Request: Invalid format
        """
        logger.info(f"results_export called: pk={pk}, format={request.query_params.get('format')}, path={request.path}")
        try:
            poll = self.get_object()
        except Exception as e:
            logger.error(f"Error getting poll {pk}: {e}")
            raise
        
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
        # Use 'export_format' to avoid DRF's special 'format' parameter for content negotiation
        # Fall back to 'format' for backward compatibility
        export_format = request.query_params.get("export_format") or request.query_params.get("format", "json")
        export_format = export_format.lower()
        use_background = request.query_params.get("background", "false").lower() == "true"
        
        # Check if export is large enough for background processing
        estimated_size = estimate_export_size(poll.id, "results")
        large_export_threshold = getattr(settings, "LARGE_EXPORT_THRESHOLD", 1024 * 1024)  # 1MB default
        
        if use_background or estimated_size > large_export_threshold:
            # Use background task
            if not request.user.is_authenticated or not request.user.email:
                return Response(
                    {"error": "Email required for background export"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            from apps.polls.tasks import export_poll_data_task
            export_poll_data_task.delay(
                poll_id=poll.id,
                export_type="results",
                format=export_format,
                user_email=request.user.email,
            )
            
            return Response(
                {
                    "message": "Export started. You will receive an email when it's ready.",
                    "poll_id": poll.id,
                    "format": export_format,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        
        # Handle immediate export
        if export_format == "csv":
            from core.services.export_service import export_poll_results_csv
            from django.http import HttpResponse
            
            csv_content = export_poll_results_csv(poll.id)
            response = HttpResponse(csv_content, content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="poll_{poll.id}_results.csv"'
            return response
            
        elif export_format == "json":
            from core.services.export_service import export_poll_results_json
            json_data = export_poll_results_json(poll.id)
            return Response(json_data, status=status.HTTP_200_OK)
        
        elif export_format == "pdf":
            pdf_buffer = export_poll_results_pdf(poll.id)
            from django.http import HttpResponse
            
            response = HttpResponse(pdf_buffer.getvalue(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="poll_{poll.id}_results.pdf"'
            return response
            
        else:
            return Response(
                {"error": f"Invalid format '{export_format}'. Supported formats: csv, json, pdf"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["get"], url_path="results", renderer_classes=[JSONRenderer, BrowsableAPIRenderer])
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

    @action(detail=True, methods=["get"], url_path="export-vote-log")
    def export_vote_log(self, request, pk=None):
        """
        Export vote log for a poll.
        
        GET /api/v1/polls/{id}/export-vote-log/?format=csv|json&anonymize=true&include_invalid=false
        
        Query Parameters:
        - format: Export format (csv or json, default: csv)
        - anonymize: Whether to anonymize user data (default: false)
        - include_invalid: Whether to include invalid votes (default: false)
        - background: Use background task for large exports (default: false)
        
        Returns:
        - 200 OK: Exported vote log
        - 202 Accepted: Export started in background
        - 403 Forbidden: User not authorized
        - 404 Not Found: Poll not found
        """
        poll = self.get_object()
        
        # Check permissions (poll owner or admin)
        if not IsAdminOrPollOwner().has_object_permission(request, self, poll):
            return Response(
                {"error": "You do not have permission to export vote log for this poll"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Use 'export_format' to avoid DRF's special 'format' parameter for content negotiation
        export_format = request.query_params.get("export_format") or request.query_params.get("format", "csv")
        export_format = export_format.lower()
        anonymize = request.query_params.get("anonymize", "false").lower() == "true"
        include_invalid = request.query_params.get("include_invalid", "false").lower() == "true"
        use_background = request.query_params.get("background", "false").lower() == "true"
        
        # Check if export is large enough for background processing
        estimated_size = estimate_export_size(poll.id, "vote_log")
        large_export_threshold = getattr(settings, "LARGE_EXPORT_THRESHOLD", 1024 * 1024)
        
        if use_background or estimated_size > large_export_threshold:
            if not request.user.is_authenticated or not request.user.email:
                return Response(
                    {"error": "Email address required for background exports"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            from apps.polls.tasks import export_poll_data_task
            
            task = export_poll_data_task.delay(
                poll_id=poll.id,
                export_type="vote_log",
                format=export_format,
                user_email=request.user.email,
                anonymize=anonymize,
                include_invalid=include_invalid,
            )
            
            return Response(
                {
                    "message": "Export started in background. You will receive an email when ready.",
                    "task_id": task.id,
                    "estimated_size_bytes": estimated_size,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        
        # Immediate export
        try:
            content = export_vote_log(
                poll_id=poll.id,
                format=export_format,
                anonymize=anonymize,
                include_invalid=include_invalid
            )
            
            if export_format == "csv":
                from django.http import HttpResponse
                response = HttpResponse(content, content_type="text/csv")
                response["Content-Disposition"] = f'attachment; filename="poll_{poll.id}_vote_log.csv"'
                return response
            else:
                return Response(json.loads(content), status=status.HTTP_200_OK)
                
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=["get"], url_path="export-analytics")
    def export_analytics(self, request, pk=None):
        """
        Export analytics report as PDF.
        
        GET /api/v1/polls/{id}/export-analytics/?background=false
        
        Query Parameters:
        - background: Use background task (default: false)
        
        Returns:
        - 200 OK: PDF analytics report
        - 202 Accepted: Export started in background
        - 403 Forbidden: User not authorized
        - 404 Not Found: Poll not found
        """
        poll = self.get_object()
        
        # Check permissions
        if not IsAdminOrPollOwner().has_object_permission(request, self, poll):
            return Response(
                {"error": "You do not have permission to export analytics for this poll"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        use_background = request.query_params.get("background", "false").lower() == "true"
        
        if use_background:
            if not request.user.is_authenticated or not request.user.email:
                return Response(
                    {"error": "Email address required for background exports"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            from apps.polls.tasks import export_poll_data_task
            
            task = export_poll_data_task.delay(
                poll_id=poll.id,
                export_type="analytics",
                format="pdf",
                user_email=request.user.email,
            )
            
            return Response(
                {
                    "message": "Export started in background. You will receive an email when ready.",
                    "task_id": task.id,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        
        # Immediate export
        try:
            pdf_buffer = export_analytics_report_pdf(poll.id)
            from django.http import HttpResponse
            
            response = HttpResponse(pdf_buffer.getvalue(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="poll_{poll.id}_analytics.pdf"'
            return response
            
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ImportError as e:
            return Response(
                {"error": f"PDF export requires reportlab: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @action(detail=True, methods=["get"], url_path="export-audit-trail")
    def export_audit_trail(self, request, pk=None):
        """
        Export audit trail for a poll.
        
        GET /api/v1/polls/{id}/export-audit-trail/?format=csv|json&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
        
        Query Parameters:
        - format: Export format (csv or json, default: csv)
        - start_date: Start date filter (ISO format)
        - end_date: End date filter (ISO format)
        - background: Use background task (default: false)
        
        Returns:
        - 200 OK: Exported audit trail
        - 202 Accepted: Export started in background
        - 403 Forbidden: User not authorized (admin only)
        - 404 Not Found: Poll not found
        """
        from datetime import datetime
        from rest_framework.permissions import IsAdminUser
        
        poll = self.get_object()
        
        # Check permissions (admin only for audit trail)
        if not IsAdminUser().has_permission(request, self):
            return Response(
                {"error": "Only administrators can export audit trails"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Use 'export_format' to avoid DRF's special 'format' parameter for content negotiation
        export_format = request.query_params.get("export_format") or request.query_params.get("format", "csv")
        export_format = export_format.lower()
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        use_background = request.query_params.get("background", "false").lower() == "true"
        
        start_date = None
        end_date = None
        
        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
            except ValueError:
                return Response(
                    {"error": "Invalid start_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            except ValueError:
                return Response(
                    {"error": "Invalid end_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        
        if use_background:
            if not request.user.is_authenticated or not request.user.email:
                return Response(
                    {"error": "Email address required for background exports"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            from apps.polls.tasks import export_poll_data_task
            
            task = export_poll_data_task.delay(
                poll_id=poll.id,
                export_type="audit",
                format=export_format,
                user_email=request.user.email,
                start_date=start_date.isoformat() if start_date else None,
                end_date=end_date.isoformat() if end_date else None,
            )
            
            return Response(
                {
                    "message": "Export started in background. You will receive an email when ready.",
                    "task_id": task.id,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        
        # Immediate export
        try:
            content = export_audit_trail(
                poll_id=poll.id,
                format=export_format,
                start_date=start_date,
                end_date=end_date
            )
            
            if export_format == "csv":
                from django.http import HttpResponse
                response = HttpResponse(content, content_type="text/csv")
                response["Content-Disposition"] = f'attachment; filename="poll_{poll.id}_audit_trail.csv"'
                return response
            else:
                return Response(json.loads(content), status=status.HTTP_200_OK)
                
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

    @action(
        detail=True,
        methods=["get"],
        url_path="analytics",
        permission_classes=[IsAdminOrPollOwner],
    )
    def analytics(self, request, pk=None):
        """
        Get overview analytics for a poll.
        
        GET /api/v1/polls/{id}/analytics/
        
        Returns comprehensive analytics including:
        - Total votes and unique voters
        - Time series data
        - Demographics
        - Participation metrics
        - Vote distribution
        - Drop-off rates
        
        Access: Admin or poll owner only
        """
        poll = self.get_object()
        
        # Check permissions
        if not IsAdminOrPollOwner().has_object_permission(request, self, poll):
            return Response(
                {"error": "You do not have permission to view analytics for this poll"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Check cache
        from django.core.cache import cache
        cache_key = f"poll_analytics:{poll.id}"
        cached_analytics = cache.get(cache_key)
        
        if cached_analytics:
            return Response(cached_analytics, status=status.HTTP_200_OK)
        
        # Generate analytics
        analytics = get_comprehensive_analytics(poll.id)
        
        if "error" in analytics:
            return Response(analytics, status=status.HTTP_404_NOT_FOUND)
        
        # Cache for 5 minutes
        cache.set(cache_key, analytics, 300)
        
        return Response(analytics, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["get"],
        url_path="analytics/timeseries",
        permission_classes=[IsAdminOrPollOwner],
    )
    def analytics_timeseries(self, request, pk=None):
        """
        Get votes over time (time series data).
        
        GET /api/v1/polls/{id}/analytics/timeseries/?interval=hour|day&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
        
        Query Parameters:
        - interval: 'hour' or 'day' (default: 'hour')
        - start_date: Start date in ISO format (optional)
        - end_date: End date in ISO format (optional)
        
        Access: Admin or poll owner only
        """
        poll = self.get_object()
        
        # Check permissions
        if not IsAdminOrPollOwner().has_object_permission(request, self, poll):
            return Response(
                {"error": "You do not have permission to view analytics for this poll"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Parse query parameters
        interval = request.query_params.get("interval", "hour")
        if interval not in ["hour", "day"]:
            interval = "hour"
        
        start_date = None
        end_date = None
        
        start_date_str = request.query_params.get("start_date")
        if start_date_str:
            try:
                from datetime import datetime
                start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
            except ValueError:
                return Response(
                    {"error": "Invalid start_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        
        end_date_str = request.query_params.get("end_date")
        if end_date_str:
            try:
                from datetime import datetime
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            except ValueError:
                return Response(
                    {"error": "Invalid end_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        
        # Check cache
        from django.core.cache import cache
        cache_key = f"poll_timeseries:{poll.id}:{interval}:{start_date_str}:{end_date_str}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)
        
        # Generate time series
        time_series = get_total_votes_over_time(
            poll.id,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
        )
        
        response_data = {
            "poll_id": poll.id,
            "poll_title": poll.title,
            "interval": interval,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "data": time_series,
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, response_data, 300)
        
        return Response(response_data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["get"],
        url_path="analytics/demographics",
        permission_classes=[IsAdminOrPollOwner],
    )
    def analytics_demographics(self, request, pk=None):
        """
        Get voter demographics breakdown.
        
        GET /api/v1/polls/{id}/analytics/demographics/
        
        Returns:
        - Authenticated vs anonymous voters
        - Unique IP addresses
        - Top user agents
        
        Access: Admin or poll owner only
        """
        poll = self.get_object()
        
        # Check permissions
        if not IsAdminOrPollOwner().has_object_permission(request, self, poll):
            return Response(
                {"error": "You do not have permission to view analytics for this poll"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Check cache
        from django.core.cache import cache
        cache_key = f"poll_demographics:{poll.id}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)
        
        # Generate demographics
        demographics = get_voter_demographics(poll.id)
        
        response_data = {
            "poll_id": poll.id,
            "poll_title": poll.title,
            **demographics,
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, response_data, 300)
        
        return Response(response_data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["get"],
        url_path="analytics/participation",
        permission_classes=[IsAdminOrPollOwner],
    )
    def analytics_participation(self, request, pk=None):
        """
        Get participation metrics.
        
        GET /api/v1/polls/{id}/analytics/participation/
        
        Returns:
        - Participation rate (if view tracking available)
        - Unique voters
        - Total votes
        - Average time to vote
        - Drop-off rate
        
        Access: Admin or poll owner only
        """
        poll = self.get_object()
        
        # Check permissions
        if not IsAdminOrPollOwner().has_object_permission(request, self, poll):
            return Response(
                {"error": "You do not have permission to view analytics for this poll"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Check cache
        from django.core.cache import cache
        cache_key = f"poll_participation:{poll.id}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)
        
        # Generate participation metrics
        from core.services.poll_analytics import (
            get_average_time_to_vote,
            get_drop_off_rate,
        )
        
        participation = get_participation_rate(poll.id)
        avg_time = get_average_time_to_vote(poll.id)
        drop_off = get_drop_off_rate(poll.id)
        
        response_data = {
            "poll_id": poll.id,
            "poll_title": poll.title,
            "participation_rate": participation.get("participation_rate"),
            "unique_voters": participation.get("unique_voters", 0),
            "total_votes": participation.get("total_votes", 0),
            "average_time_to_vote_seconds": avg_time,
            "drop_off_rate": drop_off.get("drop_off_rate"),
            "drop_off_details": drop_off,
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, response_data, 300)
        
        return Response(response_data, status=status.HTTP_200_OK)


class CategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for Category model."""

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    @action(detail=True, methods=["get"])
    def polls(self, request, pk=None):
        """Get all polls in this category."""
        category = self.get_object()
        user = request.user
        polls = category.polls.all()

        # Filter out drafts from public listings
        if not user.is_authenticated:
            polls = polls.filter(is_draft=False)
        elif not request.query_params.get("include_drafts", "false").lower() == "true":
            polls = polls.filter(
                models.Q(is_draft=False) | models.Q(is_draft=True, created_by=user)
            )

        serializer = PollSerializer(polls, many=True, context={"request": request})
        return Response(serializer.data)


class TagViewSet(viewsets.ModelViewSet):
    """ViewSet for Tag model."""

    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    @action(detail=True, methods=["get"])
    def polls(self, request, pk=None):
        """Get all polls with this tag."""
        tag = self.get_object()
        user = request.user
        polls = tag.polls.all()

        # Filter out drafts from public listings
        if not user.is_authenticated:
            polls = polls.filter(is_draft=False)
        elif not request.query_params.get("include_drafts", "false").lower() == "true":
            polls = polls.filter(
                models.Q(is_draft=False) | models.Q(is_draft=True, created_by=user)
            )

        serializer = PollSerializer(polls, many=True, context={"request": request})
        return Response(serializer.data)
