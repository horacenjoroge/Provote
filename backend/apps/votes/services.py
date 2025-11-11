"""
Vote services with idempotency logic.
"""

from apps.polls.models import Choice, Poll
from apps.votes.models import Vote
from core.exceptions import (
    DuplicateVoteError,
    InvalidVoteError,
    PollClosedError,
    PollNotFoundError,
)
from core.utils.idempotency import (
    check_idempotency,
    generate_idempotency_key,
    store_idempotency_result,
)
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction


def create_vote(user: User, poll_id: int, choice_id: int, idempotency_key: str = None):
    """
    Create a vote with idempotency support.

    Args:
        user: The user making the vote
        poll_id: The ID of the poll
        choice_id: The ID of the choice
        idempotency_key: Optional idempotency key. If not provided, one will be generated.

    Returns:
        Vote: The created or existing vote

    Raises:
        PollNotFoundError: If the poll doesn't exist
        InvalidVoteError: If the choice doesn't belong to the poll
        PollClosedError: If the poll is closed
        DuplicateVoteError: If the user has already voted on this poll
    """
    # Get poll
    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        raise PollNotFoundError(f"Poll with id {poll_id} not found")

    # Check if poll is open
    if not poll.is_open:
        raise PollClosedError(f"Poll {poll_id} is closed")

    # Get choice and verify it belongs to poll
    try:
        choice = Choice.objects.get(id=choice_id, poll=poll)
    except Choice.DoesNotExist:
        raise InvalidVoteError(f"Choice {choice_id} does not belong to poll {poll_id}")

    # Generate idempotency key if not provided
    if not idempotency_key:
        idempotency_key = generate_idempotency_key(user.id, poll_id, choice_id)

    # Check idempotency
    is_duplicate, cached_result = check_idempotency(idempotency_key)
    if is_duplicate and cached_result:
        # Return the cached vote
        try:
            return Vote.objects.get(id=cached_result["vote_id"])
        except Vote.DoesNotExist:
            pass

    # Check if user has already voted on this poll
    existing_vote = Vote.objects.filter(user=user, poll=poll).first()
    if existing_vote:
        # Store result for idempotency
        store_idempotency_result(
            idempotency_key,
            {"vote_id": existing_vote.id, "status": "duplicate"},
        )
        raise DuplicateVoteError(
            f"User {user.username} has already voted on poll {poll_id}"
        )

    # Create vote
    with transaction.atomic():
        vote = Vote.objects.create(
            user=user,
            choice=choice,
            poll=poll,
            idempotency_key=idempotency_key,
        )

        # Store result for idempotency
        store_idempotency_result(
            idempotency_key,
            {"vote_id": vote.id, "status": "created"},
        )

    return vote
