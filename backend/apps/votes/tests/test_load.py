"""
Load tests for voting API endpoints.
Tests concurrent request handling and performance.
"""

import threading
import time

import pytest
from apps.votes.models import Vote
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


def _is_sqlite():
    """Check if using SQLite database."""
    try:
        from django.conf import settings

        return settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    except Exception:
        return True


@pytest.mark.django_db
@pytest.mark.slow
class TestVoteAPILoad:
    """Load tests for voting API."""

    @pytest.mark.skipif(
        _is_sqlite(),
        reason="Concurrent load tests require PostgreSQL, skipped on SQLite due to write lock limitations.",
    )
    def test_1000_concurrent_vote_requests(self, poll, choices):
        """
        Load test: 1000 concurrent vote requests.

        This test simulates 1000 users trying to vote simultaneously
        to verify the system handles concurrency correctly.
        """
        # Create 1000 users
        users = []
        for i in range(1000):
            user = User.objects.create_user(
                username=f"loadtest_user_{i}",
                password="testpass123",
            )
            users.append(user)

        results = {"success": 0, "errors": 0, "duplicates": 0}
        errors_list = []
        lock = threading.Lock()

        def vote_thread(user, poll_id, choice_id):
            """Thread function to cast a vote."""
            client = APIClient()
            client.force_authenticate(user=user)

            url = reverse("vote-cast")
            data = {
                "poll_id": poll_id,
                "choice_id": choice_id,
            }

            try:
                response = client.post(url, data, format="json")
                with lock:
                    if response.status_code == status.HTTP_201_CREATED:
                        results["success"] += 1
                    elif response.status_code == status.HTTP_200_OK:
                        results["success"] += 1  # Idempotent retry is also success
                    elif response.status_code == status.HTTP_409_CONFLICT:
                        results["duplicates"] += 1
                    else:
                        results["errors"] += 1
                        errors_list.append(
                            {
                                "user": user.username,
                                "status": response.status_code,
                                "error": response.data.get("error", "Unknown error"),
                            }
                        )
            except Exception as e:
                with lock:
                    results["errors"] += 1
                    errors_list.append({"user": user.username, "exception": str(e)})

        # Create threads for all users
        threads = []
        start_time = time.time()

        for user in users:
            thread = threading.Thread(
                target=vote_thread,
                args=(user, poll.id, choices[0].id),
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        end_time = time.time()
        elapsed_time = end_time - start_time

        # Verify results
        # All users should have successfully voted (or got duplicate error if they already voted)
        total_processed = results["success"] + results["duplicates"] + results["errors"]

        assert total_processed == 1000, f"Expected 1000 requests, got {total_processed}"

        # Most requests should succeed
        success_rate = results["success"] / total_processed
        assert success_rate >= 0.95, f"Success rate too low: {success_rate:.2%}"

        # Verify votes were created in database
        vote_count = Vote.objects.filter(poll=poll).count()
        assert vote_count == 1000, f"Expected 1000 votes in database, got {vote_count}"

        # Performance check: should complete in reasonable time
        # 1000 concurrent requests should complete in < 30 seconds
        assert elapsed_time < 30, f"Load test took too long: {elapsed_time:.2f} seconds"

        # Log results
        print("\nLoad Test Results:")
        print(f"  Total requests: {total_processed}")
        print(f"  Successful: {results['success']}")
        print(f"  Duplicates: {results['duplicates']}")
        print(f"  Errors: {results['errors']}")
        print(f"  Elapsed time: {elapsed_time:.2f} seconds")
        print(f"  Requests/second: {total_processed / elapsed_time:.2f}")

        if errors_list:
            print(f"\nErrors encountered: {len(errors_list)}")
            for error in errors_list[:10]:  # Print first 10 errors
                print(f"  {error}")

    @pytest.mark.skipif(
        "settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'",
        reason="Concurrent load tests require PostgreSQL, skipped on SQLite due to write lock limitations.",
    )
    def test_concurrent_votes_same_user_prevented(self, user, poll, choices):
        """
        Test that concurrent votes from same user are prevented.
        Simulates race condition where same user tries to vote multiple times.
        """
        results = {"success": 0, "duplicates": 0, "errors": 0}
        lock = threading.Lock()

        def vote_attempt():
            """Attempt to vote."""
            client = APIClient()
            client.force_authenticate(user=user)

            url = reverse("vote-cast")
            data = {
                "poll_id": poll.id,
                "choice_id": choices[0].id,
            }

            try:
                response = client.post(url, data, format="json")
                with lock:
                    if response.status_code == status.HTTP_201_CREATED:
                        results["success"] += 1
                    elif response.status_code == status.HTTP_409_CONFLICT:
                        results["duplicates"] += 1
                    else:
                        results["errors"] += 1
            except Exception:
                with lock:
                    results["errors"] += 1

        # Create 10 concurrent requests from same user
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=vote_attempt)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Only one should succeed, rest should be duplicates
        assert results["success"] == 1, f"Expected 1 success, got {results['success']}"
        assert (
            results["duplicates"] == 9
        ), f"Expected 9 duplicates, got {results['duplicates']}"

        # Verify only one vote in database
        vote_count = Vote.objects.filter(user=user, poll=poll).count()
        assert vote_count == 1, f"Expected 1 vote, got {vote_count}"

    @pytest.mark.skipif(
        "settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'",
        reason="Concurrent load tests require PostgreSQL, skipped on SQLite due to write lock limitations.",
    )
    def test_concurrent_votes_different_users_succeed(self, poll, choices):
        """
        Test that concurrent votes from different users all succeed.
        """
        # Create 100 users
        users = []
        for i in range(100):
            user = User.objects.create_user(
                username=f"concurrent_user_{i}",
                password="testpass123",
            )
            users.append(user)

        results = {"success": 0, "errors": 0}
        lock = threading.Lock()

        def vote_thread(user):
            """Thread function to cast a vote."""
            client = APIClient()
            client.force_authenticate(user=user)

            url = reverse("vote-cast")
            data = {
                "poll_id": poll.id,
                "choice_id": choices[0].id,
            }

            try:
                response = client.post(url, data, format="json")
                with lock:
                    if response.status_code in [
                        status.HTTP_201_CREATED,
                        status.HTTP_200_OK,
                    ]:
                        results["success"] += 1
                    else:
                        results["errors"] += 1
            except Exception:
                with lock:
                    results["errors"] += 1

        # Create threads for all users
        threads = []
        for user in users:
            thread = threading.Thread(target=vote_thread, args=(user,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # All should succeed
        assert (
            results["success"] == 100
        ), f"Expected 100 successes, got {results['success']}"
        assert results["errors"] == 0, f"Expected 0 errors, got {results['errors']}"

        # Verify all votes in database
        vote_count = Vote.objects.filter(poll=poll).count()
        assert vote_count == 100, f"Expected 100 votes, got {vote_count}"
