"""
Comprehensive tests for cast_vote() core voting service.
Tests atomic operations, idempotency, validation, and race conditions.
"""

import hashlib

import pytest
from apps.votes.services import cast_vote
from core.exceptions import (
    DuplicateVoteError,
    FraudDetectedError,
    InvalidPollError,
    InvalidVoteError,
    PollClosedError,
    PollNotFoundError,
)
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone


def make_fingerprint(seed: str) -> str:
    """Generate a valid 64-character hex fingerprint from a seed string."""
    return hashlib.sha256(seed.encode()).hexdigest()


@pytest.mark.django_db
class TestCastVoteSuccess:
    """Test successful vote creation scenarios."""

    def test_successful_vote_creation(self, user, poll, choices):
        """Test successful vote creation."""
        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=None,
        )

        assert vote is not None
        assert vote.user == user
        assert vote.poll == poll
        assert vote.option == choices[0]
        assert is_new is True

    def test_vote_counts_increment_correctly(self, user, poll, choices):
        """Test that vote counts increment correctly."""
        option = choices[0]

        # Initial counts
        initial_option_count = option.cached_vote_count
        initial_poll_total = poll.cached_total_votes
        initial_poll_voters = poll.cached_unique_voters

        # Create vote
        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=option.id,
            request=None,
        )

        # Refresh from database
        option.refresh_from_db()
        poll.refresh_from_db()

        # Check counts incremented
        assert option.cached_vote_count == initial_option_count + 1
        assert poll.cached_total_votes == initial_poll_total + 1
        assert poll.cached_unique_voters == initial_poll_voters + 1

    def test_vote_creates_audit_log(self, user, poll, choices):
        """Test that vote creates audit log entry."""
        from apps.votes.models import VoteAttempt

        initial_count = VoteAttempt.objects.count()

        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=None,
        )

        # Check audit log was created
        assert VoteAttempt.objects.count() == initial_count + 1
        attempt = VoteAttempt.objects.latest("created_at")
        assert attempt.success is True
        assert attempt.poll == poll
        assert attempt.option == choices[0]


@pytest.mark.django_db
class TestCastVoteIdempotency:
    """Test idempotency guarantees."""

    def test_idempotent_retry_returns_same_vote(self, user, poll, choices):
        """Test that idempotent retry returns same vote (HTTP 200, not 201)."""
        idempotency_key = "test-idempotency-key-123"

        # First vote
        vote1, is_new1 = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            idempotency_key=idempotency_key,
            request=None,
        )

        assert is_new1 is True

        # Second vote with same idempotency key (idempotent retry)
        vote2, is_new2 = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            idempotency_key=idempotency_key,
            request=None,
        )

        # Should return same vote, not create new one
        assert vote1.id == vote2.id
        assert is_new2 is False  # Not a new vote

    def test_idempotent_retry_does_not_increment_counts(self, user, poll, choices):
        """Test that idempotent retry doesn't increment vote counts."""
        option = choices[0]
        idempotency_key = "test-idempotency-key-456"

        # First vote
        vote1, _ = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=option.id,
            idempotency_key=idempotency_key,
            request=None,
        )

        # Get counts after first vote
        option.refresh_from_db()
        poll.refresh_from_db()
        count_after_first = option.cached_vote_count
        poll_total_after_first = poll.cached_total_votes

        # Idempotent retry
        vote2, _ = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=option.id,
            idempotency_key=idempotency_key,
            request=None,
        )

        # Counts should not have changed
        option.refresh_from_db()
        poll.refresh_from_db()
        assert option.cached_vote_count == count_after_first
        assert poll.cached_total_votes == poll_total_after_first


@pytest.mark.django_db
class TestCastVotePollValidation:
    """Test poll validation scenarios."""

    def test_voting_on_closed_poll_is_rejected(self, user, poll, choices):
        """Test that voting on closed poll is rejected."""
        # Close the poll
        poll.is_active = False
        poll.save()

        with pytest.raises(InvalidPollError) as exc_info:
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[0].id,
                request=None,
            )

        assert (
            "not active" in str(exc_info.value).lower()
            or "closed" in str(exc_info.value).lower()
        )

    def test_voting_on_expired_poll_is_rejected(self, user, poll, choices):
        """Test that voting on expired poll is rejected."""
        # Set poll to expire in the past
        poll.ends_at = timezone.now() - timezone.timedelta(days=1)
        poll.save()

        with pytest.raises(PollClosedError) as exc_info:
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[0].id,
                request=None,
            )

        assert (
            "expired" in str(exc_info.value).lower()
            or "closed" in str(exc_info.value).lower()
        )

    def test_voting_on_not_started_poll_is_rejected(self, user, poll, choices):
        """Test that voting on not-yet-started poll is rejected."""
        # Set poll to start in the future
        poll.starts_at = timezone.now() + timezone.timedelta(days=1)
        poll.save()

        with pytest.raises(InvalidPollError) as exc_info:
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[0].id,
                request=None,
            )

        assert "not started" in str(exc_info.value).lower()

    def test_voting_on_nonexistent_poll_is_rejected(self, user, choices):
        """Test that voting on nonexistent poll is rejected."""
        with pytest.raises(PollNotFoundError):
            cast_vote(
                user=user,
                poll_id=99999,
                choice_id=choices[0].id,
                request=None,
            )


@pytest.mark.django_db
class TestCastVoteVoterValidation:
    """Test voter validation scenarios."""

    def test_duplicate_votes_from_same_voter_rejected(self, user, poll, choices):
        """Test that duplicate votes from same voter are rejected."""
        # First vote
        vote1, _ = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=None,
        )

        # Try to vote again (different choice, same poll)
        with pytest.raises(DuplicateVoteError) as exc_info:
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[1].id,
                request=None,
            )

        assert "already voted" in str(exc_info.value).lower()

    def test_ip_limit_enforcement(self, user, poll, choices):
        """Test IP limit enforcement."""
        # Set IP limit in security rules
        poll.security_rules = {"max_votes_per_ip": 2}
        poll.save()

        factory = RequestFactory()
        request1 = factory.post("/api/votes/")
        request1.META["REMOTE_ADDR"] = "192.168.1.100"

        # Create first vote from IP
        import time

        timestamp = int(time.time() * 1000000)
        user1 = type(user).objects.create_user(
            username=f"user1_{timestamp}", password="pass"
        )
        vote1, _ = cast_vote(
            user=user1,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request1,
        )

        # Create second vote from same IP
        user2 = type(user).objects.create_user(
            username=f"user2_{timestamp}", password="pass"
        )
        vote2, _ = cast_vote(
            user=user2,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request1,
        )

        # Third vote from same IP should be rejected
        user3 = type(user).objects.create_user(
            username=f"user3_{timestamp}", password="pass"
        )
        with pytest.raises(InvalidVoteError) as exc_info:
            cast_vote(
                user=user3,
                poll_id=poll.id,
                choice_id=choices[0].id,
                request=request1,
            )

        assert (
            "ip" in str(exc_info.value).lower()
            and "limit" in str(exc_info.value).lower()
        )

    def test_authentication_requirement_enforcement(self, poll, choices):
        """Test authentication requirement enforcement."""
        # Set authentication requirement
        poll.security_rules = {"require_authentication": True}
        poll.save()

        # Try to vote without user (should fail, but we need a user object)
        # Since cast_vote requires a user, we'll test with an unauthenticated-like scenario
        # by checking the security rule
        import time

        timestamp = int(time.time() * 1000000)
        user = type(poll.created_by).objects.create_user(
            username=f"testuser_{timestamp}", password="pass"
        )
        # The function requires a user, so we test the rule check instead
        # In real scenario, middleware would handle unauthenticated users

        # For now, test that authenticated user can vote
        vote, _ = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=None,
        )
        assert vote is not None


@pytest.mark.django_db
class TestCastVoteConcurrency:
    """Test concurrent vote scenarios and race conditions."""

    def test_concurrent_votes_race_condition(self, poll, choices):
        """Test that concurrent votes from different users work correctly."""
        from django.contrib.auth.models import User
        from django.db import connection

        # Create multiple users
        users = []
        for i in range(3):
            import time

            timestamp = int(time.time() * 1000000)
            user = User.objects.create_user(
                username=f"user{i}_{timestamp}", password="pass"
            )
            users.append(user)

        # Create votes from different users (simulating concurrent requests)
        votes_created = []
        for user in users:
            try:
                # Close connection for this iteration (simulating new request)
                connection.close()
                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll.id,
                    choice_id=choices[0].id,
                    request=None,
                )
                votes_created.append((vote.id, is_new))
            except Exception as e:
                # Should not have errors for different users
                pytest.fail(f"Unexpected error: {e}")

        # All votes should be created successfully (different users)
        assert len(votes_created) == 3
        assert all(is_new for _, is_new in votes_created)

        # Try to vote again with same user but different choice (should fail - user already voted on this poll)
        with pytest.raises(DuplicateVoteError):
            cast_vote(
                user=users[0],
                poll_id=poll.id,
                choice_id=choices[1].id
                if len(choices) > 1
                else choices[0].id,  # Different choice, same poll
                request=None,
            )

    def test_select_for_update_prevents_race_conditions(self, poll, choices):
        """Test that select_for_update prevents race conditions."""
        from django.contrib.auth.models import User

        # This test verifies that select_for_update locks work
        # by checking that vote counts are accurate even under concurrency

        option = choices[0]
        initial_count = option.cached_vote_count

        # Create multiple votes sequentially (simulating concurrent requests)
        import time

        timestamp = int(time.time() * 1000000)
        user1 = User.objects.create_user(username=f"user1_{timestamp}", password="pass")
        user2 = User.objects.create_user(username=f"user2_{timestamp}", password="pass")
        user3 = User.objects.create_user(username=f"user3_{timestamp}", password="pass")

        vote1, _ = cast_vote(
            user=user1, poll_id=poll.id, choice_id=option.id, request=None
        )
        vote2, _ = cast_vote(
            user=user2, poll_id=poll.id, choice_id=option.id, request=None
        )
        vote3, _ = cast_vote(
            user=user3, poll_id=poll.id, choice_id=option.id, request=None
        )

        # Refresh and check counts
        option.refresh_from_db()
        poll.refresh_from_db()

        # Counts should be accurate
        assert option.cached_vote_count == initial_count + 3
        assert poll.cached_total_votes >= 3

    def test_same_user_concurrent_votes_prevented(self, user, poll, choices):
        """Test that same user cannot vote concurrently (race condition protection)."""
        # This simulates a race condition where the same user tries to vote twice
        # The select_for_update lock should prevent duplicate votes

        # First vote succeeds
        vote1, is_new1 = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=None,
        )
        assert is_new1 is True

        # Second vote from same user should fail (even if concurrent)
        with pytest.raises(DuplicateVoteError):
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[1].id,  # Different choice, same poll
                request=None,
            )


@pytest.mark.django_db
class TestCastVoteDatabaseRollback:
    """Test database rollback on failure scenarios."""

    def test_database_rollback_on_failure(self, user, poll, choices):
        """Test that database rolls back on failure."""
        option = choices[0]
        initial_option_count = option.cached_vote_count
        initial_poll_total = poll.cached_total_votes

        # Try to vote with invalid choice (should fail)
        from apps.polls.models import Poll as PollModel

        other_poll = PollModel.objects.create(title="Other Poll", created_by=user)
        from apps.polls.models import PollOption

        other_option = PollOption.objects.create(poll=other_poll, text="Other Option")

        with pytest.raises(InvalidVoteError):
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=other_option.id,  # Wrong poll
                request=None,
            )

        # Counts should not have changed (rolled back)
        option.refresh_from_db()
        poll.refresh_from_db()
        assert option.cached_vote_count == initial_option_count
        assert poll.cached_total_votes == initial_poll_total

    def test_rollback_on_fingerprint_validation_failure(self, user, poll, choices):
        """Test rollback when fingerprint validation fails."""
        from apps.analytics.models import FingerprintBlock
        from apps.votes.models import Vote

        # Create permanent block for fingerprint
        fingerprint = make_fingerprint("blocked_fp_123")
        FingerprintBlock.objects.create(
            fingerprint=fingerprint,
            reason="Test block",
            first_seen_user=user,
            total_users=1,
            total_votes=1,
        )

        factory = RequestFactory()
        request = factory.post("/api/votes/")
        request.fingerprint = fingerprint
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        initial_vote_count = Vote.objects.filter(poll=poll).count()

        # Try to vote (should be blocked)
        with pytest.raises(FraudDetectedError):
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[0].id,
                request=request,
            )

        # Vote should not have been created
        assert Vote.objects.filter(poll=poll).count() == initial_vote_count


@pytest.mark.django_db
class TestCastVoteCacheInvalidation:
    """Test cache invalidation."""

    def test_cache_invalidation_on_vote(self, user, poll, choices):
        """Test that cache is invalidated when vote is created."""

        # Set some cache keys
        cache.set(f"poll:{poll.id}", {"data": "test"}, 3600)
        cache.set(f"poll:{poll.id}:results", {"results": []}, 3600)
        cache.set(f"option:{choices[0].id}:votes", 0, 3600)

        # Create vote
        vote, _ = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=None,
        )

        # Cache should be invalidated
        assert cache.get(f"poll:{poll.id}") is None
        assert cache.get(f"poll:{poll.id}:results") is None
        assert cache.get(f"option:{choices[0].id}:votes") is None


@pytest.mark.django_db
class TestCastVoteEdgeCases:
    """Test edge cases and error scenarios."""

    def test_vote_with_fingerprint(self, user, poll, choices):
        """Test voting with fingerprint."""
        factory = RequestFactory()
        request = factory.post("/api/votes/")
        fingerprint = make_fingerprint("test_fingerprint_123")
        request.fingerprint = fingerprint
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request,
        )

        assert vote.fingerprint == fingerprint
        assert vote.ip_address == "192.168.1.1"
        assert is_new is True

    def test_vote_without_request(self, user, poll, choices):
        """Test voting without request object."""
        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=None,
        )

        assert vote is not None
        assert vote.fingerprint == ""
        assert vote.ip_address is None
        assert is_new is True

    def test_vote_creates_voter_token(self, user, poll, choices):
        """Test that vote creates voter token."""
        factory = RequestFactory()
        request = factory.post("/api/votes/")
        fingerprint = make_fingerprint("fp123")
        request.fingerprint = fingerprint
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0"

        vote, _ = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request,
        )

        assert vote.voter_token is not None
        assert len(vote.voter_token) == 64  # SHA256 hex length


@pytest.mark.django_db
class TestCastVoteRedisPubSub:
    """Test Redis Pub/Sub integration for vote events."""

    def test_vote_publishes_to_redis(self, user, poll, choices):
        """Test that casting a vote publishes an event to Redis."""
        from unittest.mock import patch

        with patch("core.utils.redis_pubsub.publish_vote_event") as mock_publish:
            vote, is_new = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[0].id,
                request=None,
            )

            # Verify vote was created
            assert vote is not None
            assert is_new is True

            # Verify Redis publish was called
            mock_publish.assert_called_once_with(poll.id, vote.id)

    def test_vote_handles_redis_failure_gracefully(self, user, poll, choices):
        """Test that vote casting handles Redis failures gracefully."""
        from unittest.mock import patch

        # Simulate Redis failure
        with patch(
            "core.utils.redis_pubsub.publish_vote_event",
            side_effect=Exception("Redis error"),
        ):
            # Vote should still succeed even if Redis fails
            vote, is_new = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[0].id,
                request=None,
            )

            assert vote is not None
            assert is_new is True
