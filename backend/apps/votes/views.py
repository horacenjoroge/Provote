"""
Views for Votes app.
"""

from core.exceptions import (
    DuplicateVoteError,
    InvalidVoteError,
    PollClosedError,
    PollNotFoundError,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Vote
from .serializers import VoteCreateSerializer, VoteSerializer
from .services import create_vote


class VoteViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Vote model."""

    queryset = Vote.objects.all()
    serializer_class = VoteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter votes by current user."""
        return Vote.objects.filter(user=self.request.user)

    @action(detail=False, methods=["post"])
    def create_vote(self, request):
        """Create a new vote with idempotency support."""
        serializer = VoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            vote = create_vote(
                user=request.user,
                poll_id=serializer.validated_data["poll_id"],
                choice_id=serializer.validated_data["choice_id"],
                idempotency_key=serializer.validated_data.get("idempotency_key"),
            )
            return Response(
                VoteSerializer(vote).data,
                status=status.HTTP_201_CREATED,
            )
        except PollNotFoundError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except (InvalidVoteError, PollClosedError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DuplicateVoteError as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)
