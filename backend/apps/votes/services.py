"""
Vote services with idempotency and fingerprint validation logic.
"""

import logging

from apps.polls.models import Choice, Poll
from apps.votes.models import Vote, VoteAttempt
from core.exceptions import (
    DuplicateVoteError,
    InvalidVoteError,
    PollClosedError,
    PollNotFoundError,
)
from core.utils.fingerprint_validation import (
    check_fingerprint_suspicious,
    update_fingerprint_cache,
)
from core.utils.idempotency import (
    check_idempotency,
    generate_idempotency_key,
    store_idempotency_result,
)
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def create_vote(
    user: User,
    poll_id: int,
    choice_id: int,
    idempotency_key: str = None,
    request=None,
):
    """
    Create a vote with idempotency and fingerprint validation support.

    Args:
        user: The user making the vote
        poll_id: The ID of the poll
        choice_id: The ID of the choice
        idempotency_key: Optional idempotency key.
            If not provided, one will be generated.
        request: Django request object (optional, for fingerprint/IP extraction)

    Returns:
        Vote: The created or existing vote

    Raises:
        PollNotFoundError: If the poll doesn't exist
        InvalidVoteError: If the choice doesn't belong to the poll
        PollClosedError: If the poll is closed
        DuplicateVoteError: If the user has already voted on this poll
        InvalidVoteError: If fingerprint validation blocks the vote
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

    # Extract fingerprint and tracking data from request
    fingerprint = getattr(request, "fingerprint", "") if request else ""
    ip_address = None
    user_agent = ""

    if request:
        # Get IP address
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(",")[0].strip()
        else:
            ip_address = request.META.get("REMOTE_ADDR")

        # Get user agent
        user_agent = request.META.get("HTTP_USER_AGENT", "")

    # Fingerprint validation (Tier 1 & 2)
    validation_result = None
    if fingerprint:
        try:
            validation_result = check_fingerprint_suspicious(
                fingerprint=fingerprint,
                poll_id=poll_id,
                user_id=user.id,
                ip_address=ip_address,
                request=request,
            )

            # Block vote if critical suspicious pattern detected
            if validation_result.get("block_vote", False):
                # Log to VoteAttempt
                VoteAttempt.objects.create(
                    user=user,
                    poll=poll,
                    option=choice,
                    voter_token="",  # Will be set if needed
                    idempotency_key=idempotency_key,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    fingerprint=fingerprint,
                    success=False,
                    error_message=f"Fingerprint validation failed: {', '.join(validation_result.get('reasons', []))}",
                )

                raise InvalidVoteError(
                    f"Vote blocked due to suspicious activity: {', '.join(validation_result.get('reasons', []))}"
                )

            # Log warning if suspicious but not blocking
            if validation_result.get("suspicious", False):
                logger.warning(
                    f"Suspicious fingerprint detected for user {user.id}, poll {poll_id}: "
                    f"{', '.join(validation_result.get('reasons', []))}"
                )

                # Trigger async analysis (Tier 3)
                try:
                    from apps.votes.tasks import analyze_fingerprint_patterns

                    analyze_fingerprint_patterns.delay(fingerprint, poll_id)
                except Exception as e:
                    logger.error(f"Failed to trigger async fingerprint analysis: {e}")

        except InvalidVoteError:
            raise
        except Exception as e:
            logger.error(f"Error in fingerprint validation: {e}")
            # Don't block vote if validation fails, but log error

    # Create vote
    with transaction.atomic():
        vote = Vote.objects.create(
            user=user,
            option=choice,
            poll=poll,
            idempotency_key=idempotency_key,
            voter_token="",  # Can be set if needed for anonymous voting
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=fingerprint,
        )

        # Update fingerprint cache
        if fingerprint:
            try:
                update_fingerprint_cache(
                    fingerprint=fingerprint,
                    poll_id=poll_id,
                    user_id=user.id,
                    ip_address=ip_address,
                )
            except Exception as e:
                logger.error(f"Error updating fingerprint cache: {e}")

        # Store result for idempotency
        store_idempotency_result(
            idempotency_key,
            {"vote_id": vote.id, "status": "created"},
        )

        # Log successful vote attempt
        VoteAttempt.objects.create(
            user=user,
            poll=poll,
            option=choice,
            voter_token="",
            idempotency_key=idempotency_key,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=fingerprint,
            success=True,
        )

    return vote
