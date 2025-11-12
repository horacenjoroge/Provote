"""
Tests for Vote services.
"""

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from apps.votes.services import create_vote
from core.exceptions import DuplicateVoteError, InvalidVoteError, PollNotFoundError


@pytest.mark.unit
class TestVoteService:
    """Test vote service functions."""

    def test_create_vote(self, user, poll, choices):
        """Test creating a vote."""
        vote = create_vote(
            user=user, poll_id=poll.id, choice_id=choices[0].id, request=None
        )
        assert vote is not None
        assert vote.user == user
        assert vote.option == choices[0]
        assert vote.poll == poll

    def test_create_vote_poll_not_found(self, user):
        """Test creating a vote with non-existent poll."""
        with pytest.raises(PollNotFoundError):
            create_vote(user=user, poll_id=999, choice_id=1, request=None)

    def test_create_vote_invalid_choice(self, user, poll, choices):
        """Test creating a vote with invalid choice."""
        # Create another poll
        from apps.polls.models import Poll, PollOption

        other_poll = Poll.objects.create(title="Other Poll", created_by=user)
        other_choice = PollOption.objects.create(poll=other_poll, text="Other Choice")

        with pytest.raises(InvalidVoteError):
            create_vote(
                user=user, poll_id=poll.id, choice_id=other_choice.id, request=None
            )

    def test_create_vote_duplicate(self, user, poll, choices):
        """Test creating duplicate vote."""
        create_vote(
            user=user, poll_id=poll.id, choice_id=choices[0].id, request=None
        )
        with pytest.raises(DuplicateVoteError):
            create_vote(
                user=user, poll_id=poll.id, choice_id=choices[1].id, request=None
            )

    def test_create_vote_with_fingerprint(self, user, poll, choices):
        """Test creating vote with fingerprint from request."""
        factory = RequestFactory()
        request = factory.post("/api/votes/")
        request.fingerprint = "test_fingerprint_123"
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        vote = create_vote(
            user=user, poll_id=poll.id, choice_id=choices[0].id, request=request
        )

        assert vote.fingerprint == "test_fingerprint_123"
        assert vote.ip_address == "192.168.1.1"
        assert vote.user_agent == "Test Agent"

    def test_create_vote_stores_fingerprint(self, user, poll, choices):
        """Test that fingerprint is stored in Vote model."""
        factory = RequestFactory()
        request = factory.post("/api/votes/")
        request.fingerprint = "stored_fp_123"

        vote = create_vote(
            user=user, poll_id=poll.id, choice_id=choices[0].id, request=request
        )

        assert vote.fingerprint == "stored_fp_123"


@pytest.mark.django_db
class TestVoteServiceFingerprintValidation:
    """Test fingerprint validation in vote service."""

    def test_fingerprint_validation_blocks_suspicious_vote(self, user):
        """Test that suspicious fingerprints block votes."""
        from apps.polls.models import Poll, PollOption
        from apps.votes.models import Vote

        cache.clear()

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        option = PollOption.objects.create(poll=poll, text="Option 1")

        user2 = type(user).objects.create_user(username="user2", password="pass")

        # Create vote with fingerprint
        Vote.objects.create(
            user=user,
            poll=poll,
            option=option,
            fingerprint="suspicious_fp",
            ip_address="192.168.1.1",
            voter_token="token1",
            idempotency_key="key1",
        )

        # Update cache to mark as suspicious
        from core.utils.fingerprint_validation import update_fingerprint_cache

        update_fingerprint_cache("suspicious_fp", poll.id, user.id, "192.168.1.1")

        # Try to create vote with same fingerprint, different user
        factory = RequestFactory()
        request = factory.post("/api/votes/")
        request.fingerprint = "suspicious_fp"
        request.META["REMOTE_ADDR"] = "192.168.1.2"

        with pytest.raises(InvalidVoteError) as exc_info:
            create_vote(
                user=user2, poll_id=poll.id, choice_id=option.id, request=request
            )

        assert "suspicious" in str(exc_info.value).lower()

    def test_fingerprint_validation_allows_clean_vote(self, user, poll, choices):
        """Test that clean fingerprints allow votes."""
        cache.clear()

        factory = RequestFactory()
        request = factory.post("/api/votes/")
        request.fingerprint = "clean_fp_123"
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        vote = create_vote(
            user=user, poll_id=poll.id, choice_id=choices[0].id, request=request
        )

        assert vote is not None
        assert vote.fingerprint == "clean_fp_123"

    def test_vote_attempt_logged_on_failure(self, user):
        """Test that failed vote attempts are logged."""
        from apps.polls.models import Poll, PollOption
        from apps.votes.models import Vote, VoteAttempt

        cache.clear()

        poll = Poll.objects.create(title="Test Poll", created_by=user)
        option = PollOption.objects.create(poll=poll, text="Option 1")

        user2 = type(user).objects.create_user(username="user2", password="pass")

        # Create vote with fingerprint
        Vote.objects.create(
            user=user,
            poll=poll,
            option=option,
            fingerprint="blocked_fp",
            ip_address="192.168.1.1",
            voter_token="token1",
            idempotency_key="key1",
        )

        # Update cache
        from core.utils.fingerprint_validation import update_fingerprint_cache

        update_fingerprint_cache("blocked_fp", poll.id, user.id, "192.168.1.1")

        # Try to create vote (should be blocked)
        factory = RequestFactory()
        request = factory.post("/api/votes/")
        request.fingerprint = "blocked_fp"
        request.META["REMOTE_ADDR"] = "192.168.1.2"

        initial_count = VoteAttempt.objects.count()

        try:
            create_vote(user=user2, poll_id=poll.id, choice_id=option.id, request=request)
        except InvalidVoteError:
            pass

        # Check that attempt was logged
        assert VoteAttempt.objects.count() == initial_count + 1
        attempt = VoteAttempt.objects.latest("created_at")
        assert attempt.success is False
        assert attempt.fingerprint == "blocked_fp"

    def test_vote_attempt_logged_on_success(self, user, poll, choices):
        """Test that successful votes are logged."""
        from apps.votes.models import VoteAttempt

        cache.clear()

        factory = RequestFactory()
        request = factory.post("/api/votes/")
        request.fingerprint = "success_fp"
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        initial_count = VoteAttempt.objects.count()

        vote = create_vote(
            user=user, poll_id=poll.id, choice_id=choices[0].id, request=request
        )

        # Check that attempt was logged
        assert VoteAttempt.objects.count() == initial_count + 1
        attempt = VoteAttempt.objects.latest("created_at")
        assert attempt.success is True
        assert attempt.fingerprint == "success_fp"
        assert attempt.user == user
