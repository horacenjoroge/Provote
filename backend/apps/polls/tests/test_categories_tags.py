"""
Tests for poll categories and tags functionality.
"""

import pytest
from apps.polls.models import Category, Poll, Tag
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def user():
    """Create a test user."""
    return User.objects.create_user(username="testuser", password="testpass123")


@pytest.fixture
def api_client():
    """Create an API client."""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, user):
    """Create an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def category():
    """Create a test category."""
    return Category.objects.create(
        name="Politics", slug="politics", description="Political polls"
    )


@pytest.fixture
def tag():
    """Create a test tag."""
    return Tag.objects.create(name="election", slug="election")


@pytest.mark.django_db
class TestCategoryCreation:
    """Test category creation."""

    def test_create_category(self, authenticated_client):
        """Test creating a category."""
        url = reverse("category-list")
        data = {"name": "Sports", "description": "Sports related polls"}
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Sports"
        assert response.data["slug"] == "sports"
        assert Category.objects.filter(name="Sports").exists()

    def test_create_category_auto_slug(self, authenticated_client):
        """Test that slug is auto-generated from name."""
        url = reverse("category-list")
        data = {"name": "Entertainment & Media"}
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["slug"] == "entertainment-media"

    def test_create_category_duplicate_name_fails(self, authenticated_client, category):
        """Test that duplicate category names are rejected."""
        url = reverse("category-list")
        data = {"name": "Politics"}
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestTagCreation:
    """Test tag creation."""

    def test_create_tag(self, authenticated_client):
        """Test creating a tag."""
        url = reverse("tag-list")
        data = {"name": "football"}
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "football"
        assert response.data["slug"] == "football"
        assert Tag.objects.filter(name="football").exists()

    def test_create_tag_auto_slug(self, authenticated_client):
        """Test that slug is auto-generated from name."""
        url = reverse("tag-list")
        data = {"name": "World Cup 2024"}
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["slug"] == "world-cup-2024"

    def test_create_tag_duplicate_name_fails(self, authenticated_client, tag):
        """Test that duplicate tag names are rejected."""
        url = reverse("tag-list")
        data = {"name": "election"}
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPollFilteringByCategory:
    """Test filtering polls by category."""

    def test_filter_by_category_slug(self, authenticated_client, user, category):
        """Test filtering polls by category slug."""
        poll1 = Poll.objects.create(title="Poll 1", category=category, created_by=user)
        poll2 = Poll.objects.create(title="Poll 2", created_by=user)

        url = reverse("poll-list")
        response = authenticated_client.get(url, {"category": "politics"})

        assert response.status_code == status.HTTP_200_OK
        results = (
            response.data["results"] if "results" in response.data else response.data
        )
        poll_ids = [p["id"] for p in results]
        assert poll1.id in poll_ids
        assert poll2.id not in poll_ids

    def test_filter_by_category_id(self, authenticated_client, user, category):
        """Test filtering polls by category ID."""
        poll1 = Poll.objects.create(title="Poll 1", category=category, created_by=user)
        poll2 = Poll.objects.create(title="Poll 2", created_by=user)

        url = reverse("poll-list")
        response = authenticated_client.get(url, {"category": str(category.id)})

        assert response.status_code == status.HTTP_200_OK
        results = (
            response.data["results"] if "results" in response.data else response.data
        )
        poll_ids = [p["id"] for p in results]
        assert poll1.id in poll_ids
        assert poll2.id not in poll_ids

    def test_filter_by_nonexistent_category(self, authenticated_client, user):
        """Test filtering by non-existent category returns empty."""
        Poll.objects.create(title="Poll 1", created_by=user)

        url = reverse("poll-list")
        response = authenticated_client.get(url, {"category": "nonexistent"})

        assert response.status_code == status.HTTP_200_OK
        results = (
            response.data["results"] if "results" in response.data else response.data
        )
        assert len(results) == 0


@pytest.mark.django_db
class TestPollFilteringByTags:
    """Test filtering polls by tags."""

    def test_filter_by_single_tag(self, authenticated_client, user, tag):
        """Test filtering polls by a single tag."""
        poll1 = Poll.objects.create(title="Poll 1", created_by=user)
        poll1.tags.add(tag)
        poll2 = Poll.objects.create(title="Poll 2", created_by=user)

        url = reverse("poll-list")
        response = authenticated_client.get(url, {"tags": "election"})

        assert response.status_code == status.HTTP_200_OK
        results = (
            response.data["results"] if "results" in response.data else response.data
        )
        poll_ids = [p["id"] for p in results]
        assert poll1.id in poll_ids
        assert poll2.id not in poll_ids

    def test_filter_by_multiple_tags(self, authenticated_client, user):
        """Test filtering polls by multiple tags (comma-separated)."""
        tag1 = Tag.objects.create(name="election", slug="election")
        tag2 = Tag.objects.create(name="presidential", slug="presidential")
        poll1 = Poll.objects.create(title="Poll 1", created_by=user)
        poll1.tags.add(tag1, tag2)
        poll2 = Poll.objects.create(title="Poll 2", created_by=user)
        poll2.tags.add(tag1)

        url = reverse("poll-list")
        response = authenticated_client.get(url, {"tags": "election,presidential"})

        assert response.status_code == status.HTTP_200_OK
        results = (
            response.data["results"] if "results" in response.data else response.data
        )
        poll_ids = [p["id"] for p in results]
        assert poll1.id in poll_ids
        # poll2 should also appear since it has "election" tag
        assert poll2.id in poll_ids

    def test_filter_by_tag_id(self, authenticated_client, user, tag):
        """Test filtering polls by tag ID."""
        poll1 = Poll.objects.create(title="Poll 1", created_by=user)
        poll1.tags.add(tag)
        poll2 = Poll.objects.create(title="Poll 2", created_by=user)

        url = reverse("poll-list")
        response = authenticated_client.get(url, {"tags": str(tag.id)})

        assert response.status_code == status.HTTP_200_OK
        results = (
            response.data["results"] if "results" in response.data else response.data
        )
        poll_ids = [p["id"] for p in results]
        assert poll1.id in poll_ids
        assert poll2.id not in poll_ids


@pytest.mark.django_db
class TestPollSearchByTags:
    """Test searching polls by tags."""

    def test_search_by_tag_name(self, authenticated_client, user):
        """Test searching polls by tag name."""
        tag1 = Tag.objects.create(name="election")
        tag2 = Tag.objects.create(name="presidential")
        poll1 = Poll.objects.create(title="Poll 1", created_by=user)
        poll1.tags.add(tag1, tag2)
        poll2 = Poll.objects.create(title="Poll 2", created_by=user)
        poll2.tags.add(tag1)

        url = reverse("poll-list")
        response = authenticated_client.get(url, {"search": "election"})

        assert response.status_code == status.HTTP_200_OK
        results = (
            response.data["results"] if "results" in response.data else response.data
        )
        poll_ids = [p["id"] for p in results]
        assert poll1.id in poll_ids
        assert poll2.id in poll_ids

    def test_tag_search_case_insensitive(self, authenticated_client, user):
        """Test that tag search is case insensitive."""
        tag = Tag.objects.create(name="Election")
        poll = Poll.objects.create(title="Poll 1", created_by=user)
        poll.tags.add(tag)

        url = reverse("poll-list")
        response = authenticated_client.get(url, {"search": "election"})

        assert response.status_code == status.HTTP_200_OK
        results = (
            response.data["results"] if "results" in response.data else response.data
        )
        assert len(results) >= 1

    def test_tag_search_partial_match(self, authenticated_client, user):
        """Test that tag search supports partial matching."""
        tag = Tag.objects.create(name="presidential-election")
        poll = Poll.objects.create(title="Poll 1", created_by=user)
        poll.tags.add(tag)

        url = reverse("poll-list")
        response = authenticated_client.get(url, {"search": "presidential"})

        assert response.status_code == status.HTTP_200_OK
        results = (
            response.data["results"] if "results" in response.data else response.data
        )
        assert len(results) >= 1


@pytest.mark.django_db
class TestPollCreationWithCategoryAndTags:
    """Test creating polls with category and tags."""

    def test_create_poll_with_category(self, authenticated_client, user, category):
        """Test creating a poll with a category."""
        url = reverse("poll-list")
        data = {
            "title": "Test Poll",
            "description": "Test description",
            "options": [
                {"text": "Option 1"},
                {"text": "Option 2"},
            ],
            "category": category.id,
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["category"]["id"] == category.id
        assert response.data["category"]["name"] == "Politics"

        # Verify in database
        poll = Poll.objects.get(id=response.data["id"])
        assert poll.category == category

    def test_create_poll_with_tags(self, authenticated_client, user, tag):
        """Test creating a poll with tags."""
        tag2 = Tag.objects.create(name="politics", slug="politics")
        url = reverse("poll-list")
        data = {
            "title": "Test Poll",
            "description": "Test description",
            "options": [
                {"text": "Option 1"},
                {"text": "Option 2"},
            ],
            "tags": [tag.id, tag2.id],
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data["tags"]) == 2
        tag_ids = [t["id"] for t in response.data["tags"]]
        assert tag.id in tag_ids
        assert tag2.id in tag_ids

        # Verify in database
        poll = Poll.objects.get(id=response.data["id"])
        assert poll.tags.count() == 2
        assert tag in poll.tags.all()
        assert tag2 in poll.tags.all()

    def test_create_poll_with_category_and_tags(
        self, authenticated_client, user, category, tag
    ):
        """Test creating a poll with both category and tags."""
        url = reverse("poll-list")
        data = {
            "title": "Test Poll",
            "description": "Test description",
            "options": [
                {"text": "Option 1"},
                {"text": "Option 2"},
            ],
            "category": category.id,
            "tags": [tag.id],
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["category"]["id"] == category.id
        assert len(response.data["tags"]) == 1
        assert response.data["tags"][0]["id"] == tag.id


@pytest.mark.django_db
class TestCategoryViewSet:
    """Test CategoryViewSet endpoints."""

    def test_list_categories(self, authenticated_client, category):
        """Test listing all categories."""
        Category.objects.create(name="Sports", slug="sports")
        url = reverse("category-list")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 2

    def test_get_category_detail(self, authenticated_client, category):
        """Test getting a category detail."""
        url = reverse("category-detail", kwargs={"pk": category.id})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Politics"
        assert response.data["poll_count"] == 0

    def test_category_polls_endpoint(self, authenticated_client, user, category):
        """Test getting polls in a category."""
        poll1 = Poll.objects.create(title="Poll 1", category=category, created_by=user)
        poll2 = Poll.objects.create(title="Poll 2", created_by=user)

        url = reverse("category-polls", kwargs={"pk": category.id})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        poll_ids = [p["id"] for p in response.data]
        assert poll1.id in poll_ids
        assert poll2.id not in poll_ids


@pytest.mark.django_db
class TestTagViewSet:
    """Test TagViewSet endpoints."""

    def test_list_tags(self, authenticated_client, tag):
        """Test listing all tags."""
        Tag.objects.create(name="sports", slug="sports")
        url = reverse("tag-list")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 2

    def test_get_tag_detail(self, authenticated_client, tag):
        """Test getting a tag detail."""
        url = reverse("tag-detail", kwargs={"pk": tag.id})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "election"
        assert response.data["poll_count"] == 0

    def test_tag_polls_endpoint(self, authenticated_client, user, tag):
        """Test getting polls with a tag."""
        poll1 = Poll.objects.create(title="Poll 1", created_by=user)
        poll1.tags.add(tag)
        poll2 = Poll.objects.create(title="Poll 2", created_by=user)

        url = reverse("tag-polls", kwargs={"pk": tag.id})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        poll_ids = [p["id"] for p in response.data]
        assert poll1.id in poll_ids
        assert poll2.id not in poll_ids
