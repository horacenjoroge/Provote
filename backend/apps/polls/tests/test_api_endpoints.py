"""
Comprehensive tests for poll CRUD API endpoints.
"""

import pytest
from apps.polls.models import Poll, PollOption
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestPollCreation:
    """Test POST /api/v1/polls/ endpoint."""

    def test_poll_creation_with_options(self, user):
        """Test poll creation with nested options."""
        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-list")
        data = {
            "title": "Test Poll",
            "description": "Test Description",
            "options": [
                {"text": "Option 1", "order": 0},
                {"text": "Option 2", "order": 1},
                {"text": "Option 3", "order": 2},
            ],
        }

        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["title"] == "Test Poll"
        assert len(response.data["options"]) == 3

        # Verify poll and options in database
        poll = Poll.objects.get(id=response.data["id"])
        assert poll.created_by == user
        assert poll.options.count() == 3

    def test_poll_creation_without_options(self, user):
        """Test poll creation without options (as draft)."""
        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-list")
        data = {
            "title": "Test Poll",
            "description": "Test Description",
            "is_draft": True,  # Drafts can be created without options
        }

        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["title"] == "Test Poll"
        assert len(response.data.get("options", [])) == 0
        assert response.data["is_draft"] is True

    def test_poll_creation_requires_authentication(self):
        """Test that poll creation requires authentication."""
        client = APIClient()

        url = reverse("poll-list")
        data = {"title": "Test Poll"}

        response = client.post(url, data, format="json")

        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]


@pytest.mark.django_db
class TestPollListing:
    """Test GET /api/v1/polls/ endpoint."""

    def test_poll_listing_with_pagination(self, user):
        """Test poll listing with pagination."""
        # Create multiple polls
        for i in range(25):
            Poll.objects.create(
                title=f"Poll {i}",
                description=f"Description {i}",
                created_by=user,
            )

        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-list")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data or isinstance(response.data, list)

    def test_poll_filtering_by_creator(self, user):
        """Test poll filtering by creator."""
        user2 = User.objects.create_user(username="user2", password="pass")

        # Create polls by different users
        Poll.objects.create(title="Poll 1", created_by=user)
        Poll.objects.create(title="Poll 2", created_by=user)
        Poll.objects.create(title="Poll 3", created_by=user2)

        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-list")
        response = client.get(url, {"creator": user.username})

        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        assert len(results) == 2
        assert all(poll["created_by"] == user.username for poll in results)

    def test_poll_filtering_by_active_status(self, user):
        """Test poll filtering by active status."""
        Poll.objects.create(title="Active Poll", is_active=True, created_by=user)
        Poll.objects.create(title="Inactive Poll", is_active=False, created_by=user)

        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-list")
        response = client.get(url, {"is_active": "true"})

        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        assert all(poll["is_active"] is True for poll in results)

    def test_poll_filtering_by_is_open(self, user):
        """Test poll filtering by is_open status."""
        from django.utils import timezone

        # Create open poll
        Poll.objects.create(
            title="Open Poll",
            is_active=True,
            starts_at=timezone.now() - timezone.timedelta(days=1),
            created_by=user,
        )

        # Create closed poll
        Poll.objects.create(
            title="Closed Poll",
            is_active=False,
            created_by=user,
        )

        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-list")
        response = client.get(url, {"is_open": "true"})

        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        assert all(poll["is_open"] is True for poll in results)


@pytest.mark.django_db
class TestPollDetail:
    """Test GET /api/v1/polls/{id}/ endpoint."""

    def test_get_poll_detail(self, user, poll):
        """Test getting poll detail."""
        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == poll.id
        assert response.data["title"] == poll.title

    def test_get_poll_detail_includes_options(self, user, poll, choices):
        """Test that poll detail includes options."""
        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "options" in response.data
        assert len(response.data["options"]) == len(choices)


@pytest.mark.django_db
class TestPollUpdate:
    """Test PATCH /api/v1/polls/{id}/ endpoint."""

    def test_poll_update_by_owner(self, user, poll):
        """Test poll update by owner."""
        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-detail", kwargs={"pk": poll.id})
        data = {"title": "Updated Title", "description": "Updated Description"}

        response = client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Updated Title"

        poll.refresh_from_db()
        assert poll.title == "Updated Title"

    def test_poll_update_by_non_owner_rejected(self, poll):
        """Test that poll update by non-owner is rejected."""
        user2 = User.objects.create_user(username="user2", password="pass")
        client = APIClient()
        client.force_authenticate(user=user2)

        url = reverse("poll-detail", kwargs={"pk": poll.id})
        data = {"title": "Hacked Title"}

        response = client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "only update polls you created" in response.data["error"].lower()

    def test_cannot_modify_poll_after_votes_cast(self, user, poll, choices):
        """Test that poll cannot be fully modified after votes cast."""
        from apps.votes.models import Vote

        # Create a vote
        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
        )

        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-detail", kwargs={"pk": poll.id})

        # Try to modify restricted field (title)
        data = {"title": "New Title"}
        response = client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "cannot modify" in response.data["error"].lower()

        # Try to modify allowed field (is_active)
        data = {"is_active": False}
        response = client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        poll.refresh_from_db()
        assert poll.is_active is False


@pytest.mark.django_db
class TestPollDeletion:
    """Test DELETE /api/v1/polls/{id}/ endpoint."""

    def test_poll_deletion_by_owner(self, user, poll):
        """Test poll deletion by owner."""
        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Poll.objects.filter(id=poll.id).exists()

    def test_poll_deletion_by_non_owner_rejected(self, poll):
        """Test that poll deletion by non-owner is rejected."""
        user2 = User.objects.create_user(username="user2", password="pass")
        client = APIClient()
        client.force_authenticate(user=user2)

        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_delete_poll_with_votes(self, user, poll, choices):
        """Test that poll with votes cannot be deleted."""
        from apps.votes.models import Vote

        # Create a vote
        _vote = Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
        )

        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = client.delete(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "cannot delete poll with votes" in response.data["error"].lower()
        assert response.data["vote_count"] == 1

        # Poll should still exist
        assert Poll.objects.filter(id=poll.id).exists()


@pytest.mark.django_db
class TestOptionManagement:
    """Test option management endpoints."""

    def test_add_option_to_poll(self, user, poll):
        """Test adding option to poll."""
        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-add-options", kwargs={"pk": poll.id})
        data = {
            "options": [
                {"text": "New Option 1", "order": 0},
                {"text": "New Option 2", "order": 1},
            ]
        }

        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data) == 2

        # Verify options in database
        poll.refresh_from_db()
        assert poll.options.count() == 2

    def test_add_option_requires_ownership(self, poll):
        """Test that adding option requires ownership."""
        user2 = User.objects.create_user(username="user2", password="pass")
        client = APIClient()
        client.force_authenticate(user=user2)

        url = reverse("poll-add-options", kwargs={"pk": poll.id})
        data = {"options": [{"text": "New Option"}]}

        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_add_option_after_votes_cast(self, user, poll, choices):
        """Test that options cannot be added after votes cast."""
        from apps.votes.models import Vote

        # Create a vote
        Vote.objects.create(
            user=user,
            poll=poll,
            option=choices[0],
            voter_token="token1",
            idempotency_key="key1",
        )

        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-add-options", kwargs={"pk": poll.id})
        data = {"options": [{"text": "New Option"}]}

        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "cannot add options" in response.data["error"].lower()

    def test_remove_option_from_poll(self, user, poll, choices):
        """Test removing option from poll."""
        option = choices[0]

        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse(
            "poll-remove-option", kwargs={"pk": poll.id, "option_id": option.id}
        )
        response = client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not PollOption.objects.filter(id=option.id).exists()

    def test_remove_option_requires_ownership(self, poll, choices):
        """Test that removing option requires ownership."""
        user2 = User.objects.create_user(username="user2", password="pass")
        client = APIClient()
        client.force_authenticate(user=user2)

        url = reverse(
            "poll-remove-option", kwargs={"pk": poll.id, "option_id": choices[0].id}
        )
        response = client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_remove_option_with_votes(self, user, poll, choices):
        """Test that option with votes cannot be removed."""
        from apps.votes.models import Vote

        option = choices[0]

        # Create a vote
        Vote.objects.create(
            user=user,
            poll=poll,
            option=option,
            voter_token="token1",
            idempotency_key="key1",
        )

        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse(
            "poll-remove-option", kwargs={"pk": poll.id, "option_id": option.id}
        )
        response = client.delete(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "cannot delete option with" in response.data["error"].lower()
        assert response.data["vote_count"] == 1

        # Option should still exist
        assert PollOption.objects.filter(id=option.id).exists()

    def test_option_ordering(self, user, poll):
        """Test that options maintain correct order."""
        client = APIClient()
        client.force_authenticate(user=user)

        url = reverse("poll-add-options", kwargs={"pk": poll.id})
        data = {
            "options": [
                {"text": "Option 1", "order": 0},
                {"text": "Option 2", "order": 1},
                {"text": "Option 3", "order": 2},
            ]
        }

        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED

        # Verify order
        poll.refresh_from_db()
        options = poll.options.all()
        for i, option in enumerate(options):
            assert option.order == i


@pytest.mark.django_db
class TestPollAPIIntegration:
    """Integration tests for poll API."""

    def test_full_poll_lifecycle(self, user):
        """Test complete poll lifecycle: create, update, delete."""
        client = APIClient()
        client.force_authenticate(user=user)

        # 1. Create poll with options
        url = reverse("poll-list")
        data = {
            "title": "Lifecycle Poll",
            "description": "Test lifecycle",
            "options": [
                {"text": "Option 1"},
                {"text": "Option 2"},
            ],
        }
        response = client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        poll_id = response.data["id"]

        # 2. Get poll detail
        url = reverse("poll-detail", kwargs={"pk": poll_id})
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK

        # 3. Update poll
        data = {"title": "Updated Lifecycle Poll"}
        response = client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK

        # 4. Add more options
        url = reverse("poll-add-options", kwargs={"pk": poll_id})
        data = {"options": [{"text": "Option 3"}]}
        response = client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # 5. Delete poll
        url = reverse("poll-detail", kwargs={"pk": poll_id})
        response = client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify poll is deleted
        assert not Poll.objects.filter(id=poll_id).exists()
