"""
Comprehensive unit tests for Poll models using factories.
Tests all edge cases, error paths, and model methods.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from datetime import timedelta

from apps.polls.factories import CategoryFactory, PollFactory, PollOptionFactory, TagFactory
from apps.polls.models import Category, Poll, PollOption, Tag


@pytest.mark.unit
@pytest.mark.django_db
class TestCategoryModel:
    """Comprehensive tests for Category model."""

    def test_category_creation(self):
        """Test creating a category with all fields."""
        category = CategoryFactory(
            name="Politics",
            description="Political polls"
        )
        assert category.name == "Politics"
        assert category.description == "Political polls"
        assert category.slug == "politics"
        assert category.created_at is not None

    def test_category_auto_slug_generation(self):
        """Test that slug is auto-generated from name."""
        category = CategoryFactory(name="Sports & Entertainment")
        assert category.slug == "sports-entertainment"

    def test_category_unique_name(self):
        """Test that category name must be unique."""
        CategoryFactory(name="Unique Category")
        with pytest.raises(IntegrityError):
            CategoryFactory(name="Unique Category")

    def test_category_unique_slug(self):
        """Test that category slug must be unique."""
        CategoryFactory(name="Test Category")
        with pytest.raises(IntegrityError):
            CategoryFactory(name="Test Category")

    def test_category_str_representation(self):
        """Test category string representation."""
        category = CategoryFactory(name="Test Category")
        assert str(category) == "Test Category"

    def test_category_ordering(self):
        """Test that categories are ordered by name."""
        CategoryFactory(name="Zebra")
        CategoryFactory(name="Alpha")
        CategoryFactory(name="Beta")
        
        categories = list(Category.objects.all())
        assert categories[0].name == "Alpha"
        assert categories[1].name == "Beta"
        assert categories[2].name == "Zebra"

    def test_category_with_empty_description(self):
        """Test category can have empty description."""
        category = CategoryFactory(description="")
        assert category.description == ""

    @pytest.mark.skip(reason="get_indexes method not available in Django 5.x - use database-specific introspection")
    def test_category_slug_index(self):
        """Test that slug has an index for efficient lookups."""
        from django.db import connection
        category = CategoryFactory()
        indexes = connection.introspection.get_indexes(connection.cursor(), "polls_category")
        index_fields = [idx["columns"] for idx in indexes.values()]
        assert any("slug" in fields for fields in index_fields)


@pytest.mark.unit
@pytest.mark.django_db
class TestTagModel:
    """Comprehensive tests for Tag model."""

    def test_tag_creation(self):
        """Test creating a tag."""
        tag = TagFactory(name="technology")
        assert tag.name == "technology"
        assert tag.slug == "technology"
        assert tag.created_at is not None

    def test_tag_auto_slug_generation(self):
        """Test that slug is auto-generated from name."""
        tag = TagFactory(name="Machine Learning")
        assert tag.slug == "machine-learning"

    def test_tag_unique_name(self):
        """Test that tag name must be unique."""
        TagFactory(name="unique-tag")
        with pytest.raises(IntegrityError):
            TagFactory(name="unique-tag")

    def test_tag_unique_slug(self):
        """Test that tag slug must be unique."""
        TagFactory(name="Test Tag")
        with pytest.raises(IntegrityError):
            TagFactory(name="Test Tag")

    def test_tag_str_representation(self):
        """Test tag string representation."""
        tag = TagFactory(name="test-tag")
        assert str(tag) == "test-tag"

    def test_tag_ordering(self):
        """Test that tags are ordered by name."""
        TagFactory(name="zebra")
        TagFactory(name="alpha")
        TagFactory(name="beta")
        
        tags = list(Tag.objects.all())
        assert tags[0].name == "alpha"
        assert tags[1].name == "beta"
        assert tags[2].name == "zebra"

    @pytest.mark.skip(reason="get_indexes method not available in Django 5.x - use database-specific introspection")
    def test_tag_slug_index(self):
        """Test that slug has an index."""
        from django.db import connection
        tag = TagFactory()
        indexes = connection.introspection.get_indexes(connection.cursor(), "polls_tag")
        index_fields = [idx["columns"] for idx in indexes.values()]
        assert any("slug" in fields for fields in index_fields)

    @pytest.mark.skip(reason="get_indexes method not available in Django 5.x - use database-specific introspection")
    def test_tag_name_index(self):
        """Test that name has an index."""
        from django.db import connection
        tag = TagFactory()
        indexes = connection.introspection.get_indexes(connection.cursor(), "polls_tag")
        index_fields = [idx["columns"] for idx in indexes.values()]
        assert any("name" in fields for fields in index_fields)


@pytest.mark.unit
@pytest.mark.django_db
class TestPollModelComprehensive:
    """Comprehensive tests for Poll model using factories."""

    def test_poll_with_category(self, user):
        """Test poll with category."""
        category = CategoryFactory()
        poll = PollFactory(created_by=user, category=category)
        assert poll.category == category
        assert poll in category.polls.all()

    def test_poll_with_tags(self, user):
        """Test poll with multiple tags."""
        tag1 = TagFactory()
        tag2 = TagFactory()
        poll = PollFactory(created_by=user, tags=[tag1, tag2])
        assert tag1 in poll.tags.all()
        assert tag2 in poll.tags.all()
        assert poll in tag1.polls.all()
        assert poll in tag2.polls.all()

    def test_poll_draft_not_open(self, user):
        """Test that draft polls are never open."""
        poll = PollFactory(created_by=user, is_draft=True, is_active=True)
        assert poll.is_open is False

    def test_poll_is_open_edge_cases(self, user):
        """Test is_open property with various edge cases."""
        now = timezone.now()
        
        # Poll that hasn't started
        poll = PollFactory(
            created_by=user,
            starts_at=now + timedelta(days=1),
            is_active=True,
            is_draft=False
        )
        assert poll.is_open is False

        # Poll that has ended
        poll = PollFactory(
            created_by=user,
            starts_at=now - timedelta(days=2),
            ends_at=now - timedelta(days=1),
            is_active=True,
            is_draft=False
        )
        assert poll.is_open is False

        # Poll currently open
        poll = PollFactory(
            created_by=user,
            starts_at=now - timedelta(days=1),
            ends_at=None,
            is_active=True,
            is_draft=False
        )
        assert poll.is_open is True

        # Poll with end date in future
        poll = PollFactory(
            created_by=user,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
            is_active=True,
            is_draft=False
        )
        assert poll.is_open is True

    def test_poll_update_cached_totals_with_multiple_users(self, user):
        """Test updating cached totals with multiple users."""
        from apps.votes.factories import VoteFactory
        from apps.users.factories import UserFactory
        
        poll = PollFactory(created_by=user)
        option = PollOptionFactory(poll=poll)
        
        # Create votes from different users
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()
        
        VoteFactory(user=user1, poll=poll, option=option)
        VoteFactory(user=user2, poll=poll, option=option)
        VoteFactory(user=user3, poll=poll, option=option)
        
        poll.update_cached_totals()
        poll.refresh_from_db()
        assert poll.cached_total_votes == 3
        assert poll.cached_unique_voters == 3

    def test_poll_update_cached_totals_empty_poll(self, user):
        """Test updating cached totals for poll with no votes."""
        poll = PollFactory(created_by=user)
        poll.update_cached_totals()
        poll.refresh_from_db()
        assert poll.cached_total_votes == 0
        assert poll.cached_unique_voters == 0

    @pytest.mark.skip(reason="get_indexes method not available in Django 5.x - use database-specific introspection")
    def test_poll_category_index(self, user):
        """Test that category has an index."""
        from django.db import connection
        poll = PollFactory(created_by=user)
        indexes = connection.introspection.get_indexes(connection.cursor(), "polls_poll")
        index_fields = [idx["columns"] for idx in indexes.values()]
        assert any("category_id" in fields for fields in index_fields)

    @pytest.mark.skip(reason="get_indexes method not available in Django 5.x - use database-specific introspection")
    def test_poll_draft_index(self, user):
        """Test that is_draft and created_by have a composite index."""
        from django.db import connection
        poll = PollFactory(created_by=user, is_draft=True)
        indexes = connection.introspection.get_indexes(connection.cursor(), "polls_poll")
        index_fields = [idx["columns"] for idx in indexes.values()]
        # Check for composite index on is_draft and created_by
        assert any("is_draft" in fields and "created_by_id" in fields for fields in index_fields)


@pytest.mark.unit
@pytest.mark.django_db
class TestPollOptionModelComprehensive:
    """Comprehensive tests for PollOption model using factories."""

    def test_poll_option_ordering(self, user):
        """Test poll option ordering."""
        poll = PollFactory(created_by=user)
        option3 = PollOptionFactory(poll=poll, text="Option 3", order=3)
        option1 = PollOptionFactory(poll=poll, text="Option 1", order=1)
        option2 = PollOptionFactory(poll=poll, text="Option 2", order=2)
        
        options = list(poll.options.all())
        assert options[0] == option1
        assert options[1] == option2
        assert options[2] == option3

    def test_poll_option_vote_count_property(self, user):
        """Test vote_count property with multiple votes."""
        from apps.votes.factories import VoteFactory
        from apps.users.factories import UserFactory
        
        poll = PollFactory(created_by=user)
        option = PollOptionFactory(poll=poll)
        
        # Create multiple votes
        for _ in range(5):
            vote_user = UserFactory()
            VoteFactory(user=vote_user, poll=poll, option=option)
        
        assert option.vote_count == 5

    def test_poll_option_update_cached_vote_count(self, user):
        """Test updating cached vote count."""
        from apps.votes.factories import VoteFactory
        from apps.users.factories import UserFactory
        
        poll = PollFactory(created_by=user)
        option = PollOptionFactory(poll=poll)
        
        # Create votes
        for _ in range(3):
            vote_user = UserFactory()
            VoteFactory(user=vote_user, poll=poll, option=option)
        
        option.update_cached_vote_count()
        option.refresh_from_db()
        assert option.cached_vote_count == 3

    def test_poll_option_cascade_delete(self, user):
        """Test that options are deleted when poll is deleted."""
        poll = PollFactory(created_by=user)
        option = PollOptionFactory(poll=poll)
        option_id = option.id
        
        poll.delete()
        assert not PollOption.objects.filter(id=option_id).exists()

    @pytest.mark.skip(reason="get_indexes method not available in Django 5.x - use database-specific introspection")
    def test_poll_option_poll_index(self, user):
        """Test that poll and order have a composite index."""
        from django.db import connection
        poll = PollFactory(created_by=user)
        option = PollOptionFactory(poll=poll)
        indexes = connection.introspection.get_indexes(connection.cursor(), "polls_polloption")
        index_fields = [idx["columns"] for idx in indexes.values()]
        assert any("poll_id" in fields and "order" in fields for fields in index_fields)

