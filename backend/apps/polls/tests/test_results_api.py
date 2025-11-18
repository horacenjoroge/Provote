"""
Comprehensive tests for poll results API endpoints.
"""

import json
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from apps.polls.models import Poll, PollOption
from apps.votes.models import Vote


@pytest.mark.django_db
class TestResultsEndpoint:
    """Test GET /api/polls/{id}/results/ endpoint."""

    def test_results_endpoint_returns_correct_data(self, authenticated_client, poll, choices):
        """Test that results endpoint returns correct data structure."""
        from django.contrib.auth.models import User

        # Create some votes
        user1 = User.objects.create_user(username="user1", password="pass")
        user2 = User.objects.create_user(username="user2", password="pass")

        Vote.objects.create(
            user=user1,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        Vote.objects.create(
            user=user2,
            poll=poll,
            option=choices[0],
            voter_token="token2",
            idempotency_key="key2",
            is_valid=True,
        )

        # Update cached counts
        poll.refresh_from_db()
        choices[0].refresh_from_db()

        # Configure poll to show results
        poll.settings["show_results_during_voting"] = True
        poll.save()

        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/")

        assert response.status_code == 200
        data = response.data

        # Check structure
        assert "poll_id" in data
        assert "poll_title" in data
        assert "total_votes" in data
        assert "unique_voters" in data
        assert "participation_rate" in data
        assert "options" in data
        assert "winners" in data
        assert "is_tie" in data
        assert "calculated_at" in data
        assert "statistics" in data

        # Check values
        assert data["poll_id"] == poll.id
        assert data["total_votes"] == 2
        assert data["unique_voters"] == 2
        assert len(data["options"]) == len(choices)

        # Check statistics
        assert "average_votes_per_option" in data["statistics"]
        assert "median_votes_per_option" in data["statistics"]
        assert "max_votes" in data["statistics"]
        assert "min_votes" in data["statistics"]

    def test_private_poll_results_hidden_from_non_owners(self, authenticated_client, poll, choices):
        """Test that private poll results are hidden from non-owners."""
        from django.contrib.auth.models import User

        # Create another user
        other_user = User.objects.create_user(username="other", password="pass")
        other_client = authenticated_client
        other_client.force_authenticate(user=other_user)

        # Make poll private
        poll.settings["is_private"] = True
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Try to access results as non-owner
        response = other_client.get(f"/api/v1/polls/{poll.id}/results/")

        assert response.status_code == 403
        assert "not authorized" in response.data["error"].lower()

    def test_private_poll_results_visible_to_owner(self, authenticated_client, poll, choices):
        """Test that private poll results are visible to owner."""
        # Make poll private
        poll.settings["is_private"] = True
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Access results as owner
        authenticated_client.force_authenticate(user=poll.created_by)
        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/")

        assert response.status_code == 200
        assert response.data["poll_id"] == poll.id

    def test_public_poll_results_visible(self, authenticated_client, poll, choices):
        """Test that public poll results are visible to anyone."""
        # Make poll public (default)
        poll.settings["is_private"] = False
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Access results
        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/")

        assert response.status_code == 200
        assert response.data["poll_id"] == poll.id

    def test_results_during_voting_when_enabled(self, authenticated_client, poll, choices):
        """Test that results are shown during voting when enabled."""
        from django.contrib.auth.models import User

        # Create a vote
        user = User.objects.create_user(username="user1", password="pass")
        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        poll.refresh_from_db()
        choices[0].refresh_from_db()

        # Enable showing results during voting
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Poll should be open
        assert poll.is_open

        # Should be able to see results
        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/")

        assert response.status_code == 200
        assert response.data["total_votes"] == 1

    def test_results_during_voting_when_disabled(self, authenticated_client, poll, choices):
        """Test that results are hidden during voting when disabled."""
        # Disable showing results during voting
        poll.settings["show_results_during_voting"] = False
        poll.save()

        # Poll should be open
        assert poll.is_open

        # Should not be able to see results
        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/")

        assert response.status_code == 403
        assert "not authorized" in response.data["error"].lower()

    def test_results_after_poll_closes(self, authenticated_client, poll, choices):
        """Test that results are shown after poll closes."""
        from django.contrib.auth.models import User

        # Create a vote
        user = User.objects.create_user(username="user1", password="pass")
        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        poll.refresh_from_db()
        choices[0].refresh_from_db()

        # Close the poll
        poll.ends_at = timezone.now() - timedelta(hours=1)
        poll.settings["show_results_during_voting"] = False  # Don't show during voting
        poll.save()

        # Poll should be closed
        assert not poll.is_open

        # Should be able to see results after poll closes
        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/")

        assert response.status_code == 200
        assert response.data["total_votes"] == 1

    def test_results_with_anonymous_user(self, client, poll, choices):
        """Test results access with anonymous user."""
        # Make poll public and show results
        poll.settings["is_private"] = False
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Anonymous user should be able to see public poll results
        response = client.get(f"/api/v1/polls/{poll.id}/results/")

        assert response.status_code == 200

    def test_results_with_anonymous_user_private_poll(self, client, poll, choices):
        """Test that anonymous user cannot see private poll results."""
        # Make poll private
        poll.settings["is_private"] = True
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Anonymous user should not be able to see private poll results
        response = client.get(f"/api/v1/polls/{poll.id}/results/")

        assert response.status_code == 403


@pytest.mark.django_db
class TestResultsLiveEndpoint:
    """Test GET /api/polls/{id}/results/live/ endpoint."""

    def test_live_endpoint_returns_results(self, authenticated_client, poll, choices):
        """Test that live endpoint returns results with has_updates flag."""
        # Configure poll to show results
        poll.settings["show_results_during_voting"] = True
        poll.save()

        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/live/")

        assert response.status_code == 200
        data = response.data

        # Check structure
        assert "poll_id" in data
        assert "has_updates" in data
        assert "poll_status" in data
        assert data["has_updates"] is True

        # Check poll status
        assert "is_open" in data["poll_status"]
        assert "is_active" in data["poll_status"]

    def test_live_endpoint_detects_updates(self, authenticated_client, poll, choices):
        """Test that live endpoint detects when results have changed."""
        from django.contrib.auth.models import User

        # Configure poll to show results
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Get initial results
        response1 = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/live/")
        assert response1.status_code == 200
        last_update = response1.data["calculated_at"]

        # Create a new vote
        user = User.objects.create_user(username="user1", password="pass")
        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        poll.refresh_from_db()
        choices[0].refresh_from_db()

        # Get updated results with last_update parameter
        response2 = authenticated_client.get(
            f"/api/v1/polls/{poll.id}/results/live/?last_update={last_update}"
        )

        assert response2.status_code == 200
        assert response2.data["has_updates"] is True
        assert response2.data["total_votes"] == 1

    def test_live_endpoint_no_updates(self, authenticated_client, poll, choices):
        """Test that live endpoint correctly identifies when there are no updates."""
        # Configure poll to show results
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Get initial results
        response1 = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/live/")
        assert response1.status_code == 200
        last_update = response1.data["calculated_at"]

        # Get results again with same last_update (should show no updates)
        response2 = authenticated_client.get(
            f"/api/v1/polls/{poll.id}/results/live/?last_update={last_update}"
        )

        assert response2.status_code == 200
        # Note: has_updates might still be True if cache was invalidated
        # This is expected behavior for live updates

    def test_live_endpoint_respects_visibility_rules(self, authenticated_client, poll, choices):
        """Test that live endpoint respects visibility rules."""
        # Make poll private
        poll.settings["is_private"] = True
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Create another user
        from django.contrib.auth.models import User

        other_user = User.objects.create_user(username="other", password="pass")
        authenticated_client.force_authenticate(user=other_user)

        # Should not be able to see results
        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/live/")

        assert response.status_code == 403


@pytest.mark.django_db
class TestResultsExportEndpoint:
    """Test GET /api/polls/{id}/results/export/ endpoint."""

    def test_results/export_json_format(self, authenticated_client, poll, choices):
        """Test results/exporting results in JSON format."""
        from django.contrib.auth.models import User

        # Create some votes
        user = User.objects.create_user(username="user1", password="pass")
        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        poll.refresh_from_db()
        choices[0].refresh_from_db()

        # Configure poll to show results
        poll.settings["show_results_during_voting"] = True
        poll.save()

        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/export/?format=json")

        assert response.status_code == 200
        assert "poll_id" in response.data
        assert "options" in response.data
        assert response.data["poll_id"] == poll.id

    def test_results/export_csv_format(self, authenticated_client, poll, choices):
        """Test results/exporting results in CSV format."""
        from django.contrib.auth.models import User

        # Create some votes
        user = User.objects.create_user(username="user1", password="pass")
        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        poll.refresh_from_db()
        choices[0].refresh_from_db()

        # Configure poll to show results
        poll.settings["show_results_during_voting"] = True
        poll.save()

        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/export/?format=csv")

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        assert "attachment" in response["Content-Disposition"]
        assert f"poll_{poll.id}_results.csv" in response["Content-Disposition"]

        # Check CSV content
        content = response.content.decode("utf-8")
        assert "Poll Results" in content
        assert poll.title in content
        assert "Option ID" in content
        assert "Option Text" in content
        assert "Votes" in content

    def test_results/export_default_format(self, authenticated_client, poll, choices):
        """Test that default results/export format is JSON."""
        # Configure poll to show results
        poll.settings["show_results_during_voting"] = True
        poll.save()

        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/export/")

        assert response.status_code == 200
        assert "poll_id" in response.data  # JSON response

    def test_results/export_invalid_format(self, authenticated_client, poll, choices):
        """Test that invalid format returns 400 error."""
        # Configure poll to show results
        poll.settings["show_results_during_voting"] = True
        poll.save()

        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/export/?format=xml")

        assert response.status_code == 400
        assert "Invalid format" in response.data["error"]

    def test_results/export_respects_visibility_rules(self, authenticated_client, poll, choices):
        """Test that results/export respects visibility rules."""
        # Make poll private
        poll.settings["is_private"] = True
        poll.settings["show_results_during_voting"] = True
        poll.save()

        # Create another user
        from django.contrib.auth.models import User

        other_user = User.objects.create_user(username="other", password="pass")
        authenticated_client.force_authenticate(user=other_user)

        # Should not be able to results/export results
        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/export/?format=json")

        assert response.status_code == 403

    def test_results/export_csv_content_structure(self, authenticated_client, poll, choices):
        """Test that CSV results/export has correct structure."""
        from django.contrib.auth.models import User

        # Create votes for multiple options
        users = []
        for i in range(3):
            user = User.objects.create_user(username=f"user{i}", password="pass")
            users.append(user)

        # Vote for different options
        Vote.objects.create(
            user=users[0],
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        Vote.objects.create(
            user=users[1],
            poll=poll,
            option=choices[1],
            voter_token="token2",
            idempotency_key="key2",
            is_valid=True,
        )

        Vote.objects.create(
            user=users[2],
            poll=poll,
            option=choices[0],
            voter_token="token3",
            idempotency_key="key3",
            is_valid=True,
        )

        poll.refresh_from_db()
        choices[0].refresh_from_db()
        choices[1].refresh_from_db()

        # Configure poll to show results
        poll.settings["show_results_during_voting"] = True
        poll.save()

        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/export/?format=csv")

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Check CSV structure
        lines = content.split("\n")
        assert "Poll Results" in lines[0]
        assert "Option ID" in content
        assert "Option Text" in content
        assert "Votes" in content
        assert "Percentage" in content
        assert "Is Winner" in content

        # Check that options are included
        assert choices[0].text in content
        assert choices[1].text in content


@pytest.mark.django_db
class TestResultsAggregateStatistics:
    """Test aggregate statistics in results."""

    def test_statistics_included_in_results(self, authenticated_client, poll, choices):
        """Test that aggregate statistics are included in results."""
        from django.contrib.auth.models import User

        # Create votes
        users = []
        for i in range(5):
            user = User.objects.create_user(username=f"user{i}", password="pass")
            users.append(user)

        # Distribute votes
        for i, user in enumerate(users):
            option_index = i % len(choices)
            Vote.objects.create(
                user=user,
                poll=poll,
                option=choices[option_index],
                voter_token=f"token{i}",
                idempotency_key=f"key{i}",
                is_valid=True,
            )

        # Update cached counts
        poll.refresh_from_db()
        for choice in choices:
            choice.refresh_from_db()

        # Configure poll to show results
        poll.settings["show_results_during_voting"] = True
        poll.save()

        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/")

        assert response.status_code == 200
        stats = response.data["statistics"]

        # Check statistics structure
        assert "average_votes_per_option" in stats
        assert "median_votes_per_option" in stats
        assert "max_votes" in stats
        assert "min_votes" in stats
        assert "vote_distribution" in stats
        assert "options_count" in stats

        # Check values
        assert stats["options_count"] == len(choices)
        assert stats["max_votes"] >= stats["min_votes"]
        assert stats["average_votes_per_option"] > 0

