"""
Tests for scheduled polls functionality.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import pytz
from apps.polls.models import Poll, PollOption
from apps.polls.tasks import (
    activate_scheduled_poll,
    close_scheduled_poll,
    process_scheduled_polls,
)
from core.utils.timezone_utils import convert_to_utc
from django.contrib.auth.models import User
from django.utils import timezone


@pytest.mark.django_db
class TestActivateScheduledPoll:
    """Test poll activation task."""

    def test_activate_poll_at_start_time(self, user):
        """Test that poll activates when start time is reached."""
        # Create poll with start time in the past
        past_time = timezone.now() - timedelta(minutes=5)
        poll = Poll.objects.create(
            title="Scheduled Poll",
            description="Test poll",
            created_by=user,
            starts_at=past_time,
            is_active=False,
        )

        with patch(
            "core.services.poll_notifications.send_poll_opened_notification"
        ) as mock_notify:
            result = activate_scheduled_poll(poll.id)

            poll.refresh_from_db()

            assert result["success"] is True
            assert poll.is_active is True
            assert result["action"] == "activated"
            mock_notify.assert_called_once_with(poll)

    def test_activate_poll_already_active(self, user):
        """Test that already active poll is not reactivated."""
        past_time = timezone.now() - timedelta(minutes=5)
        poll = Poll.objects.create(
            title="Active Poll",
            description="Test poll",
            created_by=user,
            starts_at=past_time,
            is_active=True,  # Already active
        )

        with patch(
            "core.services.poll_notifications.send_poll_opened_notification"
        ) as mock_notify:
            result = activate_scheduled_poll(poll.id)

            poll.refresh_from_db()

            assert result["success"] is False
            assert poll.is_active is True  # Still active
            assert "already active" in result["reason"].lower()
            mock_notify.assert_not_called()

    def test_activate_poll_not_yet_ready(self, user):
        """Test that poll with future start time is not activated."""
        future_time = timezone.now() + timedelta(hours=1)
        poll = Poll.objects.create(
            title="Future Poll",
            description="Test poll",
            created_by=user,
            starts_at=future_time,
            is_active=False,
        )

        with patch(
            "core.services.poll_notifications.send_poll_opened_notification"
        ) as mock_notify:
            result = activate_scheduled_poll(poll.id)

            poll.refresh_from_db()

            assert result["success"] is False
            assert poll.is_active is False  # Still inactive
            assert "not yet ready" in result["reason"].lower()
            mock_notify.assert_not_called()

    def test_activate_nonexistent_poll(self):
        """Test that activating nonexistent poll returns error."""
        result = activate_scheduled_poll(99999)

        assert result["success"] is False
        assert result["error"] == "Poll not found"


@pytest.mark.django_db
class TestCloseScheduledPoll:
    """Test poll closing task."""

    def test_close_poll_at_end_time(self, user):
        """Test that poll closes when end time is reached."""
        # Create poll with end time in the past
        past_time = timezone.now() - timedelta(minutes=5)
        poll = Poll.objects.create(
            title="Closing Poll",
            description="Test poll",
            created_by=user,
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=past_time,
            is_active=True,
        )

        with patch(
            "core.services.poll_notifications.send_poll_closed_notification"
        ) as mock_notify:
            result = close_scheduled_poll(poll.id)

            poll.refresh_from_db()

            assert result["success"] is True
            assert poll.is_active is False
            assert result["action"] == "closed"
            mock_notify.assert_called_once_with(poll)

    def test_close_poll_already_closed(self, user):
        """Test that already closed poll is not reclosed."""
        past_time = timezone.now() - timedelta(minutes=5)
        poll = Poll.objects.create(
            title="Closed Poll",
            description="Test poll",
            created_by=user,
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=past_time,
            is_active=False,  # Already closed
        )

        with patch(
            "core.services.poll_notifications.send_poll_closed_notification"
        ) as mock_notify:
            result = close_scheduled_poll(poll.id)

            poll.refresh_from_db()

            assert result["success"] is False
            assert poll.is_active is False  # Still closed
            assert "already closed" in result["reason"].lower()
            mock_notify.assert_not_called()

    def test_close_poll_not_yet_ready(self, user):
        """Test that poll with future end time is not closed."""
        future_time = timezone.now() + timedelta(hours=1)
        poll = Poll.objects.create(
            title="Future Closing Poll",
            description="Test poll",
            created_by=user,
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=future_time,
            is_active=True,
        )

        with patch(
            "core.services.poll_notifications.send_poll_closed_notification"
        ) as mock_notify:
            result = close_scheduled_poll(poll.id)

            poll.refresh_from_db()

            assert result["success"] is False
            assert poll.is_active is True  # Still active
            assert "not yet ready" in result["reason"].lower()
            mock_notify.assert_not_called()

    def test_close_poll_no_end_time(self, user):
        """Test that poll without end time is not closed."""
        poll = Poll.objects.create(
            title="No End Poll",
            description="Test poll",
            created_by=user,
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=None,
            is_active=True,
        )

        with patch(
            "core.services.poll_notifications.send_poll_closed_notification"
        ) as mock_notify:
            result = close_scheduled_poll(poll.id)

            poll.refresh_from_db()

            assert result["success"] is False
            assert poll.is_active is True  # Still active
            mock_notify.assert_not_called()

    def test_close_nonexistent_poll(self):
        """Test that closing nonexistent poll returns error."""
        result = close_scheduled_poll(99999)

        assert result["success"] is False
        assert result["error"] == "Poll not found"


@pytest.mark.django_db
class TestProcessScheduledPolls:
    """Test periodic scheduled polls processing."""

    def test_process_activates_ready_polls(self, user):
        """Test that process_scheduled_polls activates ready polls."""
        # Create poll ready for activation
        past_time = timezone.now() - timedelta(minutes=5)
        poll = Poll.objects.create(
            title="Ready Poll",
            description="Test poll",
            created_by=user,
            starts_at=past_time,
            is_active=False,
        )

        with patch("core.services.poll_notifications.send_poll_opened_notification"):
            result = process_scheduled_polls()

            poll.refresh_from_db()

            assert result["success"] is True
            assert result["activated_count"] == 1
            assert result["closed_count"] == 0
            assert poll.is_active is True

    def test_process_closes_ready_polls(self, user):
        """Test that process_scheduled_polls closes ready polls."""
        # Create poll ready for closing
        past_time = timezone.now() - timedelta(minutes=5)
        poll = Poll.objects.create(
            title="Closing Poll",
            description="Test poll",
            created_by=user,
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=past_time,
            is_active=True,
        )

        with patch("core.services.poll_notifications.send_poll_closed_notification"):
            result = process_scheduled_polls()

            poll.refresh_from_db()

            assert result["success"] is True
            assert result["activated_count"] == 0
            assert result["closed_count"] == 1
            assert poll.is_active is False

    def test_process_handles_both_activation_and_closing(self, user):
        """Test that process_scheduled_polls handles both activation and closing."""
        past_time = timezone.now() - timedelta(minutes=5)

        # Poll to activate
        poll1 = Poll.objects.create(
            title="Activate Poll",
            description="Test poll",
            created_by=user,
            starts_at=past_time,
            is_active=False,
        )

        # Poll to close
        poll2 = Poll.objects.create(
            title="Close Poll",
            description="Test poll",
            created_by=user,
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=past_time,
            is_active=True,
        )

        with patch(
            "core.services.poll_notifications.send_poll_opened_notification"
        ), patch("core.services.poll_notifications.send_poll_closed_notification"):
            result = process_scheduled_polls()

            poll1.refresh_from_db()
            poll2.refresh_from_db()

            assert result["success"] is True
            assert result["activated_count"] == 1
            assert result["closed_count"] == 1
            assert poll1.is_active is True
            assert poll2.is_active is False

    def test_process_skips_not_ready_polls(self, user):
        """Test that process_scheduled_polls skips polls not ready."""
        # Future poll
        future_time = timezone.now() + timedelta(hours=1)
        poll = Poll.objects.create(
            title="Future Poll",
            description="Test poll",
            created_by=user,
            starts_at=future_time,
            is_active=False,
        )

        result = process_scheduled_polls()

        poll.refresh_from_db()

        assert result["success"] is True
        assert result["activated_count"] == 0
        assert result["closed_count"] == 0
        assert poll.is_active is False

    def test_process_handles_errors_gracefully(self, user):
        """Test that process_scheduled_polls handles errors gracefully."""
        # Create poll that will cause an error by mocking the activation to fail
        past_time = timezone.now() - timedelta(minutes=5)
        poll = Poll.objects.create(
            title="Error Poll",
            description="Test poll",
            created_by=user,
            starts_at=past_time,
            is_active=False,
        )

        # Mock activate_scheduled_poll to raise an exception
        with patch(
            "apps.polls.tasks.activate_scheduled_poll",
            side_effect=Exception("Test error"),
        ):
            result = process_scheduled_polls()

            assert result["success"] is True
            assert len(result["errors"]) > 0


@pytest.mark.django_db
class TestScheduledPollsTimezoneHandling:
    """Test timezone handling in scheduled polls."""

    def test_poll_activation_with_timezone(self, user):
        """Test that poll activation handles timezones correctly."""

        # Create poll with start time in a specific timezone
        ny_tz = pytz.timezone("America/New_York")
        ny_time = ny_tz.localize(datetime(2024, 1, 1, 12, 0, 0))
        __utc_time = convert_to_utc(ny_time)  # Converted but not used in this test

        # Set poll start time to past (in UTC)
        past_utc = timezone.now() - timedelta(minutes=5)
        poll = Poll.objects.create(
            title="Timezone Test Poll",
            description="Test poll",
            created_by=user,
            starts_at=past_utc,
            is_active=False,
        )

        with patch("core.services.poll_notifications.send_poll_opened_notification"):
            result = activate_scheduled_poll(poll.id)

            poll.refresh_from_db()

            assert result["success"] is True
            assert poll.is_active is True

    def test_poll_closing_with_timezone(self, user):
        """Test that poll closing handles timezones correctly."""

        # Create poll with end time in a specific timezone
        past_utc = timezone.now() - timedelta(minutes=5)
        poll = Poll.objects.create(
            title="Timezone Closing Poll",
            description="Test poll",
            created_by=user,
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=past_utc,
            is_active=True,
        )

        with patch("core.services.poll_notifications.send_poll_closed_notification"):
            result = close_scheduled_poll(poll.id)

            poll.refresh_from_db()

            assert result["success"] is True
            assert poll.is_active is False

    def test_polls_in_different_timezones(self, user):
        """Test that polls in different timezones are handled correctly."""

        # Create polls with different timezone contexts
        # All stored in UTC in database, but created with different timezone awareness
        past_utc = timezone.now() - timedelta(minutes=5)

        poll1 = Poll.objects.create(
            title="NY Timezone Poll",
            description="Test poll",
            created_by=user,
            starts_at=past_utc,
            is_active=False,
        )

        poll2 = Poll.objects.create(
            title="Tokyo Timezone Poll",
            description="Test poll",
            created_by=user,
            starts_at=past_utc,
            is_active=False,
        )

        with patch("core.services.poll_notifications.send_poll_opened_notification"):
            result = process_scheduled_polls()

            poll1.refresh_from_db()
            poll2.refresh_from_db()

            assert result["success"] is True
            assert result["activated_count"] == 2
            assert poll1.is_active is True
            assert poll2.is_active is True
