"""
Tests for poll cloning functionality.
"""

import pytest
from apps.polls.models import Poll, PollOption
from apps.polls.services import clone_poll
from apps.votes.models import Vote
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestPollCloning:
    """Test poll cloning functionality."""

    def test_clone_poll_with_all_data(self, user):
        """Test that poll is cloned with all options and data."""
        # Create original poll with options
        original_poll = Poll.objects.create(
            title="Original Poll",
            description="Original description",
            created_by=user,
            settings={"show_results_during_voting": True},
            security_rules={"require_authentication": False},
        )

        option1 = PollOption.objects.create(
            poll=original_poll, text="Option 1", order=0
        )
        option2 = PollOption.objects.create(
            poll=original_poll, text="Option 2", order=1
        )
        option3 = PollOption.objects.create(
            poll=original_poll, text="Option 3", order=2
        )

        # Clone the poll
        cloned_poll = clone_poll(
            poll=original_poll,
            user=user,
        )

        # Verify cloned poll
        assert cloned_poll.title == "Copy of Original Poll"
        assert cloned_poll.description == original_poll.description
        assert cloned_poll.created_by == user
        assert cloned_poll.is_draft is True
        assert cloned_poll.is_active is False
        assert cloned_poll.cached_total_votes == 0
        assert cloned_poll.cached_unique_voters == 0

        # Verify options are cloned
        cloned_options = cloned_poll.options.all().order_by("order")
        assert cloned_options.count() == 3
        assert cloned_options[0].text == "Option 1"
        assert cloned_options[0].order == 0
        assert cloned_options[0].cached_vote_count == 0
        assert cloned_options[1].text == "Option 2"
        assert cloned_options[1].order == 1
        assert cloned_options[2].text == "Option 3"
        assert cloned_options[2].order == 2

        # Verify settings are cloned
        assert cloned_poll.settings == original_poll.settings
        assert cloned_poll.security_rules == original_poll.security_rules

    def test_clone_poll_vote_counts_reset(self, user):
        """Test that vote counts are reset in cloned poll."""
        # Create original poll with votes
        original_poll = Poll.objects.create(
            title="Poll with Votes",
            created_by=user,
        )

        option1 = PollOption.objects.create(
            poll=original_poll, text="Option 1", order=0
        )
        option2 = PollOption.objects.create(
            poll=original_poll, text="Option 2", order=1
        )

        # Create some votes
        user1 = User.objects.create_user(username="voter1", password="pass")
        user2 = User.objects.create_user(username="voter2", password="pass")

        Vote.objects.create(
            poll=original_poll,
            option=option1,
            user=user1,
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )
        Vote.objects.create(
            poll=original_poll,
            option=option1,
            user=user2,
            voter_token="token2",
            idempotency_key="key2",
            is_valid=True,
        )

        # Update cached counts
        original_poll.update_cached_totals()
        option1.update_cached_vote_count()

        # Verify original has votes
        assert original_poll.cached_total_votes == 2
        assert option1.cached_vote_count == 2

        # Clone the poll
        cloned_poll = clone_poll(poll=original_poll, user=user)

        # Verify vote counts are reset
        assert cloned_poll.cached_total_votes == 0
        assert cloned_poll.cached_unique_voters == 0

        clonedoption1 = cloned_poll.options.get(text="Option 1")
        assert cloned_option1.cached_vote_count == 0

        # Verify original poll is unchanged
        original_poll.refresh_from_db()
        assert original_poll.cached_total_votes == 2

    def test_clone_poll_options_preserved(self, user):
        """Test that all options are preserved in cloned poll."""
        # Create poll with many options
        original_poll = Poll.objects.create(
            title="Multi-Option Poll",
            created_by=user,
        )

        options_texts = [f"Option {i}" for i in range(1, 11)]
        for i, text in enumerate(options_texts):
            PollOption.objects.create(poll=original_poll, text=text, order=i)

        # Clone the poll
        cloned_poll = clone_poll(poll=original_poll, user=user)

        # Verify all options are preserved
        cloned_options = cloned_poll.options.all().order_by("order")
        assert cloned_options.count() == 10

        for i, option in enumerate(cloned_options):
            assert option.text == options_texts[i]
            assert option.order == i

    def test_clone_poll_independent(self, user):
        """Test that cloned poll is independent from original."""
        # Create original poll
        original_poll = Poll.objects.create(
            title="Original",
            description="Original description",
            created_by=user,
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)
        PollOption.objects.create(poll=original_poll, text="Option 2", order=1)

        # Clone the poll
        cloned_poll = clone_poll(poll=original_poll, user=user)

        # Modify cloned poll
        cloned_poll.title = "Modified Clone"
        cloned_poll.description = "Modified description"
        cloned_poll.save()

        # Add option to cloned poll
        PollOption.objects.create(poll=cloned_poll, text="New Option", order=2)

        # Verify original poll is unchanged
        original_poll.refresh_from_db()
        assert original_poll.title == "Original"
        assert original_poll.description == "Original description"
        assert original_poll.options.count() == 2

        # Verify cloned poll has changes
        assert cloned_poll.title == "Modified Clone"
        assert cloned_poll.description == "Modified description"
        assert cloned_poll.options.count() == 3

    def test_clone_poll_custom_title(self, user):
        """Test cloning with custom title."""
        original_poll = Poll.objects.create(
            title="Original Poll",
            created_by=user,
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)
        PollOption.objects.create(poll=original_poll, text="Option 2", order=1)

        # Clone with custom title
        cloned_poll = clone_poll(
            poll=original_poll,
            user=user,
            new_title="My Custom Title",
        )

        assert cloned_poll.title == "My Custom Title"
        assert cloned_poll.title != "Copy of Original Poll"

    def test_clone_poll_without_settings(self, user):
        """Test cloning without settings."""
        original_poll = Poll.objects.create(
            title="Original",
            created_by=user,
            settings={"key": "value"},
            security_rules={"rule": "value"},
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)
        PollOption.objects.create(poll=original_poll, text="Option 2", order=1)

        # Clone without settings
        cloned_poll = clone_poll(
            poll=original_poll,
            user=user,
            clone_settings=False,
            clone_security_rules=False,
        )

        assert cloned_poll.settings == {}
        assert cloned_poll.security_rules == {}

    def test_clone_poll_with_settings(self, user):
        """Test cloning with settings."""
        original_poll = Poll.objects.create(
            title="Original",
            created_by=user,
            settings={
                "show_results_during_voting": True,
                "allow_multiple_votes": False,
            },
            security_rules={"require_authentication": True},
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)
        PollOption.objects.create(poll=original_poll, text="Option 2", order=1)

        # Clone with settings
        cloned_poll = clone_poll(
            poll=original_poll,
            user=user,
            clone_settings=True,
            clone_security_rules=True,
        )

        assert cloned_poll.settings == original_poll.settings
        assert cloned_poll.security_rules == original_poll.security_rules

    def test_clone_poll_as_published(self, user):
        """Test cloning poll as published (not draft)."""
        original_poll = Poll.objects.create(
            title="Original",
            created_by=user,
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)
        PollOption.objects.create(poll=original_poll, text="Option 2", order=1)

        # Clone as published
        cloned_poll = clone_poll(
            poll=original_poll,
            user=user,
            is_draft=False,
        )

        assert cloned_poll.is_draft is False

    def test_clone_poll_no_options_fails(self, user):
        """Test that cloning poll without options fails."""
        original_poll = Poll.objects.create(
            title="Poll Without Options",
            created_by=user,
        )

        # Try to clone poll without options
        with pytest.raises(ValueError, match="no options"):
            clone_poll(poll=original_poll, user=user)

    def test_clone_poll_title_truncation(self, user):
        """Test that long titles are truncated when adding 'Copy of' prefix."""
        # Create poll with very long title
        long_title = "A" * 195  # 195 characters
        original_poll = Poll.objects.create(
            title=long_title,
            created_by=user,
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)
        PollOption.objects.create(poll=original_poll, text="Option 2", order=1)

        # Clone without custom title (should truncate)
        cloned_poll = clone_poll(poll=original_poll, user=user)

        assert len(cloned_poll.title) <= 200
        assert cloned_poll.title.startswith("Copy of")


@pytest.mark.django_db
class TestPollCloningAPI:
    """Test poll cloning API endpoint."""

    def test_clone_poll_via_api(self, user):
        """Test cloning poll via API endpoint."""
        # Create original poll
        original_poll = Poll.objects.create(
            title="Original Poll",
            description="Original description",
            created_by=user,
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)
        PollOption.objects.create(poll=original_poll, text="Option 2", order=1)

        client = APIClient()
        client.force_authenticate(user=user)

        # Clone via API
        response = client.post(f"/api/v1/polls/{original_poll.id}/clone/")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["message"] == "Poll cloned successfully"
        assert "poll" in response.data

        cloned_data = response.data["poll"]
        assert cloned_data["title"] == "Copy of Original Poll"
        assert cloned_data["description"] == original_poll.description
        assert cloned_data["is_draft"] is True
        assert len(cloned_data["options"]) == 2

    def test_clone_poll_with_custom_title_via_api(self, user):
        """Test cloning poll with custom title via API."""
        original_poll = Poll.objects.create(
            title="Original",
            created_by=user,
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)
        PollOption.objects.create(poll=original_poll, text="Option 2", order=1)

        client = APIClient()
        client.force_authenticate(user=user)

        # Clone with custom title
        response = client.post(
            f"/api/v1/polls/{original_poll.id}/clone/",
            {"new_title": "My Custom Clone"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["poll"]["title"] == "My Custom Clone"

    def test_clone_poll_with_options_via_api(self, user):
        """Test cloning poll with options preserved via API."""
        original_poll = Poll.objects.create(
            title="Original",
            created_by=user,
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)
        PollOption.objects.create(poll=original_poll, text="Option 2", order=1)
        PollOption.objects.create(poll=original_poll, text="Option 3", order=2)

        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(f"/api/v1/polls/{original_poll.id}/clone/")

        assert response.status_code == status.HTTP_201_CREATED
        cloned_options = response.data["poll"]["options"]
        assert len(cloned_options) == 3
        assert cloned_options[0]["text"] == "Option 1"
        assert cloned_options[1]["text"] == "Option 2"
        assert cloned_options[2]["text"] == "Option 3"

    def test_clone_poll_vote_counts_reset_via_api(self, user):
        """Test that vote counts are reset in cloned poll via API."""
        # Create poll with votes
        original_poll = Poll.objects.create(
            title="Poll with Votes",
            created_by=user,
        )

        option1 = PollOption.objects.create(
            poll=original_poll, text="Option 1", order=0
        )

        # Create votes
        user1 = User.objects.create_user(username="voter1", password="pass")
        Vote.objects.create(
            poll=original_poll,
            option=option1,
            user=user1,
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        original_poll.update_cached_totals()

        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(f"/api/v1/polls/{original_poll.id}/clone/")

        assert response.status_code == status.HTTP_201_CREATED
        cloned_data = response.data["poll"]
        assert cloned_data["total_votes"] == 0
        assert cloned_data["unique_voters"] == 0

    def test_clone_poll_independent_via_api(self, user):
        """Test that cloned poll is independent via API."""
        original_poll = Poll.objects.create(
            title="Original",
            created_by=user,
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)

        client = APIClient()
        client.force_authenticate(user=user)

        # Clone the poll
        response = client.post(f"/api/v1/polls/{original_poll.id}/clone/")
        assert response.status_code == status.HTTP_201_CREATED

        cloned_poll_id = response.data["poll"]["id"]

        # Modify cloned poll
        update_response = client.patch(
            f"/api/v1/polls/{cloned_poll_id}/",
            {"title": "Modified Clone"},
            format="json",
        )
        assert update_response.status_code == status.HTTP_200_OK

        # Verify original is unchanged
        original_response = client.get(f"/api/v1/polls/{original_poll.id}/")
        assert original_response.data["title"] == "Original"

    def test_clone_poll_without_options_fails_via_api(self, user):
        """Test that cloning poll without options fails via API."""
        original_poll = Poll.objects.create(
            title="Poll Without Options",
            created_by=user,
        )

        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(f"/api/v1/polls/{original_poll.id}/clone/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "no options" in response.data["error"].lower()

    def test_clone_poll_requires_authentication(self, user):
        """Test that cloning requires authentication."""
        original_poll = Poll.objects.create(
            title="Original",
            created_by=user,
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)
        PollOption.objects.create(poll=original_poll, text="Option 2", order=1)

        client = APIClient()
        # Not authenticated

        response = client.post(f"/api/v1/polls/{original_poll.id}/clone/")

        # Permission class returns 403 for unauthenticated users
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_clone_poll_with_settings_options_via_api(self, user):
        """Test cloning with settings options via API."""
        original_poll = Poll.objects.create(
            title="Original",
            created_by=user,
            settings={"key": "value"},
            security_rules={"rule": "value"},
        )

        PollOption.objects.create(poll=original_poll, text="Option 1", order=0)
        PollOption.objects.create(poll=original_poll, text="Option 2", order=1)

        client = APIClient()
        client.force_authenticate(user=user)

        # Clone without settings
        response = client.post(
            f"/api/v1/polls/{original_poll.id}/clone/",
            {
                "clone_settings": False,
                "clone_security_rules": False,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        cloned_data = response.data["poll"]
        assert cloned_data["settings"] == {}
        assert cloned_data["security_rules"] == {}
