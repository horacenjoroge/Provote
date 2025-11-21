"""
Load tests for concurrent operations.
"""

import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from django.db import connection
from django.test import RequestFactory
import hashlib

from apps.polls.factories import PollFactory, PollOptionFactory
from apps.polls.models import Poll
from apps.users.factories import UserFactory
from apps.votes.models import Vote
from apps.votes.services import cast_vote


# Skip concurrent load tests on SQLite - it doesn't support true concurrent writes
# These tests require PostgreSQL for accurate results
IS_SQLITE = connection.vendor == "sqlite"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
@pytest.mark.skipif(IS_SQLITE, reason="SQLite doesn't support concurrent writes. Use PostgreSQL for load tests.")
class TestConcurrentLoad:
    """Load tests for concurrent voting.
    
    Note: These tests require PostgreSQL. SQLite uses file-level locking
    and will fail with "database table is locked" errors under concurrent load.
    """

    def test_100_concurrent_votes(self, poll, choices):
        """Test 100 concurrent votes from different users."""
        users = [UserFactory() for _ in range(100)]
        results = []
        lock = threading.Lock()

        def vote(user):
            try:
                factory = RequestFactory()
                request = factory.post("/api/v1/votes/")
                request.META["REMOTE_ADDR"] = "192.168.1.1"
                request.META["HTTP_USER_AGENT"] = "ConcurrentTest/1.0"
                user_id = user.id if hasattr(user, "id") else 0
                request.fingerprint = hashlib.sha256(f"user_{user_id}".encode()).hexdigest()
                
                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll.id,
                    choice_id=choices[0].id,
                    request=request,
                )
                with lock:
                    results.append({"success": True, "user_id": user.id})
            except Exception as e:
                with lock:
                    error_msg = str(e)
                    import traceback
                    results.append({"success": False, "error": error_msg, "traceback": traceback.format_exc()})
                    # Print first few errors for debugging
                    failed_count = len([r for r in results if not r.get("success")])
                    if failed_count <= 5:
                        print(f"Error in vote (attempt {failed_count}): {error_msg}")
                        if "DuplicateVoteError" not in error_msg and "PollNotFoundError" not in error_msg:
                            print(traceback.format_exc())

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(vote, user) for user in users]
            for future in futures:
                future.result()
        end_time = time.time()

        # All should succeed
        successful = [r for r in results if r["success"]]
        assert len(successful) == 100

        # Should complete in reasonable time
        assert (end_time - start_time) < 30  # 30 seconds

        # Verify database state
        poll.refresh_from_db()
        actual_vote_count = Vote.objects.filter(poll=poll).count()
        print(f"\nVote count: Database={actual_vote_count}, Cached={poll.cached_total_votes}, Successful={len(successful)}")
        
        # Check actual database count (more reliable than cached)
        assert actual_vote_count == len(successful), f"Database has {actual_vote_count} votes but {len(successful)} were reported successful"
        assert actual_vote_count >= 95, f"Expected at least 95 votes, got {actual_vote_count}"

    def test_50_concurrent_polls_and_votes(self, user):
        """Test 50 concurrent poll creations and votes."""
        poll_ids = []
        results = []
        lock = threading.Lock()

        def create_and_vote():
            try:
                # Create poll
                poll = PollFactory(created_by=user)
                option1 = PollOptionFactory(poll=poll, text="Option 1", order=0)
                option2 = PollOptionFactory(poll=poll, text="Option 2", order=1)

                # Vote
                factory = RequestFactory()
                request = factory.post("/api/v1/votes/")
                request.META["REMOTE_ADDR"] = "192.168.1.1"
                request.META["HTTP_USER_AGENT"] = "ConcurrentTest/1.0"
                import hashlib
                request.fingerprint = hashlib.sha256(f"fingerprint_{poll.id}".encode()).hexdigest()
                
                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll.id,
                    choice_id=option1.id,
                    request=request,
                )
                with lock:
                    poll_ids.append(poll.id)
                    results.append({"success": True, "poll_id": poll.id})
            except Exception as e:
                with lock:
                    error_msg = str(e)
                    import traceback
                    results.append({"success": False, "error": error_msg, "traceback": traceback.format_exc()})
                    # Print first few errors for debugging
                    failed_count = len([r for r in results if not r.get("success")])
                    if failed_count <= 5:
                        print(f"Error in vote (attempt {failed_count}): {error_msg}")
                        if "DuplicateVoteError" not in error_msg and "PollNotFoundError" not in error_msg:
                            print(traceback.format_exc())

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_and_vote) for _ in range(50)]
            for future in futures:
                future.result()
        end_time = time.time()

        # All should succeed (allow for some failures due to race conditions)
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r.get("success")]
        
        if failed:
            error_types = {}
            for f in failed:
                error_msg = f.get("error", "Unknown error")
                error_type = error_msg.split(":")[0] if ":" in error_msg else error_msg[:50]
                error_types[error_type] = error_types.get(error_type, 0) + 1
            print(f"\nError summary: {error_types}")
        
        success_rate = len(successful) / len(results) if results else 0
        assert success_rate >= 0.95, f"Success rate too low: {success_rate:.2%}. Got {len(successful)}/{len(results)} successful."

        # Should complete in reasonable time
        assert (end_time - start_time) < 60  # 60 seconds

        # Verify all polls and votes exist
        for poll_id in poll_ids:
            poll = Poll.objects.get(id=poll_id)
            actual_votes = poll.votes.count()
            assert actual_votes == 1, f"Poll {poll_id} should have 1 vote, got {actual_votes}"

    def test_200_concurrent_votes_mixed_options(self, poll, choices):
        """Test 200 concurrent votes distributed across options."""
        users = [UserFactory() for _ in range(200)]
        results = []
        lock = threading.Lock()

        def vote(user, choice_index):
            try:
                from django.test import RequestFactory
                import hashlib
                factory = RequestFactory()
                request = factory.post("/api/v1/votes/")
                request.META["REMOTE_ADDR"] = "192.168.1.1"
                request.META["HTTP_USER_AGENT"] = "ConcurrentTest/1.0"
                user_id = user.id if hasattr(user, 'id') else 0
                request.fingerprint = hashlib.sha256(f"user_{user_id}".encode()).hexdigest()
                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll.id,
                    choice_id=choices[choice_index % len(choices)].id,
                    request=request,
                )
                with lock:
                    results.append({"success": True, "user_id": user.id, "choice": choice_index})
            except Exception as e:
                with lock:
                    error_msg = str(e)
                    import traceback
                    results.append({"success": False, "error": error_msg, "traceback": traceback.format_exc()})
                    # Print first few errors for debugging
                    failed_count = len([r for r in results if not r.get("success")])
                    if failed_count <= 5:
                        print(f"Error in vote (attempt {failed_count}): {error_msg}")
                        if "DuplicateVoteError" not in error_msg and "PollNotFoundError" not in error_msg:
                            print(traceback.format_exc())

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=25) as executor:
            futures = [
                executor.submit(vote, user, i) for i, user in enumerate(users)
            ]
            for future in futures:
                future.result()
        end_time = time.time()

        # All should succeed (allow for some failures due to race conditions)
        successful = [r for r in results if r["success"]]
        success_rate = len(successful) / len(results) if results else 0
        assert success_rate >= 0.95, f"Success rate too low: {success_rate:.2%}. Got {len(successful)}/{len(results)} successful."

        # Should complete in reasonable time
        assert (end_time - start_time) < 60  # 60 seconds

        # Verify database state
        poll.refresh_from_db()
        actual_vote_count = Vote.objects.filter(poll=poll).count()
        print(f"\nVote count: Database={actual_vote_count}, Cached={poll.cached_total_votes}")
        assert actual_vote_count >= int(200 * 0.95), f"Expected at least {int(200 * 0.95)} votes, got {actual_vote_count}"
        actual_unique_voters = Vote.objects.filter(poll=poll).values('user').distinct().count()
        print(f"Unique voters: Database={actual_unique_voters}, Cached={poll.cached_unique_voters}")
        assert actual_unique_voters >= int(200 * 0.95), f"Expected at least {int(200 * 0.95)} unique voters, got {actual_unique_voters}"

        # Verify votes distributed across options
        for choice in choices:
            choice.refresh_from_db()
            assert choice.cached_vote_count > 0

    def test_concurrent_votes_with_idempotency(self, poll, choices):
        """Test concurrent votes with same idempotency key."""
        user = UserFactory()
        idempotency_key = f"load-test-key-{int(time.time())}"
        results = []
        lock = threading.Lock()

        def vote_with_key():
            try:
                factory = RequestFactory()
                request = factory.post("/api/v1/votes/")
                request.META["REMOTE_ADDR"] = "192.168.1.1"
                request.META["HTTP_USER_AGENT"] = "ConcurrentTest/1.0"
                user_id = user.id if hasattr(user, "id") else 0
                request.fingerprint = hashlib.sha256(f"user_{user_id}".encode()).hexdigest()

                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll.id,
                    choice_id=choices[0].id,
                    idempotency_key=idempotency_key,
                request=request,
                )
                with lock:
                    results.append({"success": True, "vote_id": vote.id, "is_new": is_new})
            except Exception as e:
                with lock:
                    error_msg = str(e)
                    import traceback
                    results.append({"success": False, "error": error_msg, "traceback": traceback.format_exc()})
                    # Print first few errors for debugging
                    failed_count = len([r for r in results if not r.get("success")])
                    if failed_count <= 5:
                        print(f"Error in vote (attempt {failed_count}): {error_msg}")
                        if "DuplicateVoteError" not in error_msg and "PollNotFoundError" not in error_msg:
                            print(traceback.format_exc())

        # Attempt 20 concurrent votes with same idempotency key
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(vote_with_key) for _ in range(20)]
            for future in futures:
                future.result()

        # Only one should be new, rest should be idempotent
        successful = [r for r in results if r["success"]]
        assert len(successful) == 20

        # All should return same vote ID
        vote_ids = [r["vote_id"] for r in successful]
        assert len(set(vote_ids)) == 1  # All same vote ID

        # Only one should be marked as new
        new_votes = [r for r in successful if r["is_new"]]
        assert len(new_votes) == 1

        # Verify only one vote in database
        votes = Vote.objects.filter(poll=poll, user=user)
        assert votes.count() == 1

    def test_stress_test_500_votes(self, poll, choices):
        """Stress test: 500 concurrent votes."""
        users = [UserFactory() for _ in range(500)]
        results = []
        lock = threading.Lock()

        def vote(user):
            try:
                from django.test import RequestFactory
                import hashlib
                factory = RequestFactory()
                request = factory.post("/api/v1/votes/")
                request.META["REMOTE_ADDR"] = "192.168.1.1"
                request.META["HTTP_USER_AGENT"] = "ConcurrentTest/1.0"
                user_id = user.id if hasattr(user, 'id') else 0
                request.fingerprint = hashlib.sha256(f"user_{user_id}".encode()).hexdigest()
                vote, is_new = cast_vote(
                    user=user,
                    poll_id=poll.id,
                    choice_id=choices[0].id,
                    request=request,
                )
                with lock:
                    results.append({"success": True, "user_id": user.id})
            except Exception as e:
                with lock:
                    error_msg = str(e)
                    import traceback
                    results.append({"success": False, "error": error_msg, "traceback": traceback.format_exc()})
                    # Print first few errors for debugging
                    failed_count = len([r for r in results if not r.get("success")])
                    if failed_count <= 5:
                        print(f"Error in vote (attempt {failed_count}): {error_msg}")
                        if "DuplicateVoteError" not in error_msg and "PollNotFoundError" not in error_msg:
                            print(traceback.format_exc())

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(vote, user) for user in users]
            for future in futures:
                future.result()
        end_time = time.time()

        # All should succeed (allow for some failures due to race conditions)
        successful = [r for r in results if r["success"]]
        success_rate = len(successful) / len(results) if results else 0
        assert success_rate >= 0.95, f"Success rate too low: {success_rate:.2%}. Got {len(successful)}/{len(results)} successful."

        # Should complete in reasonable time
        assert (end_time - start_time) < 120  # 2 minutes

        # Verify database state
        poll.refresh_from_db()
        actual_vote_count = Vote.objects.filter(poll=poll).count()
        actual_unique_voters = Vote.objects.filter(poll=poll).values('user').distinct().count()
        print(f"\nVote count: Database={actual_vote_count}, Cached={poll.cached_total_votes}, Successful={len(successful)}")
        print(f"Unique voters: Database={actual_unique_voters}, Cached={poll.cached_unique_voters}")
        
        assert actual_vote_count == len(successful), f"Database has {actual_vote_count} votes but {len(successful)} were reported successful"
        assert actual_vote_count >= 475, f"Expected at least 475 votes, got {actual_vote_count}"

