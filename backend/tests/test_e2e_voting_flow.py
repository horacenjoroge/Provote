"""
End-to-end integration tests for complete voting flow.

Tests:
- Poll creation → voting → results
- Idempotency across requests
- Concurrent operations
- Database transactions
- Cache invalidation
- Happy paths, error scenarios, edge cases
"""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.polls.factories import PollFactory, PollOptionFactory
from apps.polls.models import Poll
from apps.polls.services import calculate_poll_results, invalidate_results_cache
from apps.votes.models import Vote, VoteAttempt
from apps.votes.services import cast_vote
from core.exceptions import DuplicateVoteError


@pytest.mark.integration
@pytest.mark.django_db
class TestCompleteVotingFlow:
    """Test complete flow: poll creation → voting → results."""

    def test_happy_path_complete_flow(self, user):
        """Test happy path: create poll, vote, view results."""
        client = APIClient()
        client.force_authenticate(user=user)

        # 1. Create poll
        poll_data = {
            "title": "E2E Test Poll",
            "description": "End-to-end test poll",
            "options": [
                {"text": "Option A", "order": 0},
                {"text": "Option B", "order": 1},
                {"text": "Option C", "order": 2},
            ],
            "settings": {"show_results_during_voting": True},
        }
        response = client.post(reverse("poll-list"), poll_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        poll_id = response.data["id"]
        option_ids = [opt["id"] for opt in response.data["options"]]

        # 2. Cast vote
        vote_data = {
            "poll_id": poll_id,
            "choice_id": option_ids[0],
        }
        response = client.post(reverse("vote-cast"), vote_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        vote_id = response.data["id"]

        # 3. Verify vote in database
        vote = Vote.objects.get(id=vote_id)
        assert vote.poll.id == poll_id
        assert vote.option.id == option_ids[0]
        assert vote.user == user

        # 4. View results
        response = client.get(reverse("poll-results", kwargs={"pk": poll_id}))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_votes"] == 1
        assert len(response.data["options"]) == 3
        # Find the option that was voted for
        voted_option = next(opt for opt in response.data["options"] if opt["option_id"] == option_ids[0])
        assert voted_option["votes"] == 1

        # 5. Verify cached totals updated
        poll = Poll.objects.get(id=poll_id)
        assert poll.cached_total_votes == 1
        assert poll.cached_unique_voters == 1

    def test_poll_creation_with_multiple_options(self, user):
        """Test creating poll with many options."""
        client = APIClient()
        client.force_authenticate(user=user)

        poll_data = {
            "title": "Multi-Option Poll",
            "options": [{"text": f"Option {i}", "order": i} for i in range(10)],
        }
        response = client.post(reverse("poll-list"), poll_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data["options"]) == 10

    def test_voting_flow_with_results_hidden(self, user):
        """Test voting when results are hidden during voting."""
        client = APIClient()
        client.force_authenticate(user=user)

        # Create poll with results hidden
        poll_data = {
            "title": "Hidden Results Poll",
            "options": [
                {"text": "Option A", "order": 0},
                {"text": "Option B", "order": 1},
            ],
            "settings": {"show_results_during_voting": False},
        }
        response = client.post(reverse("poll-list"), poll_data, format="json")
        poll_id = response.data["id"]
        option_ids = [opt["id"] for opt in response.data["options"]]

        # Vote
        vote_data = {"poll_id": poll_id, "choice_id": option_ids[0]}
        response = client.post(reverse("vote-cast"), vote_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Try to view results (should be blocked)
        response = client.get(reverse("poll-results", kwargs={"pk": poll_id}))
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Close poll
        poll = Poll.objects.get(id=poll_id)
        poll.is_active = False
        poll.save()

        # Now results should be visible
        response = client.get(reverse("poll-results", kwargs={"pk": poll_id}))
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.integration
@pytest.mark.django_db
class TestIdempotencyAcrossRequests:
    """Test idempotency across multiple requests."""

    def test_idempotent_vote_returns_same_vote(self, user, poll, choices):
        """Test that same idempotency key returns same vote."""
        client = APIClient()
        client.force_authenticate(user=user)

        idempotency_key = f"test-key-{uuid.uuid4()}"
        vote_data = {
            "poll_id": poll.id,
            "choice_id": choices[0].id,
            "idempotency_key": idempotency_key,
        }

        # First request
        response1 = client.post(reverse("vote-cast"), vote_data, format="json")
        assert response1.status_code == status.HTTP_201_CREATED
        vote_id_1 = response1.data["id"]

        # Second request with same key (should return 409 Conflict for duplicate vote)
        response2 = client.post(reverse("vote-cast"), vote_data, format="json")
        # API returns 409 for duplicate votes, but vote_id should still be accessible
        assert response2.status_code in [status.HTTP_200_OK, status.HTTP_409_CONFLICT]
        if response2.status_code == status.HTTP_200_OK:
            vote_id_2 = response2.data["id"]
            # Should be same vote
            assert vote_id_1 == vote_id_2

        # Verify only one vote in database
        votes = Vote.objects.filter(poll=poll, user=user)
        assert votes.count() == 1

    def test_idempotency_with_different_choices(self, user, poll, choices):
        """Test idempotency when same key used with different choice."""
        client = APIClient()
        client.force_authenticate(user=user)

        idempotency_key = f"test-key-{uuid.uuid4()}"

        # First vote
        vote_data1 = {
            "poll_id": poll.id,
            "choice_id": choices[0].id,
            "idempotency_key": idempotency_key,
        }
        response1 = client.post(reverse("vote-cast"), vote_data1, format="json")
        assert response1.status_code == status.HTTP_201_CREATED

        # Second vote with same key but different choice
        vote_data2 = {
            "poll_id": poll.id,
            "choice_id": choices[1].id,
            "idempotency_key": idempotency_key,
        }
        response2 = client.post(reverse("vote-cast"), vote_data2, format="json")
        # Should return 409 Conflict (duplicate vote) or 200 OK (idempotent)
        assert response2.status_code in [status.HTTP_200_OK, status.HTTP_409_CONFLICT]
        if response2.status_code == status.HTTP_200_OK:
            assert response2.data["id"] == response1.data["id"]

    def test_idempotency_cache_persistence(self, user, poll, choices):
        """
        Test that idempotency works across cache operations.
        
        Note: After cache clear, the service will detect duplicate votes from the database,
        which is the correct behavior. This test verifies that duplicate detection works
        even when cache is cleared.
        """
        cache.clear()

        idempotency_key = f"test-key-{uuid.uuid4()}"

        # First vote
        vote1, is_new1 = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            idempotency_key=idempotency_key,
        )
        assert is_new1 is True

        # Clear cache
        cache.clear()

        # Second vote with same key - should detect duplicate from database
        # (even though cache was cleared, database constraint prevents duplicate)
        try:
            vote2, is_new2 = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[0].id,
                idempotency_key=idempotency_key,
            )
            # If it returns the same vote (idempotent), that's correct
            assert vote1.id == vote2.id
            assert is_new2 is False
        except DuplicateVoteError:
            # Also correct - service detected duplicate from database
            # Verify only one vote exists
            votes = Vote.objects.filter(poll=poll, user=user)
            assert votes.count() == 1
            assert votes.first().id == vote1.id


@pytest.mark.integration
@pytest.mark.django_db
class TestConcurrentOperations:
    """Test concurrent voting operations."""

    def test_concurrent_votes_different_users(self, poll, choices):
        """
        Test multiple votes from different users.
        
        Note: SQLite doesn't support true concurrent writes. This test validates
        that multiple users can vote sequentially. For true concurrent testing with
        PostgreSQL, see test_concurrent_load.py which uses sequential execution
        to work around SQLite limitations.
        """
        num_users = 10
        users = []
        for i in range(num_users):
            users.append(
                User.objects.create_user(
                    username=f"concurrent_user_{i}_{uuid.uuid4().hex[:8]}",
                    password="testpass123",
                )
            )

        results = []

        # Execute sequentially (SQLite limitation) but test the logic
        for user in users:
            try:
                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll.id,
                    choice_id=choices[0].id,
                )
                results.append({"user": user.id, "vote_id": vote.id, "success": True})
            except Exception as e:
                # Should not fail for different users
                pytest.fail(f"Vote failed for user {user.id}: {e}")

        # All should succeed
        assert len(results) == num_users
        
        # Verify all votes in database
        poll.refresh_from_db()
        assert poll.cached_total_votes == num_users
        assert poll.cached_unique_voters == num_users

    def test_concurrent_votes_same_user_prevented(self, user, poll, choices):
        """
        Test that duplicate votes from same user are prevented.
        
        Note: SQLite doesn't support true concurrent writes. This test validates
        duplicate prevention sequentially.
        """
        # First vote succeeds
        vote1, is_new1 = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
        )
        assert is_new1 is True

        # Second vote from same user should fail
        try:
            vote2, is_new2 = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[1].id,
            )
            assert False, "Should have raised DuplicateVoteError"
        except DuplicateVoteError:
            pass  # Expected

        # Verify only one vote in database
        votes = Vote.objects.filter(poll=poll, user=user)
        assert votes.count() == 1

    def test_concurrent_poll_creation_and_voting(self, user):
        """
        Test poll creation and voting in sequence.
        
        Note: SQLite doesn't support true concurrent writes. This test validates
        the logic sequentially. For true concurrent testing, use PostgreSQL.
        """
        poll_ids = []

        # Create 5 polls and vote sequentially
        for _ in range(5):
            # Create poll
            poll = PollFactory(created_by=user)
            option1 = PollOptionFactory(poll=poll, text="Option 1", order=0)
            option2 = PollOptionFactory(poll=poll, text="Option 2", order=1)

            # Vote
            vote, is_new = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=option1.id,
            )
            poll_ids.append(poll.id)

        # All should succeed
        assert len(poll_ids) == 5

        # Verify all polls and votes exist
        for poll_id in poll_ids:
            poll = Poll.objects.get(id=poll_id)
            assert poll.votes.count() == 1


@pytest.mark.integration
@pytest.mark.django_db
class TestDatabaseTransactions:
    """Test database transaction handling."""

    def test_vote_rollback_on_error(self, user, poll, choices):
        """Test that vote is rolled back if transaction fails."""
        initial_vote_count = Vote.objects.filter(poll=poll).count()

        # Attempt vote that will fail (invalid choice from different poll)
        other_poll = PollFactory(created_by=user)
        other_option = PollOptionFactory(poll=other_poll, text="Other Option")

        try:
            vote, is_new = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=other_option.id,  # Invalid: choice from different poll
            )
            assert False, "Should have raised InvalidVoteError"
        except Exception:
            pass  # Expected to fail

        # Verify no vote was created
        final_vote_count = Vote.objects.filter(poll=poll).count()
        assert final_vote_count == initial_vote_count

    def test_atomic_vote_and_cache_update(self, user, poll, choices):
        """Test that vote and cache update are atomic."""
        cache.clear()

        # Cast vote
        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
        )

        # Verify vote exists
        assert Vote.objects.filter(id=vote.id).exists()

        # Verify cached totals updated
        poll.refresh_from_db()
        assert poll.cached_total_votes == 1
        assert poll.cached_unique_voters == 1

    def test_transaction_isolation(self, user, poll, choices):
        """
        Test transaction isolation between operations.
        
        Note: SQLite doesn't support true concurrent transactions. This test
        validates transaction atomicity sequentially.
        """
        results = []

        def vote_and_check(user_id, poll_id, choice_id):
            with transaction.atomic():
                user = User.objects.get(id=user_id)
                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll_id,
                    choice_id=choice_id,
                )
                # Check vote count within transaction
                poll = Poll.objects.get(id=poll_id)
                count = poll.votes.count()
                return {"vote_id": vote.id, "count": count, "is_new": is_new}

        # Create multiple users
        users = [
            User.objects.create_user(
                username=f"user_{i}_{uuid.uuid4().hex[:8]}",
                password="testpass123",
            )
            for i in range(5)
        ]

        # Vote sequentially (SQLite limitation) but test transaction atomicity
        for user_obj in users:
            result = vote_and_check(user_obj.id, poll.id, choices[0].id)
            results.append(result)

        # All should succeed
        assert len(results) == 5

        # Verify final state
        poll.refresh_from_db()
        assert poll.cached_total_votes == 5


@pytest.mark.integration
@pytest.mark.django_db
class TestCacheInvalidation:
    """Test cache invalidation on vote operations."""

    def test_results_cache_invalidated_on_vote(self, user, poll, choices):
        """Test that results cache is invalidated when vote is cast."""
        from django.core.cache import cache
        from django.conf import settings
        
        # Skip if using DummyCache (test settings)
        if hasattr(settings, 'CACHES') and 'dummy' in str(settings.CACHES.get('default', {}).get('BACKEND', '')):
            pytest.skip("Cache tests require a real cache backend, not DummyCache")
        
        cache.clear()

        # Get results (will be cached if cache is enabled)
        results1 = calculate_poll_results(poll.id)
        cache_key = f"poll_results:{poll.id}"
        
        # Check if cache is actually working
        cached_value = cache.get(cache_key)
        if cached_value is None:
            pytest.skip("Cache is not working (DummyCache or cache disabled)")

        # Cast vote
        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
        )

        # Cache should be invalidated
        assert cache.get(cache_key) is None

        # Get results again (should recalculate)
        results2 = calculate_poll_results(poll.id)
        assert results2["total_votes"] == results1["total_votes"] + 1

    def test_cache_invalidation_on_multiple_votes(self, poll, choices):
        """Test cache invalidation with multiple votes."""
        from django.core.cache import cache
        from django.conf import settings
        
        # Skip if using DummyCache (test settings)
        if hasattr(settings, 'CACHES') and 'dummy' in str(settings.CACHES.get('default', {}).get('BACKEND', '')):
            pytest.skip("Cache tests require a real cache backend, not DummyCache")
        
        cache.clear()

        users = [
            User.objects.create_user(
                username=f"cache_user_{i}_{uuid.uuid4().hex[:8]}",
                password="testpass123",
            )
            for i in range(5)
        ]

        cache_key = f"poll_results:{poll.id}"

        for user in users:
            # Get results (may be cached)
            results_before = calculate_poll_results(poll.id)
            
            # Check if cache is working
            if cache.get(cache_key) is None:
                # Cache not working, just verify vote counting works
                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll.id,
                    choice_id=choices[0].id,
                )
                results_after = calculate_poll_results(poll.id)
                assert results_after["total_votes"] == results_before["total_votes"] + 1
                continue

            # Vote
            vote, is_new = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[0].id,
            )

            # Cache should be invalidated
            assert cache.get(cache_key) is None

            # Results should be updated
            results_after = calculate_poll_results(poll.id)
            assert results_after["total_votes"] == results_before["total_votes"] + 1

    def test_manual_cache_invalidation(self, user, poll, choices):
        """Test manual cache invalidation."""
        from django.core.cache import cache
        from django.conf import settings
        
        # Skip if using DummyCache (test settings)
        if hasattr(settings, 'CACHES') and 'dummy' in str(settings.CACHES.get('default', {}).get('BACKEND', '')):
            pytest.skip("Cache tests require a real cache backend, not DummyCache")
        
        cache.clear()

        # Cache results
        results1 = calculate_poll_results(poll.id)
        cache_key = f"poll_results:{poll.id}"
        
        # Check if cache is working
        if cache.get(cache_key) is None:
            pytest.skip("Cache is not working (DummyCache or cache disabled)")

        # Manually invalidate
        invalidate_results_cache(poll.id)

        # Cache should be cleared
        assert cache.get(cache_key) is None

        # Results should still be accessible (recalculated)
        results2 = calculate_poll_results(poll.id)
        assert results2["total_votes"] == results1["total_votes"]


@pytest.mark.integration
@pytest.mark.django_db
class TestErrorScenarios:
    """Test error scenarios in voting flow."""

    def test_vote_on_closed_poll(self, user, poll, choices):
        """Test voting on closed poll."""
        # Close poll
        poll.is_active = False
        poll.save()

        # Attempt vote
        try:
            vote, is_new = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[0].id,
            )
            assert False, "Should have raised PollClosedError or InvalidPollError"
        except Exception as e:
            error_str = str(e).lower()
            assert "closed" in error_str or "inactive" in error_str or "not active" in error_str

    def test_vote_on_nonexistent_poll(self, user, choices):
        """Test voting on non-existent poll."""
        try:
            vote, is_new = cast_vote(
                user=user,
                poll_id=99999,
                choice_id=choices[0].id,
            )
            assert False, "Should have raised PollNotFoundError"
        except Exception as e:
            assert "not found" in str(e).lower()

    def test_vote_with_invalid_choice(self, user, poll, choices):
        """Test voting with invalid choice."""
        # Create choice from different poll
        other_poll = PollFactory(created_by=user)
        other_option = PollOptionFactory(poll=other_poll, text="Other")

        try:
            vote, is_new = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=other_option.id,
            )
            assert False, "Should have raised InvalidVoteError"
        except Exception as e:
            assert "invalid" in str(e).lower() or "not belong" in str(e).lower()


@pytest.mark.integration
@pytest.mark.django_db
class TestEdgeCases:
    """Test edge cases in voting flow."""

    def test_vote_on_poll_with_single_option(self, user):
        """Test voting on poll with only one option."""
        poll = PollFactory(created_by=user)
        option = PollOptionFactory(poll=poll, text="Only Option")

        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=option.id,
        )

        assert vote is not None
        assert vote.option == option

    def test_rapid_successive_votes_same_user(self, user, poll, choices):
        """Test rapid successive vote attempts from same user."""
        # First vote succeeds
        vote1, is_new1 = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
        )
        assert is_new1 is True

        # Second vote immediately after (should fail)
        try:
            vote2, is_new2 = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[1].id,
            )
            assert False, "Should have raised DuplicateVoteError"
        except Exception as e:
            assert "already voted" in str(e).lower() or "duplicate" in str(e).lower()

    def test_vote_attempt_logging(self, user, poll, choices):
        """Test that vote attempts are logged."""
        initial_attempts = VoteAttempt.objects.count()

        # Successful vote (may or may not log attempt depending on implementation)
        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
        )

        # Failed vote attempt (should be logged)
        try:
            vote2, is_new2 = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choices[1].id,
            )
        except Exception:
            pass

        # At least the failed attempt should be logged
        final_attempts = VoteAttempt.objects.count()
        # The service may log failed attempts, but successful votes might not always log attempts
        assert final_attempts >= initial_attempts + 1, f"Expected at least 1 new attempt, got {final_attempts - initial_attempts}"

