"""
Tests for Poll views.
"""

import pytest
from apps.polls.models import Poll


@pytest.mark.unit
class TestPollViewSet:
    """Test PollViewSet."""

    def test_list_polls(self, authenticated_client, poll):
        """Test listing polls."""
        response = authenticated_client.get("/api/v1/polls/")
        assert response.status_code == 200
        assert len(response.data["results"]) >= 1

    def test_retrieve_poll(self, authenticated_client, poll):
        """Test retrieving a poll."""
        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/")
        assert response.status_code == 200
        assert response.data["title"] == poll.title

    def test_create_poll(self, authenticated_client, user):
        """Test creating a poll."""
        data = {
            "title": "New Poll",
            "description": "A new poll",
            "is_active": True,
        }
        response = authenticated_client.post("/api/v1/polls/", data)
        assert response.status_code == 201
        assert Poll.objects.filter(title="New Poll").exists()

    def test_poll_results(self, authenticated_client, poll, choices):
        """Test getting poll results."""
        response = authenticated_client.get(f"/api/v1/polls/{poll.id}/results/")
        assert response.status_code == 200
        assert "results" in response.data
