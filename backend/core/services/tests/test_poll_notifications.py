"""
Tests for poll notification service.
"""

import pytest
from datetime import timedelta
from django.contrib.auth.models import User
from django.utils import timezone
from unittest.mock import patch, MagicMock

from apps.polls.models import Poll
from core.services.poll_notifications import (
    send_poll_opened_notification,
    send_poll_closed_notification,
    get_poll_url,
)


@pytest.mark.django_db
class TestPollNotifications:
    """Test poll notification functions."""

    def test_send_poll_opened_notification_success(self, user):
        """Test successful poll opened notification."""
        user.email = "test@example.com"
        user.save()
        
        poll = Poll.objects.create(
            title="Test Poll",
            description="Test description",
            created_by=user,
            starts_at=timezone.now(),
        )

        with patch('core.services.poll_notifications.send_mail') as mock_send:
            result = send_poll_opened_notification(poll)
            
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert "Poll Opened" in call_args[1]["subject"]
            assert poll.title in call_args[1]["message"]
            assert user.email in call_args[1]["recipient_list"]

    def test_send_poll_opened_notification_no_email(self, user):
        """Test poll opened notification when user has no email."""
        user.email = ""
        user.save()
        
        poll = Poll.objects.create(
            title="Test Poll",
            description="Test description",
            created_by=user,
            starts_at=timezone.now(),
        )

        with patch('core.services.poll_notifications.send_mail') as mock_send:
            result = send_poll_opened_notification(poll)
            
            assert result is False
            mock_send.assert_not_called()

    def test_send_poll_closed_notification_success(self, user):
        """Test successful poll closed notification."""
        user.email = "test@example.com"
        user.save()
        
        poll = Poll.objects.create(
            title="Test Poll",
            description="Test description",
            created_by=user,
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=timezone.now(),
        )
        
        # Create some votes
        from apps.votes.models import Vote
        from apps.polls.models import PollOption
        
        option = PollOption.objects.create(poll=poll, text="Option 1", order=0)
        Vote.objects.create(
            poll=poll,
            option=option,
            user=user,
            voter_token="token1",
            idempotency_key="key1",
            is_valid=True,
        )

        with patch('core.services.poll_notifications.send_mail') as mock_send:
            result = send_poll_closed_notification(poll)
            
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert "Poll Closed" in call_args[1]["subject"]
            assert poll.title in call_args[1]["message"]
            assert "Total Votes: 1" in call_args[1]["message"]
            assert user.email in call_args[1]["recipient_list"]

    def test_send_poll_closed_notification_no_email(self, user):
        """Test poll closed notification when user has no email."""
        user.email = ""
        user.save()
        
        poll = Poll.objects.create(
            title="Test Poll",
            description="Test description",
            created_by=user,
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=timezone.now(),
        )

        with patch('core.services.poll_notifications.send_mail') as mock_send:
            result = send_poll_closed_notification(poll)
            
            assert result is False
            mock_send.assert_not_called()

    def test_send_poll_opened_notification_handles_error(self, user):
        """Test that notification handles errors gracefully."""
        user.email = "test@example.com"
        user.save()
        
        poll = Poll.objects.create(
            title="Test Poll",
            description="Test description",
            created_by=user,
            starts_at=timezone.now(),
        )

        with patch('core.services.poll_notifications.send_mail', side_effect=Exception("Email error")):
            result = send_poll_opened_notification(poll)
            
            assert result is False

    def test_get_poll_url(self):
        """Test poll URL generation."""
        url = get_poll_url(123)
        assert "/api/v1/polls/123/" in url
        assert "123" in url


@pytest.mark.django_db
class TestPollNotificationsIntegration:
    """Integration tests for poll notifications with actual polls."""

    def test_notification_sent_on_activation(self, user):
        """Test that notification is sent when poll is activated."""
        user.email = "test@example.com"
        user.save()
        
        past_time = timezone.now() - timedelta(minutes=5)
        poll = Poll.objects.create(
            title="Integration Test Poll",
            description="Test",
            created_by=user,
            starts_at=past_time,
            is_active=False,
        )

        with patch('core.services.poll_notifications.send_mail') as mock_send:
            from apps.polls.tasks import activate_scheduled_poll
            result = activate_scheduled_poll.apply(args=(poll.id,))
            
            assert result.result["success"] is True
            mock_send.assert_called_once()

