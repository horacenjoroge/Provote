"""
Tests for Poll models.
"""

from datetime import timedelta

import pytest
from django.utils import timezone


@pytest.mark.unit
class TestPollModel:
    """Test Poll model."""

    def test_poll_creation(self, poll):
        """Test creating a poll."""
        assert poll.title == "Test Poll"
        assert poll.is_active is True
        assert poll.created_by is not None

    def test_poll_is_open(self, poll):
        """Test poll is_open property."""
        poll.starts_at = timezone.now() - timedelta(days=1)
        poll.ends_at = None
        poll.is_active = True
        assert poll.is_open is True

    def test_poll_is_closed_when_inactive(self, poll):
        """Test poll is closed when inactive."""
        poll.is_active = False
        assert poll.is_open is False

    def test_poll_is_closed_when_ended(self, poll):
        """Test poll is closed when end date passed."""
        poll.starts_at = timezone.now() - timedelta(days=2)
        poll.ends_at = timezone.now() - timedelta(days=1)
        poll.is_active = True
        assert poll.is_open is False


@pytest.mark.unit
class TestChoiceModel:
    """Test Choice model."""

    def test_choice_creation(self, choices):
        """Test creating choices."""
        assert len(choices) == 2
        assert choices[0].text == "Choice 1"
        assert choices[1].text == "Choice 2"

    def test_choice_vote_count(self, choices):
        """Test choice vote_count property."""
        assert choices[0].vote_count == 0
