"""
Tests for follow system.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import Follow


@pytest.fixture
def user1():
    """Create first test user."""
    return User.objects.create_user(
        username="user1", email="user1@example.com", password="testpass123"
    )


@pytest.fixture
def user2():
    """Create second test user."""
    return User.objects.create_user(
        username="user2", email="user2@example.com", password="testpass123"
    )


@pytest.fixture
def user3():
    """Create third test user."""
    return User.objects.create_user(
        username="user3", email="user3@example.com", password="testpass123"
    )


@pytest.fixture
def authenticated_client(user1):
    """Create an authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user1)
    return client


@pytest.mark.django_db
class TestFollowModel:
    """Test Follow model."""

    def test_create_follow(self, user1, user2):
        """Test creating a follow relationship."""
        follow = Follow.objects.create(follower=user1, following=user2)
        assert follow.follower == user1
        assert follow.following == user2
        assert Follow.objects.filter(follower=user1, following=user2).exists()

    def test_cannot_follow_self(self, user1):
        """Test that user cannot follow themselves."""
        follow = Follow(follower=user1, following=user1)
        with pytest.raises(ValidationError):
            follow.clean()

    def test_unique_follow(self, user1, user2):
        """Test that follow relationship is unique."""
        Follow.objects.create(follower=user1, following=user2)
        # Try to create duplicate
        with pytest.raises(Exception):  # IntegrityError
            Follow.objects.create(follower=user1, following=user2)

    def test_follow_str(self, user1, user2):
        """Test Follow string representation."""
        follow = Follow.objects.create(follower=user1, following=user2)
        assert str(follow) == f"{user1.username} follows {user2.username}"


@pytest.mark.django_db
class TestFollowAPI:
    """Test follow API endpoints."""

    def test_follow_user(self, authenticated_client, user1, user2):
        """Test following a user."""
        url = reverse("user-follow", kwargs={"pk": user2.id})
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_201_CREATED
        assert Follow.objects.filter(follower=user1, following=user2).exists()
        assert response.data["following"] == user2.id
        assert response.data["follower"] == user1.id

    def test_follow_already_following(self, authenticated_client, user1, user2):
        """Test following a user that is already being followed."""
        Follow.objects.create(follower=user1, following=user2)

        url = reverse("user-follow", kwargs={"pk": user2.id})
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        assert "already following" in response.data["message"].lower()

    def test_cannot_follow_self(self, authenticated_client, user1):
        """Test that user cannot follow themselves."""
        url = reverse("user-follow", kwargs={"pk": user1.id})
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "cannot follow yourself" in response.data["error"].lower()

    def test_unfollow_user(self, authenticated_client, user1, user2):
        """Test unfollowing a user."""
        Follow.objects.create(follower=user1, following=user2)

        url = reverse("user-unfollow", kwargs={"pk": user2.id})
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        assert not Follow.objects.filter(follower=user1, following=user2).exists()
        assert "unfollowed" in response.data["message"].lower()

    def test_unfollow_not_following(self, authenticated_client, user1, user2):
        """Test unfollowing a user that is not being followed."""
        url = reverse("user-unfollow", kwargs={"pk": user2.id})
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not following" in response.data["error"].lower()

    def test_get_followers(self, authenticated_client, user1, user2, user3):
        """Test getting list of followers."""
        Follow.objects.create(follower=user2, following=user1)
        Follow.objects.create(follower=user3, following=user1)

        url = reverse("user-followers", kwargs={"pk": user1.id})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        follower_ids = [item["follower"] for item in response.data]
        assert user2.id in follower_ids
        assert user3.id in follower_ids

    def test_get_following(self, authenticated_client, user1, user2, user3):
        """Test getting list of users being followed."""
        Follow.objects.create(follower=user1, following=user2)
        Follow.objects.create(follower=user1, following=user3)

        url = reverse("user-following", kwargs={"pk": user1.id})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        following_ids = [item["following"] for item in response.data]
        assert user2.id in following_ids
        assert user3.id in following_ids


@pytest.mark.django_db
class TestFollowViewSet:
    """Test FollowViewSet endpoints."""

    def test_list_my_following(self, authenticated_client, user1, user2, user3):
        """Test listing users I am following."""
        Follow.objects.create(follower=user1, following=user2)
        Follow.objects.create(follower=user1, following=user3)

        url = reverse("follow-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_my_followers_endpoint(self, authenticated_client, user1, user2, user3):
        """Test getting my followers."""
        Follow.objects.create(follower=user2, following=user1)
        Follow.objects.create(follower=user3, following=user1)

        url = reverse("follow-my-followers")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_my_following_endpoint(self, authenticated_client, user1, user2, user3):
        """Test getting users I am following."""
        Follow.objects.create(follower=user1, following=user2)
        Follow.objects.create(follower=user1, following=user3)

        url = reverse("follow-my-following")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2


@pytest.mark.django_db
class TestUserSerializerFollowFields:
    """Test UserSerializer follow-related fields."""

    def test_followers_count(self, authenticated_client, user1, user2, user3):
        """Test followers_count field."""
        Follow.objects.create(follower=user2, following=user1)
        Follow.objects.create(follower=user3, following=user1)

        url = reverse("user-detail", kwargs={"pk": user1.id})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["followers_count"] == 2

    def test_following_count(self, authenticated_client, user1, user2, user3):
        """Test following_count field."""
        Follow.objects.create(follower=user1, following=user2)
        Follow.objects.create(follower=user1, following=user3)

        url = reverse("user-detail", kwargs={"pk": user1.id})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["following_count"] == 2

    def test_is_following(self, authenticated_client, user1, user2):
        """Test is_following field."""
        Follow.objects.create(follower=user1, following=user2)

        url = reverse("user-detail", kwargs={"pk": user2.id})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_following"] is True

    def test_is_followed_by(self, authenticated_client, user1, user2):
        """Test is_followed_by field."""
        Follow.objects.create(follower=user2, following=user1)

        url = reverse("user-detail", kwargs={"pk": user2.id})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_followed_by"] is True


@pytest.mark.django_db
class TestFollowNotificationIntegration:
    """Test integration of follow system with notifications."""

    def test_poll_creation_notifies_followers(self, authenticated_client, user1, user2):
        """Test that creating a poll notifies followers."""
        from apps.notifications.models import Notification, NotificationType
        from apps.polls.models import Poll

        # User2 follows User1
        Follow.objects.create(follower=user2, following=user1)

        # User1 creates a poll
        url = reverse("poll-list")
        data = {
            "title": "New Poll",
            "description": "Test poll",
            "options": [{"text": "Option 1"}, {"text": "Option 2"}],
            "is_draft": False,
        }
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        poll_id = response.data["id"]

        # Check that User2 received a notification
        notification = Notification.objects.filter(
            user=user2,
            notification_type=NotificationType.NEW_POLL_FROM_FOLLOWED,
            poll_id=poll_id,
        ).first()

        assert notification is not None
        assert user1.username in notification.title

    def test_draft_poll_does_not_notify_followers(self, authenticated_client, user1, user2):
        """Test that draft polls don't notify followers."""
        from apps.notifications.models import Notification, NotificationType

        # User2 follows User1
        Follow.objects.create(follower=user2, following=user1)

        # User1 creates a draft poll
        url = reverse("poll-list")
        data = {
            "title": "Draft Poll",
            "description": "Draft poll",
            "options": [{"text": "Option 1"}, {"text": "Option 2"}],
            "is_draft": True,
        }
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED

        # Check that User2 did NOT receive a notification
        notification = Notification.objects.filter(
            user=user2,
            notification_type=NotificationType.NEW_POLL_FROM_FOLLOWED,
        ).first()

        assert notification is None

