"""
Idempotency Stress Tests

Brutally test idempotency guarantees under extreme conditions:
- 1000 simultaneous identical votes
- Network retry simulation
- Concurrent votes from same voter
- Race condition testing
- Database deadlock testing

Tests verify:
- Only 1 vote counted regardless of retries
- No duplicate votes in database
- Proper HTTP status codes
- Performance under retry storm
"""

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from apps.polls.models import Poll, PollOption
from apps.votes.models import Vote
from apps.votes.services import cast_vote
from core.utils.idempotency import generate_idempotency_key
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient


def _is_sqlite():
    """Check if using SQLite database."""
    try:
        return connection.vendor == "sqlite"
    except Exception:
        return True


@pytest.mark.django_db(transaction=True)
@pytest.mark.stress
@pytest.mark.skipif(
    _is_sqlite(),
    reason="Idempotency stress tests require PostgreSQL. SQLite doesn't support concurrent writes.",
)
class TestIdempotencyStress:
    """Brutal stress tests for idempotency guarantees."""

    @pytest.fixture
    def poll_with_choices(self, user):
        """Create a poll with choices for testing."""
        poll = Poll.objects.create(
            title="Stress Test Poll",
            description="Poll for idempotency stress testing",
            created_by=user,
            is_active=True,
            starts_at=timezone.now() - timezone.timedelta(hours=1),
            ends_at=timezone.now() + timezone.timedelta(hours=24),
        )
        choice1 = PollOption.objects.create(poll=poll, text="Choice 1", order=0)
        choice2 = PollOption.objects.create(poll=poll, text="Choice 2", order=1)
        return poll, [choice1, choice2]

    @pytest.fixture
    def request_factory(self):
        """Request factory for creating mock requests."""
        import hashlib

        # Generate a valid 64-character fingerprint (SHA256 hex)
        fingerprint = hashlib.sha256(b"test_fingerprint_123").hexdigest()

        factory = RequestFactory()
        request = factory.post("/api/v1/votes/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        request.META["HTTP_USER_AGENT"] = "StressTest/1.0"
        request.fingerprint = fingerprint
        return request

    def test_1000_simultaneous_identical_votes(self, poll_with_choices, user):
        """
        Test submitting the same vote 1000 times simultaneously.

        Expected: Only 1 vote should be created, all others should return existing vote.
        """
        poll, choices = poll_with_choices
        choice = choices[0]

        # Generate valid 64-character fingerprint
        import hashlib

        fingerprint = hashlib.sha256(b"test_fingerprint_123").hexdigest()

        # Generate idempotency key once
        idempotency_key = generate_idempotency_key(
            user_id=user.id,
            poll_id=poll.id,
            choice_id=choice.id,
            fingerprint=fingerprint,
            ip_address="192.168.1.1",
        )

        # Clear cache to start fresh
        cache.clear()

        # Track results
        results = []
        errors = []

        def submit_vote(attempt_num):
            """Submit a vote and return the result."""
            try:
                # Create a fresh request for each attempt
                factory = RequestFactory()
                request = factory.post("/api/v1/votes/")
                request.META["REMOTE_ADDR"] = "192.168.1.1"
                request.META["HTTP_USER_AGENT"] = "StressTest/1.0"
                fingerprint = hashlib.sha256(b"test_fingerprint_123").hexdigest()
                request.fingerprint = fingerprint

                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll.id,
                    choice_id=choice.id,
                    idempotency_key=idempotency_key,
                    request=request,
                )
                return {
                    "attempt": attempt_num,
                    "vote_id": vote.id,
                    "is_new": is_new,
                    "success": True,
                }
            except Exception as e:
                return {
                    "attempt": attempt_num,
                    "error": str(e),
                    "success": False,
                }

        # Submit 1000 votes simultaneously using ThreadPoolExecutor
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(submit_vote, i) for i in range(1000)]
            for future in as_completed(futures):
                results.append(future.result())
        end_time = time.time()

        # Analyze results
        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        # Debug: Print first few failures if any
        if failed:
            print(f"\nFirst 5 failures: {failed[:5]}")

        # Get unique vote IDs
        unique_vote_ids = set(r["vote_id"] for r in successful if "vote_id" in r)

        # Count new vs existing votes
        new_votes = sum(1 for r in successful if r.get("is_new"))
        existing_votes = sum(1 for r in successful if not r.get("is_new"))

        # Verify at least some votes succeeded
        assert len(successful) > 0, f"No successful votes. Failures: {failed[:10]}"

        # Verify only 1 vote was created
        assert (
            len(unique_vote_ids) == 1
        ), f"Expected 1 unique vote, got {len(unique_vote_ids)}. Successful: {len(successful)}, Failed: {len(failed)}"

        # Verify only 1 new vote, rest are idempotent retries
        assert new_votes == 1, f"Expected 1 new vote, got {new_votes}"
        assert (
            existing_votes == len(successful) - 1
        ), f"Expected {len(successful) - 1} idempotent retries, got {existing_votes}"

        # Allow some failures due to SQLite limitations, but most should succeed
        if len(failed) > 0:
            success_rate = len(successful) / len(results)
            assert (
                success_rate >= 0.9
            ), f"Success rate too low: {success_rate:.2%}. Failures: {failed[:5]}"

        # Verify database has only 1 vote
        vote_count = Vote.objects.filter(poll=poll, user=user).count()
        assert vote_count == 1, f"Expected 1 vote in database, got {vote_count}"

        # Verify performance (should complete in reasonable time)
        elapsed = end_time - start_time
        assert elapsed < 30, f"Test took too long: {elapsed:.2f}s"

        # Verify all votes have same idempotency key
        vote = Vote.objects.get(poll=poll, user=user)
        assert vote.idempotency_key == idempotency_key

        print(
            f"\n✓ 1000 simultaneous votes: {elapsed:.2f}s, {new_votes} new, {existing_votes} idempotent"
        )

    def test_network_retry_simulation(self, poll_with_choices, user):
        """
        Simulate network retries with delays.

        Expected: All retries should return the same vote, no duplicates created.
        """
        poll, choices = poll_with_choices
        choice = choices[0]

        idempotency_key = generate_idempotency_key(
            user_id=user.id,
            poll_id=poll.id,
            choice_id=choice.id,
            fingerprint=hashlib.sha256(b"test_fingerprint_123").hexdigest(),
            ip_address="192.168.1.1",
        )

        cache.clear()

        vote_ids = []
        is_new_flags = []

        # Simulate 50 retries with random delays
        for i in range(50):
            # Create fresh request for each retry
            factory = RequestFactory()
            request = factory.post("/api/v1/votes/")
            request.META["REMOTE_ADDR"] = "192.168.1.1"
            request.META["HTTP_USER_AGENT"] = "StressTest/1.0"
            request.fingerprint = hashlib.sha256(b"test_fingerprint_123").hexdigest()

            vote, is_new = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choice.id,
                idempotency_key=idempotency_key,
                request=request,
            )
            vote_ids.append(vote.id)
            is_new_flags.append(is_new)

            # Simulate network delay (0-100ms)
            time.sleep(0.001 * (i % 10))

        # All votes should be the same
        assert (
            len(set(vote_ids)) == 1
        ), f"Expected 1 unique vote, got {len(set(vote_ids))}"

        # Only first should be new
        assert is_new_flags[0] is True, "First vote should be new"
        assert all(
            not is_new for is_new in is_new_flags[1:]
        ), "All subsequent votes should be idempotent"

        # Database should have only 1 vote
        assert Vote.objects.filter(poll=poll, user=user).count() == 1

        print("\n✓ Network retry simulation: 50 retries, all idempotent")

    def test_concurrent_votes_same_voter_different_choices(
        self, poll_with_choices, user
    ):
        """
        Test concurrent votes from same voter but different choices.

        Expected: Should fail with DuplicateVoteError (user already voted on poll).
        """
        poll, choices = poll_with_choices
        choice1, choice2 = choices[0], choices[1]

        # Create request
        factory = RequestFactory()
        request = factory.post("/api/v1/votes/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        request.META["HTTP_USER_AGENT"] = "StressTest/1.0"
        request.fingerprint = hashlib.sha256(b"test_fingerprint_123").hexdigest()

        # First vote succeeds
        vote1, is_new1 = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choice1.id,
            request=request,
        )
        assert is_new1 is True

        # Second vote with different choice should fail (user already voted)
        from core.exceptions import DuplicateVoteError

        with pytest.raises(DuplicateVoteError):
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choice2.id,
                request=request,
            )

        # Database should have only 1 vote
        assert Vote.objects.filter(poll=poll, user=user).count() == 1

        print("\n✓ Concurrent votes same voter: correctly rejected duplicate")

    def test_race_condition_same_idempotency_key(self, poll_with_choices, user):
        """
        Test race condition where multiple threads try to create vote with same idempotency key.

        Expected: Only 1 vote created, others return existing vote.
        """
        poll, choices = poll_with_choices
        choice = choices[0]

        idempotency_key = generate_idempotency_key(
            user_id=user.id,
            poll_id=poll.id,
            choice_id=choice.id,
            fingerprint=hashlib.sha256(b"test_fingerprint_123").hexdigest(),
            ip_address="192.168.1.1",
        )

        cache.clear()

        # Clear any existing votes
        Vote.objects.filter(poll=poll, user=user).delete()

        results = []
        barrier_reached = [0]

        def submit_vote_with_barrier(attempt_num):
            """Submit vote, all threads start at roughly the same time."""
            barrier_reached[0] += 1
            if barrier_reached[0] < 10:
                # Wait for all threads to be ready
                time.sleep(0.01)

            try:
                # Create fresh request for each attempt
                factory = RequestFactory()
                request = factory.post("/api/v1/votes/")
                request.META["REMOTE_ADDR"] = "192.168.1.1"
                request.META["HTTP_USER_AGENT"] = "StressTest/1.0"
                request.fingerprint = hashlib.sha256(
                    b"test_fingerprint_123"
                ).hexdigest()

                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll.id,
                    choice_id=choice.id,
                    idempotency_key=idempotency_key,
                    request=request,
                )
                return {
                    "attempt": attempt_num,
                    "vote_id": vote.id,
                    "is_new": is_new,
                    "success": True,
                }
            except Exception as e:
                return {
                    "attempt": attempt_num,
                    "error": str(e),
                    "success": False,
                }

        # Submit 10 votes simultaneously (race condition)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(submit_vote_with_barrier, i) for i in range(10)]
            for future in as_completed(futures):
                results.append(future.result())

        successful = [r for r in results if r.get("success")]
        unique_vote_ids = set(r["vote_id"] for r in successful)
        new_votes = sum(1 for r in successful if r.get("is_new"))

        # Only 1 vote should be created
        assert (
            len(unique_vote_ids) == 1
        ), f"Expected 1 unique vote, got {len(unique_vote_ids)}"
        assert new_votes == 1, f"Expected 1 new vote, got {new_votes}"
        assert Vote.objects.filter(poll=poll, user=user).count() == 1

        print("\n✓ Race condition test: 10 simultaneous, 1 created")

    def test_database_deadlock_handling(self, poll_with_choices, user, request_factory):
        """
        Test database deadlock handling under extreme concurrency.

        Expected: System should handle deadlocks gracefully, no data corruption.
        """
        poll, choices = poll_with_choices
        choice = choices[0]

        idempotency_key = generate_idempotency_key(
            user_id=user.id,
            poll_id=poll.id,
            choice_id=choice.id,
            fingerprint=hashlib.sha256(b"test_fingerprint_123").hexdigest(),
            ip_address="192.168.1.1",
        )

        cache.clear()
        Vote.objects.filter(poll=poll, user=user).delete()

        results = []
        deadlocks = []

        def submit_vote_with_retry(attempt_num):
            """Submit vote with retry logic for deadlocks."""
            max_retries = 3
            for retry in range(max_retries):
                try:
                    # Create fresh request for each attempt
                    factory = RequestFactory()
                    request = factory.post("/api/v1/votes/")
                    request.META["REMOTE_ADDR"] = "192.168.1.1"
                    request.META["HTTP_USER_AGENT"] = "StressTest/1.0"
                    request.fingerprint = hashlib.sha256(
                        b"test_fingerprint_123"
                    ).hexdigest()

                    vote, is_new = cast_vote(
                        user=user,
                        poll_id=poll.id,
                        choice_id=choice.id,
                        idempotency_key=idempotency_key,
                        request=request,
                    )
                    return {
                        "attempt": attempt_num,
                        "vote_id": vote.id,
                        "is_new": is_new,
                        "retries": retry,
                        "success": True,
                    }
                except Exception as e:
                    if "deadlock" in str(e).lower() or "lock" in str(e).lower():
                        deadlocks.append(attempt_num)
                        if retry < max_retries - 1:
                            time.sleep(0.01 * (retry + 1))  # Exponential backoff
                            continue
                    return {
                        "attempt": attempt_num,
                        "error": str(e),
                        "retries": retry,
                        "success": False,
                    }
            return {
                "attempt": attempt_num,
                "error": "Max retries exceeded",
                "success": False,
            }

        # Submit 100 votes with high concurrency
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(submit_vote_with_retry, i) for i in range(100)]
            for future in as_completed(futures):
                results.append(future.result())

        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        # Should have high success rate even with deadlocks
        success_rate = len(successful) / len(results)
        assert success_rate >= 0.95, f"Success rate too low: {success_rate:.2%}"

        # All successful votes should be the same
        if successful:
            unique_vote_ids = set(r["vote_id"] for r in successful)
            assert (
                len(unique_vote_ids) == 1
            ), f"Expected 1 unique vote, got {len(unique_vote_ids)}"

        # Database should have only 1 vote
        vote_count = Vote.objects.filter(poll=poll, user=user).count()
        assert vote_count == 1, f"Expected 1 vote in database, got {vote_count}"

        print(
            f"\n✓ Deadlock handling: {len(successful)}/{len(results)} successful, {len(deadlocks)} deadlocks detected"
        )

    def test_idempotency_key_manipulation(self, poll_with_choices, user):
        """
        Test that idempotency keys cannot be manipulated to create duplicates.

        Expected: Different idempotency keys should create different votes (if allowed),
        but same key should always return same vote.
        """
        poll, choices = poll_with_choices
        choice = choices[0]

        # Create vote with specific idempotency key
        fingerprint1 = hashlib.sha256(b"fingerprint1").hexdigest()
        idempotency_key1 = generate_idempotency_key(
            user_id=user.id,
            poll_id=poll.id,
            choice_id=choice.id,
            fingerprint=fingerprint1,
            ip_address="192.168.1.1",
        )

        # Create request
        factory = RequestFactory()
        request = factory.post("/api/v1/votes/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        request.META["HTTP_USER_AGENT"] = "StressTest/1.0"
        request.fingerprint = fingerprint1

        vote1, is_new1 = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choice.id,
            idempotency_key=idempotency_key1,
            request=request,
        )
        assert is_new1 is True

        # Try to create vote with same key (should return existing)
        vote2, is_new2 = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=choice.id,
            idempotency_key=idempotency_key1,
            request=request,
        )
        assert is_new2 is False
        assert vote1.id == vote2.id

        # Try with different key (should fail - user already voted)
        # Note: The system checks for duplicate votes by user+poll before processing idempotency
        # So even with a different idempotency key, it should raise DuplicateVoteError
        fingerprint2 = hashlib.sha256(b"fingerprint2").hexdigest()
        idempotency_key2 = generate_idempotency_key(
            user_id=user.id,
            poll_id=poll.id,
            choice_id=choice.id,
            fingerprint=fingerprint2,  # Different fingerprint
            ip_address="192.168.1.1",
        )

        # Create request with different fingerprint
        request2 = factory.post("/api/v1/votes/")
        request2.META["REMOTE_ADDR"] = "192.168.1.1"
        request2.META["HTTP_USER_AGENT"] = "StressTest/1.0"
        request2.fingerprint = fingerprint2

        from core.exceptions import DuplicateVoteError

        # The system should check user+poll uniqueness before idempotency
        # So this should raise DuplicateVoteError even with different idempotency key
        try:
            vote3, is_new3 = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choice.id,
                idempotency_key=idempotency_key2,
                request=request2,
            )
            # If no exception, verify it returned the existing vote (idempotent behavior)
            # This might happen if idempotency check happens before duplicate check
            assert vote3.id == vote1.id, "Should return existing vote"
            assert is_new3 is False, "Should not be a new vote"
        except DuplicateVoteError:
            # This is the expected behavior - user already voted
            pass

        # Should still have only 1 vote
        assert Vote.objects.filter(poll=poll, user=user).count() == 1

        print("\n✓ Idempotency key manipulation: correctly prevented")

    def test_http_status_codes_under_retry_storm(self, poll_with_choices, user):
        """
        Test proper HTTP status codes when API is hit with retry storm.

        Expected: First request 201, subsequent idempotent requests 200.
        """
        poll, choices = poll_with_choices
        choice = choices[0]

        client = APIClient()
        client.force_authenticate(user=user)

        # Generate idempotency key
        idempotency_key = generate_idempotency_key(
            user_id=user.id,
            poll_id=poll.id,
            choice_id=choice.id,
            fingerprint=hashlib.sha256(b"test_fingerprint").hexdigest(),
            ip_address="192.168.1.1",
        )

        cache.clear()
        Vote.objects.filter(poll=poll, user=user).delete()

        status_codes = []

        def make_request(attempt_num):
            """Make HTTP request with idempotency key."""
            try:
                response = client.post(
                    "/api/v1/votes/cast/",
                    {
                        "poll_id": poll.id,
                        "choice_id": choice.id,
                        "idempotency_key": idempotency_key,
                    },
                    format="json",
                )
                return {
                    "attempt": attempt_num,
                    "status_code": response.status_code,
                }
            except Exception as e:
                # If request fails, return 500
                return {
                    "attempt": attempt_num,
                    "status_code": 500,
                    "error": str(e),
                }

        # Make 20 requests rapidly
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(20)]
            for future in as_completed(futures):
                status_codes.append(future.result())

        # First request should be 201, rest should be 200 (or 201 if not yet processed)
        status_values = [r["status_code"] for r in status_codes]

        # Should have at least one 201 (created)
        assert (
            status.HTTP_201_CREATED in status_values
        ), f"No 201 status codes: {status_values}"

        # All should be success codes (200 or 201)
        assert all(
            sc in [status.HTTP_200_OK, status.HTTP_201_CREATED] for sc in status_values
        ), f"Unexpected status codes: {set(status_values)}"

        # Database should have only 1 vote
        assert Vote.objects.filter(poll=poll, user=user).count() == 1

        print(
            f"\n✓ HTTP status codes: {len([s for s in status_values if s == 201])} created, {len([s for s in status_values if s == 200])} idempotent"
        )

    def test_performance_under_retry_storm(self, poll_with_choices, user):
        """
        Test performance under retry storm (1000 requests in short time).

        Expected: System should handle load gracefully, response times reasonable.
        """
        poll, choices = poll_with_choices
        choice = choices[0]

        idempotency_key = generate_idempotency_key(
            user_id=user.id,
            poll_id=poll.id,
            choice_id=choice.id,
            fingerprint=hashlib.sha256(b"test_fingerprint").hexdigest(),
            ip_address="192.168.1.1",
        )

        cache.clear()
        Vote.objects.filter(poll=poll, user=user).delete()

        response_times = []

        def submit_vote_timed(attempt_num):
            """Submit vote and measure response time."""
            start = time.time()
            try:
                # Create fresh request for each attempt
                factory = RequestFactory()
                request = factory.post("/api/v1/votes/")
                request.META["REMOTE_ADDR"] = "192.168.1.1"
                request.META["HTTP_USER_AGENT"] = "StressTest/1.0"
                request.fingerprint = hashlib.sha256(b"test_fingerprint").hexdigest()

                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll.id,
                    choice_id=choice.id,
                    idempotency_key=idempotency_key,
                    request=request,
                )
                elapsed = time.time() - start
                return {
                    "attempt": attempt_num,
                    "response_time": elapsed,
                    "success": True,
                }
            except Exception as e:
                elapsed = time.time() - start
                return {
                    "attempt": attempt_num,
                    "response_time": elapsed,
                    "error": str(e),
                    "success": False,
                }

        # Submit 1000 votes
        start_total = time.time()
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(submit_vote_timed, i) for i in range(1000)]
            for future in as_completed(futures):
                response_times.append(future.result())
        total_time = time.time() - start_total

        successful = [r for r in response_times if r.get("success")]

        if successful:
            avg_response_time = sum(r["response_time"] for r in successful) / len(
                successful
            )
            max_response_time = max(r["response_time"] for r in successful)
            min_response_time = min(r["response_time"] for r in successful)

            # Average response time should be reasonable
            # Under extreme load (1000 concurrent), allow higher times
            # For PostgreSQL with 1000 concurrent requests, < 1s average is acceptable
            assert (
                avg_response_time < 1.0
            ), f"Average response time too high: {avg_response_time:.3f}s"

            # Max response time should be reasonable (< 10s under extreme load with PostgreSQL)
            # PostgreSQL can have higher latency under concurrent load
            assert (
                max_response_time < 10.0
            ), f"Max response time too high: {max_response_time:.3f}s"

            print(
                f"\n✓ Performance: {len(successful)}/{len(response_times)} successful"
            )
            print(f"  Total time: {total_time:.2f}s")
            print(f"  Avg response: {avg_response_time*1000:.2f}ms")
            print(
                f"  Min: {min_response_time*1000:.2f}ms, Max: {max_response_time*1000:.2f}ms"
            )

        # Verify only 1 vote created
        assert Vote.objects.filter(poll=poll, user=user).count() == 1

    @pytest.mark.skipif(
        settings.CACHES["default"]["BACKEND"]
        == "django.core.cache.backends.dummy.DummyCache",
        reason="Cache consistency tests require a functional cache backend (not DummyCache)",
    )
    def test_cache_consistency_under_load(self, poll_with_choices, user):
        """
        Test that cache and database stay consistent under load.

        Expected: Cache and database should always agree on vote existence.
        """
        poll, choices = poll_with_choices
        choice = choices[0]

        idempotency_key = generate_idempotency_key(
            user_id=user.id,
            poll_id=poll.id,
            choice_id=choice.id,
            fingerprint=hashlib.sha256(b"test_fingerprint").hexdigest(),
            ip_address="192.168.1.1",
        )

        cache.clear()
        Vote.objects.filter(poll=poll, user=user).delete()

        def submit_and_verify(attempt_num):
            """Submit vote and verify cache/database consistency."""
            # Create fresh request for each attempt
            factory = RequestFactory()
            request = factory.post("/api/v1/votes/")
            request.META["REMOTE_ADDR"] = "192.168.1.1"
            request.META["HTTP_USER_AGENT"] = "StressTest/1.0"
            request.fingerprint = hashlib.sha256(b"test_fingerprint").hexdigest()

            vote, is_new = cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=choice.id,
                idempotency_key=idempotency_key,
                request=request,
            )

            # Verify cache
            from core.utils.idempotency import check_idempotency

            is_duplicate, cached_result = check_idempotency(idempotency_key)
            assert is_duplicate is True, "Cache should have idempotency key after vote"
            assert cached_result is not None, "Cache should have result"
            assert cached_result.get("vote_id") == vote.id, "Cache vote_id mismatch"

            # Verify database
            db_vote = Vote.objects.filter(idempotency_key=idempotency_key).first()
            assert db_vote is not None, "Database should have vote"
            assert db_vote.id == vote.id, "Database vote_id mismatch"

            return {"attempt": attempt_num, "vote_id": vote.id, "success": True}

        # Submit 100 votes and verify consistency each time
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(submit_and_verify, i) for i in range(100)]
            results = [future.result() for future in as_completed(futures)]

        # All should succeed
        assert all(r["success"] for r in results), "All consistency checks should pass"

        # All should reference same vote
        unique_vote_ids = set(r["vote_id"] for r in results)
        assert (
            len(unique_vote_ids) == 1
        ), f"Expected 1 unique vote, got {len(unique_vote_ids)}"

        print("\n✓ Cache consistency: 100 checks, all consistent")
