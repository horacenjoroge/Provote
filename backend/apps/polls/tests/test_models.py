"""
Comprehensive tests for Poll models.
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.polls.models import Poll, PollOption


@pytest.mark.unit
class TestPollModel:
    """Test Poll model creation and properties."""

    def test_poll_creation(self, user):
        """Test creating a poll with all fields."""
        poll = Poll.objects.create(
            title="Test Poll",
            description="Test Description",
            created_by=user,
            settings={"allow_multiple_votes": False, "show_results": True},
            security_rules={"require_authentication": True, "ip_whitelist": []},
        )
        assert poll.title == "Test Poll"
        assert poll.description == "Test Description"
        assert poll.created_by == user
        assert poll.is_active is True
        assert poll.settings == {"allow_multiple_votes": False, "show_results": True}
        assert poll.security_rules == {"require_authentication": True, "ip_whitelist": []}
        assert poll.cached_total_votes == 0
        assert poll.cached_unique_voters == 0
        assert poll.created_at is not None
        assert poll.updated_at is not None

    def test_poll_default_values(self, user):
        """Test poll default values."""
        poll = Poll.objects.create(title="Test Poll", created_by=user)
        assert poll.settings == {}
        assert poll.security_rules == {}
        assert poll.cached_total_votes == 0
        assert poll.cached_unique_voters == 0
        assert poll.is_active is True

    def test_poll_is_open_property(self, poll):
        """Test poll is_open property when poll is open."""
        poll.starts_at = timezone.now() - timedelta(days=1)
        poll.ends_at = None
        poll.is_active = True
        poll.save()
        assert poll.is_open is True

    def test_poll_is_closed_when_inactive(self, poll):
        """Test poll is closed when inactive."""
        poll.is_active = False
        poll.save()
        assert poll.is_open is False

    def test_poll_is_closed_when_ended(self, poll):
        """Test poll is closed when end date passed."""
        poll.starts_at = timezone.now() - timedelta(days=2)
        poll.ends_at = timezone.now() - timedelta(days=1)
        poll.is_active = True
        poll.save()
        assert poll.is_open is False

    def test_poll_is_closed_when_not_started(self, poll):
        """Test poll is closed when start date hasn't arrived."""
        poll.starts_at = timezone.now() + timedelta(days=1)
        poll.ends_at = None
        poll.is_active = True
        poll.save()
        assert poll.is_open is False

    def test_poll_update_cached_totals(self, poll, user):
        """Test updating cached totals."""
        from apps.votes.models import Vote

        # Create some votes
        option1 = PollOption.objects.create(poll=poll, text="Option 1")
        option2 = PollOption.objects.create(poll=poll, text="Option 2")

        Vote.objects.create(
            user=user,
            poll=poll,
            option=option1,
            voter_token="token1",
            idempotency_key="key1",
        )
        Vote.objects.create(
            user=user,
            poll=poll,
            option=option2,
            voter_token="token1",
            idempotency_key="key2",
        )

        poll.update_cached_totals()
        poll.refresh_from_db()
        assert poll.cached_total_votes == 2
        assert poll.cached_unique_voters == 1

    def test_poll_str_representation(self, poll):
        """Test poll string representation."""
        assert str(poll) == poll.title


@pytest.mark.unit
class TestPollOptionModel:
    """Test PollOption model creation and properties."""

    def test_poll_option_creation(self, poll):
        """Test creating a poll option."""
        option = PollOption.objects.create(
            poll=poll,
            text="Option 1",
            order=1,
        )
        assert option.poll == poll
        assert option.text == "Option 1"
        assert option.order == 1
        assert option.cached_vote_count == 0
        assert option.created_at is not None

    def test_poll_option_default_values(self, poll):
        """Test poll option default values."""
        option = PollOption.objects.create(poll=poll, text="Option 1")
        assert option.order == 0
        assert option.cached_vote_count == 0

    def test_poll_option_vote_count_property(self, poll, user):
        """Test poll option vote_count property."""
        from apps.votes.models import Vote

        option = PollOption.objects.create(poll=poll, text="Option 1")
        assert option.vote_count == 0

        Vote.objects.create(
            user=user,
            poll=poll,
            option=option,
            voter_token="token1",
            idempotency_key="key1",
        )
        assert option.vote_count == 1

    def test_poll_option_update_cached_vote_count(self, poll, user):
        """Test updating cached vote count."""
        from apps.votes.models import Vote

        option = PollOption.objects.create(poll=poll, text="Option 1")
        assert option.cached_vote_count == 0

        Vote.objects.create(
            user=user,
            poll=poll,
            option=option,
            voter_token="token1",
            idempotency_key="key1",
        )
        option.update_cached_vote_count()
        option.refresh_from_db()
        assert option.cached_vote_count == 1

    def test_poll_option_ordering(self, poll):
        """Test poll option ordering by order field."""
        option1 = PollOption.objects.create(poll=poll, text="Option 1", order=2)
        option2 = PollOption.objects.create(poll=poll, text="Option 2", order=1)
        option3 = PollOption.objects.create(poll=poll, text="Option 3", order=3)

        options = list(PollOption.objects.filter(poll=poll))
        assert options[0] == option2  # order=1
        assert options[1] == option1  # order=2
        assert options[2] == option3  # order=3

    def test_poll_option_str_representation(self, poll):
        """Test poll option string representation."""
        option = PollOption.objects.create(poll=poll, text="Option 1")
        assert str(option) == f"{poll.title} - Option 1"

    def test_poll_option_cascade_delete(self, poll):
        """Test that poll option is deleted when poll is deleted."""
        option = PollOption.objects.create(poll=poll, text="Option 1")
        option_id = option.id

        poll.delete()
        assert not PollOption.objects.filter(id=option_id).exists()


@pytest.mark.django_db
class TestPollModelDatabaseConstraints:
    """Test database constraints and indexes for Poll model."""

    def test_poll_requires_title(self, user):
        """Test that poll requires a title."""
        with pytest.raises(Exception):  # IntegrityError or ValidationError
            Poll.objects.create(created_by=user)

    def test_poll_requires_created_by(self):
        """Test that poll requires created_by."""
        with pytest.raises(Exception):
            Poll.objects.create(title="Test Poll")

    @pytest.mark.skip(reason="get_indexes method not available in Django 5.x - use database-specific introspection")
    def test_poll_indexes_exist(self, poll):
        """Test that poll indexes exist."""
        from django.db import connection

        indexes = connection.introspection.get_indexes(connection.cursor(), "polls_poll")
        index_fields = [idx["columns"] for idx in indexes.values()]

        # Check for created_at index
        assert any("created_at" in fields for fields in index_fields)

    def test_poll_can_have_null_ends_at(self, user):
        """Test that poll can have null ends_at."""
        poll = Poll.objects.create(
            title="Open Poll",
            created_by=user,
            ends_at=None,
        )
        assert poll.ends_at is None


@pytest.mark.django_db
class TestPollOptionModelDatabaseConstraints:
    """Test database constraints and indexes for PollOption model."""

    def test_poll_option_requires_poll(self):
        """Test that poll option requires a poll."""
        with pytest.raises(Exception):
            PollOption.objects.create(text="Option 1")

    def test_poll_option_requires_text(self, poll):
        """Test that poll option requires text."""
        with pytest.raises(Exception):
            PollOption.objects.create(poll=poll)

    @pytest.mark.skip(reason="get_indexes method not available in Django 5.x - use database-specific introspection")
    def test_poll_option_indexes_exist(self, poll):
        """Test that poll option indexes exist."""
        from django.db import connection

        PollOption.objects.create(poll=poll, text="Option 1", order=1)
        indexes = connection.introspection.get_indexes(connection.cursor(), "polls_polloption")
        index_fields = [idx["columns"] for idx in indexes.values()]

        # Check for poll, order index
        assert any("poll_id" in fields and "order" in fields for fields in index_fields)

    def test_poll_option_cascade_delete_with_poll(self, poll):
        """Test that poll options are deleted when poll is deleted."""
        option1 = PollOption.objects.create(poll=poll, text="Option 1")
        option2 = PollOption.objects.create(poll=poll, text="Option 2")
        option1_id = option1.id
        option2_id = option2.id

        poll.delete()

        assert not PollOption.objects.filter(id=option1_id).exists()
        assert not PollOption.objects.filter(id=option2_id).exists()
