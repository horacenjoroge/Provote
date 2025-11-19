"""
Integration tests for fingerprint validation in vote casting.
"""

import hashlib
import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.utils import timezone

from apps.votes.services import cast_vote
from core.exceptions import FingerprintValidationError, FraudDetectedError


def make_fingerprint(seed: str) -> str:
    """Generate a valid 64-character hex fingerprint from a seed string."""
    return hashlib.sha256(seed.encode()).hexdigest()


@pytest.mark.django_db
class TestFingerprintValidationInVoteCasting:
    """Test fingerprint validation during vote casting."""

    def test_anonymous_vote_requires_fingerprint(self, poll, choices):
        """Test that anonymous votes require fingerprint."""
        factory = RequestFactory()
        request = factory.post("/api/votes/cast/")
        request.fingerprint = ""  # Missing fingerprint
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        anonymous_user = AnonymousUser()

        with pytest.raises(FingerprintValidationError) as exc_info:
            cast_vote(
                user=anonymous_user,
                poll_id=poll.id,
                choice_id=choices[0].id,
                request=request,
            )

        assert "required" in str(exc_info.value).lower()
        assert "anonymous" in str(exc_info.value).lower()

    def test_anonymous_vote_with_valid_fingerprint_succeeds(self, poll, choices):
        """Test that anonymous votes with valid fingerprint succeed."""
        factory = RequestFactory()
        request = factory.post("/api/votes/cast/")
        fingerprint = make_fingerprint("valid_fp")
        request.fingerprint = fingerprint
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        anonymous_user = AnonymousUser()

        vote, is_new = cast_vote(
            user=anonymous_user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request,
        )

        assert vote is not None
        assert vote.fingerprint == fingerprint
        assert is_new is True

    def test_authenticated_vote_without_fingerprint_succeeds(self, user, poll, choices):
        """Test that authenticated votes don't require fingerprint."""
        factory = RequestFactory()
        request = factory.post("/api/votes/cast/")
        request.fingerprint = ""  # Missing fingerprint
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request,
        )

        assert vote is not None
        assert is_new is True

    def test_vote_with_invalid_fingerprint_format_rejected(self, poll, choices):
        """Test that votes with invalid fingerprint format are rejected."""
        factory = RequestFactory()
        request = factory.post("/api/votes/cast/")
        request.fingerprint = "short"  # Invalid format
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        anonymous_user = AnonymousUser()

        with pytest.raises(FingerprintValidationError) as exc_info:
            cast_vote(
                user=anonymous_user,
                poll_id=poll.id,
                choice_id=choices[0].id,
                request=request,
            )

        assert "format" in str(exc_info.value).lower() or "64" in str(exc_info.value)

    def test_vote_with_missing_fingerprint_flagged(self, user, poll, choices):
        """Test that votes with missing fingerprint are flagged."""
        factory = RequestFactory()
        request = factory.post("/api/votes/cast/")
        request.fingerprint = ""  # Missing fingerprint
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request,
        )

        # Vote should be created but flagged
        assert vote is not None
        assert vote.fingerprint == ""
        # For authenticated users, missing fingerprint doesn't invalidate vote
        # but it's logged in fraud_reasons
        assert "Missing browser fingerprint" in vote.fraud_reasons or vote.is_valid

    def test_same_fingerprint_different_ips_blocked(self, poll, choices):
        """Test that same fingerprint from different IPs is blocked."""
        from apps.votes.models import Vote

        factory = RequestFactory()
        fingerprint = make_fingerprint("shared_fp")

        # First vote from IP1
        request1 = factory.post("/api/votes/cast/")
        request1.fingerprint = fingerprint
        request1.META["REMOTE_ADDR"] = "192.168.1.1"

        anonymous_user1 = AnonymousUser()
        vote1, _ = cast_vote(
            user=anonymous_user1,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request1,
        )

        # Second vote from IP2 (should be OK - only 1 different IP so far)
        request2 = factory.post("/api/votes/cast/")
        request2.fingerprint = fingerprint
        request2.META["REMOTE_ADDR"] = "192.168.1.2"

        anonymous_user2 = AnonymousUser()
        vote2, _ = cast_vote(
            user=anonymous_user2,
            poll_id=poll.id,
            choice_id=choices[1].id,
            request=request2,
        )

        # Third vote from IP3 (should be blocked - 2+ different IPs)
        request3 = factory.post("/api/votes/cast/")
        request3.fingerprint = fingerprint
        request3.META["REMOTE_ADDR"] = "192.168.1.3"

        anonymous_user3 = AnonymousUser()
        with pytest.raises(FraudDetectedError) as exc_info:
            cast_vote(
                user=anonymous_user3,
                poll_id=poll.id,
                choice_id=choices[0].id,
                request=request3,
            )

        assert "different ip" in str(exc_info.value).lower() or "shared" in str(exc_info.value).lower()

    def test_fingerprint_used_in_idempotency_key(self, poll, choices):
        """Test that fingerprint is used in idempotency key generation."""
        from core.utils.idempotency import generate_idempotency_key

        factory = RequestFactory()
        fingerprint = make_fingerprint("test_fp")
        ip_address = "192.168.1.1"

        request = factory.post("/api/votes/cast/")
        request.fingerprint = fingerprint
        request.META["REMOTE_ADDR"] = ip_address

        anonymous_user = AnonymousUser()

        # Cast vote
        vote1, is_new1 = cast_vote(
            user=anonymous_user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request,
        )

        # Generate idempotency key manually with same params
        idempotency_key = generate_idempotency_key(
            user_id=None,
            poll_id=poll.id,
            choice_id=choices[0].id,
            fingerprint=fingerprint,
            ip_address=ip_address,
        )

        # Should match the vote's idempotency key
        assert vote1.idempotency_key == idempotency_key

        # Cast vote again with same fingerprint+IP (should be idempotent)
        vote2, is_new2 = cast_vote(
            user=anonymous_user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request,
        )

        # Should return existing vote
        assert vote2.id == vote1.id
        assert is_new2 is False

    def test_legitimate_fingerprint_change_allowed(self, user, poll, choices):
        """Test that legitimate fingerprint changes are allowed (on different polls)."""
        from apps.votes.models import Vote
        from datetime import timedelta
        from apps.polls.factories import PollFactory, PollOptionFactory

        factory = RequestFactory()

        # Create a second poll for testing fingerprint change
        poll2 = PollFactory(created_by=user, is_active=True)
        choice2 = PollOptionFactory(poll=poll2, text="Option 1")
        choice2_2 = PollOptionFactory(poll=poll2, text="Option 2")

        # Create old vote with first fingerprint on first poll
        old_time = timezone.now() - timedelta(days=2)
        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            fingerprint=make_fingerprint("old_fp"),
            ip_address="192.168.1.1",
            voter_token="token1",
            idempotency_key="key1",
            created_at=old_time,
        )

        # Cast vote on different poll with different fingerprint (should be OK)
        request = factory.post("/api/votes/cast/")
        fingerprint = make_fingerprint("new_fp")
        request.fingerprint = fingerprint
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        vote, is_new = cast_vote(
            user=user,
            poll_id=poll2.id,
            choice_id=choice2.id,
            request=request,
        )

        # Should succeed (legitimate change on different poll)
        assert vote is not None
        assert is_new is True
        assert vote.fingerprint == fingerprint

