"""
Views for Votes app with comprehensive API endpoints.
"""

import logging

from core.exceptions import (
    CaptchaVerificationError,
    DuplicateVoteError,
    FraudDetectedError,
    InvalidPollError,
    InvalidVoteError,
    PollClosedError,
    PollNotFoundError,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.mixins import RateLimitHeadersMixin
from core.throttles import VoteCastRateThrottle

from .models import Vote
from .permissions import CanVotePermission
from .serializers import VoteCastSerializer, VoteSerializer
from .services import cast_vote

logger = logging.getLogger(__name__)


class VoteViewSet(RateLimitHeadersMixin, viewsets.ModelViewSet):
    """
    ViewSet for Vote model with comprehensive API endpoints.
    
    Endpoints:
    - POST /api/v1/votes/cast/ - Cast a vote
    - GET /api/v1/votes/my-votes/ - Get current user's votes
    - DELETE /api/v1/votes/{id}/ - Retract vote (if allowed)
    """

    queryset = Vote.objects.all()
    serializer_class = VoteSerializer
    permission_classes = [CanVotePermission]
    
    def get_throttles(self):
        """Return throttles based on action."""
        if self.action == "cast":
            return [VoteCastRateThrottle()]
        return []

    def get_queryset(self):
        """Filter votes by current user if authenticated."""
        if self.request.user and self.request.user.is_authenticated:
            return Vote.objects.filter(user=self.request.user)
        return Vote.objects.none()

    @action(detail=False, methods=["post"], url_path="cast")
    def cast(self, request):
        """
        Cast a vote on a poll.
        
        POST /api/v1/votes/cast/
        
        Request Body:
        {
            "poll_id": 1,
            "choice_id": 2,
            "idempotency_key": "optional-key"
        }
        
        Returns:
        - 201 Created: New vote created
        - 200 OK: Idempotent retry (same vote returned)
        - 400 Bad Request: Invalid request or poll closed
        - 404 Not Found: Poll not found
        - 409 Conflict: Duplicate vote
        - 429 Too Many Requests: Rate limit exceeded
        """
        serializer = VoteCastSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        poll_id = serializer.validated_data["poll_id"]
        choice_id = serializer.validated_data["choice_id"]
        idempotency_key = serializer.validated_data.get("idempotency_key")
        captcha_token = serializer.validated_data.get("captcha_token")

        # Check if user is authenticated
        user = request.user if request.user.is_authenticated else None
        
        # Attach captcha_token to request for service layer
        if captcha_token:
            request.captcha_token = captcha_token

        # For anonymous users, we need to handle this differently
        # Since cast_vote requires a user, we'll need to create an anonymous user
        # or modify the service. For now, require authentication for voting.
        if not user:
            # Check if poll allows anonymous voting
            from apps.polls.models import Poll

            try:
                poll = Poll.objects.get(id=poll_id)
                # If poll requires authentication, reject
                if poll.security_rules.get("require_authentication", False):
                    return Response(
                        {"error": "This poll requires authentication"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
                # For now, we require authentication for voting
                # TODO: Support anonymous voting with voter tokens
                return Response(
                    {"error": "Authentication required to vote"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            except Poll.DoesNotExist:
                pass

        try:
            vote, is_new = cast_vote(
                user=user,
                poll_id=poll_id,
                choice_id=choice_id,
                idempotency_key=idempotency_key,
                request=request,
            )

            # Return appropriate status code based on whether vote is new
            if is_new:
                return Response(
                    VoteSerializer(vote).data,
                    status=status.HTTP_201_CREATED,
                )
            else:
                # Idempotent retry - return existing vote with 200 OK
                return Response(
                    VoteSerializer(vote).data,
                    status=status.HTTP_200_OK,
                )

        except PollNotFoundError as e:
            return Response(
                {"error": str(e), "error_code": "PollNotFoundError"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except InvalidPollError as e:
            return Response(
                {"error": str(e), "error_code": "InvalidPollError"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except PollClosedError as e:
            return Response(
                {"error": str(e), "error_code": "PollClosedError"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except InvalidVoteError as e:
            return Response(
                {"error": str(e), "error_code": "InvalidVoteError"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DuplicateVoteError as e:
            return Response(
                {"error": str(e), "error_code": "DuplicateVoteError"},
                status=status.HTTP_409_CONFLICT,
            )
        except FraudDetectedError as e:
            return Response(
                {"error": str(e), "error_code": "FraudDetectedError"},
                status=status.HTTP_403_FORBIDDEN,
            )
        except CaptchaVerificationError as e:
            return Response(
                {"error": str(e), "error_code": "CaptchaVerificationError"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Unexpected error in cast_vote: {e}", exc_info=True)
            return Response(
                {"error": "An internal server error occurred", "error_code": "InternalServerError"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="my-votes")
    def my_votes(self, request):
        """
        Get current user's votes.
        
        GET /api/v1/votes/my-votes/
        
        Returns:
        - 200 OK: List of user's votes
        - 401 Unauthorized: User not authenticated
        """
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        votes = self.get_queryset()
        serializer = self.get_serializer(votes, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """
        Retract a vote (if allowed).
        
        DELETE /api/v1/votes/{id}/
        
        Returns:
        - 204 No Content: Vote retracted successfully
        - 403 Forbidden: Cannot retract vote (not owner or poll doesn't allow)
        - 404 Not Found: Vote not found
        """
        vote = self.get_object()

        # Check if user owns the vote
        if vote.user != request.user:
            return Response(
                {"error": "You can only retract your own votes"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if poll allows vote retraction
        poll = vote.poll
        if not poll.settings.get("allow_vote_retraction", False):
            return Response(
                {"error": "This poll does not allow vote retraction"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if poll is still open
        if not poll.is_open:
            return Response(
                {"error": "Cannot retract vote from closed poll"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Delete the vote
        vote_id = vote.id
        vote.delete()

        # Update cached counts
        from django.db.models import F
        from apps.polls.models import Poll, PollOption

        PollOption.objects.filter(id=vote.option.id).update(
            cached_vote_count=F("cached_vote_count") - 1
        )
        Poll.objects.filter(id=poll.id).update(
            cached_total_votes=F("cached_total_votes") - 1
        )

        logger.info(f"Vote {vote_id} retracted by user {request.user.id}")

        return Response(status=status.HTTP_204_NO_CONTENT)
