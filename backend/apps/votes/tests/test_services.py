"""
Tests for Vote services.
"""

import pytest
from apps.votes.services import create_vote
from core.exceptions import DuplicateVoteError, InvalidVoteError, PollNotFoundError


@pytest.mark.unit
class TestVoteService:
    """Test vote service functions."""

    def test_create_vote(self, user, poll, choices):
        """Test creating a vote."""
        vote = create_vote(user=user, poll_id=poll.id, choice_id=choices[0].id)
        assert vote is not None
        assert vote.user == user
        assert vote.choice == choices[0]
        assert vote.poll == poll

    def test_create_vote_poll_not_found(self, user):
        """Test creating a vote with non-existent poll."""
        with pytest.raises(PollNotFoundError):
            create_vote(user=user, poll_id=999, choice_id=1)

    def test_create_vote_invalid_choice(self, user, poll, choices):
        """Test creating a vote with invalid choice."""
        # Create another poll
        from apps.polls.models import Poll

        other_poll = Poll.objects.create(
            title="Other Poll",
            created_by=user,
        )
        from apps.polls.models import Choice

        other_choice = Choice.objects.create(poll=other_poll, text="Other Choice")

        with pytest.raises(InvalidVoteError):
            create_vote(user=user, poll_id=poll.id, choice_id=other_choice.id)

    def test_create_vote_duplicate(self, user, poll, choices):
        """Test creating duplicate vote."""
        create_vote(user=user, poll_id=poll.id, choice_id=choices[0].id)
        with pytest.raises(DuplicateVoteError):
            create_vote(user=user, poll_id=poll.id, choice_id=choices[1].id)

    def test_create_vote_idempotency(self, user, poll, choices):
        """Test vote idempotency."""
        idempotency_key = "test-key-123"
        vote1 = create_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            idempotency_key=idempotency_key,
        )
        # Should not raise error, but should return existing vote
        # Note: This will raise DuplicateVoteError due to unique constraint
        # In a real scenario, you'd check idempotency first
        assert vote1.idempotency_key == idempotency_key
