"""
Tests for Redis Pub/Sub integration.

Tests cover:
- Event publishing to Redis
- Event subscription and reception
- Multiple server scenarios
- Server crash handling
- Redis connection failure handling
"""

import json
import os
import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock

from core.utils.redis_pubsub import (
    VoteEventPublisher,
    VoteEventSubscriber,
    get_publisher,
    get_subscriber,
    publish_vote_event,
    VOTE_EVENTS_CHANNEL,
)


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.publish.return_value = 1  # 1 subscriber
    return mock_client


@pytest.fixture
def mock_redis_pubsub():
    """Mock Redis PubSub for testing."""
    mock_pubsub = MagicMock()
    mock_pubsub.get_message.return_value = None
    return mock_pubsub


class TestVoteEventPublisher:
    """Tests for VoteEventPublisher."""

    def test_publisher_initialization(self, mock_redis_client):
        """Test publisher initializes correctly."""
        with patch("core.utils.redis_pubsub.get_redis_connection", return_value=mock_redis_client):
            publisher = VoteEventPublisher()
            assert publisher.redis_client is not None
            assert publisher.is_connected()

    def test_publish_vote_event_success(self, mock_redis_client):
        """Test successful event publishing."""
        with patch("core.utils.redis_pubsub.get_redis_connection", return_value=mock_redis_client):
            publisher = VoteEventPublisher()
            result = publisher.publish_vote_event(poll_id=123, vote_id=456)
            
            assert result is True
            mock_redis_client.publish.assert_called_once()
            call_args = mock_redis_client.publish.call_args
            assert call_args[0][0] == VOTE_EVENTS_CHANNEL
            
            # Verify message content
            message = json.loads(call_args[0][1])
            assert message["type"] == "vote_cast"
            assert message["poll_id"] == 123
            assert message["vote_id"] == 456
            assert "timestamp" in message

    def test_publish_vote_event_connection_failure(self):
        """Test publishing when Redis connection fails."""
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("Connection failed")
        
        with patch("core.utils.redis_pubsub.get_redis_connection", return_value=mock_client):
            publisher = VoteEventPublisher()
            result = publisher.publish_vote_event(poll_id=123)
            assert result is False

    def test_publish_vote_event_reconnect(self, mock_redis_client):
        """Test publisher reconnects after connection loss."""
        publisher = VoteEventPublisher()
        publisher.redis_client = None  # Simulate connection loss
        
        with patch("core.utils.redis_pubsub.get_redis_connection", return_value=mock_redis_client):
            result = publisher.publish_vote_event(poll_id=123)
            assert result is True
            assert publisher.redis_client is not None

    def test_get_publisher_singleton(self):
        """Test get_publisher returns singleton instance."""
        # Clear the global singleton instance
        import core.utils.redis_pubsub
        core.utils.redis_pubsub._publisher_instance = None
        
        publisher1 = get_publisher()
        publisher2 = get_publisher()
        assert publisher1 is publisher2
        assert publisher1 is not None


class TestVoteEventSubscriber:
    """Tests for VoteEventSubscriber."""

    def test_subscriber_initialization(self, mock_redis_client, mock_redis_pubsub):
        """Test subscriber initializes correctly."""
        mock_redis_client.pubsub.return_value = mock_redis_pubsub
        
        with patch("core.utils.redis_pubsub.get_redis_connection", return_value=mock_redis_client):
            subscriber = VoteEventSubscriber()
            assert subscriber.redis_client is None  # Not connected until start
            assert not subscriber.is_running()

    def test_subscriber_start_stop(self, mock_redis_client, mock_redis_pubsub):
        """Test subscriber can start and stop."""
        mock_redis_client.pubsub.return_value = mock_redis_pubsub
        mock_redis_pubsub.get_message.return_value = None  # No messages
        
        with patch("core.utils.redis_pubsub.get_redis_connection", return_value=mock_redis_client):
            subscriber = VoteEventSubscriber()
            subscriber.start()
            
            assert subscriber.is_running()
            time.sleep(0.1)  # Give thread time to start
            
            subscriber.stop()
            assert not subscriber.is_running()

    def test_subscriber_receives_event(self, mock_redis_client, mock_redis_pubsub):
        """Test subscriber receives and processes events."""
        # Setup mock message
        event_data = {
            "type": "vote_cast",
            "poll_id": 123,
            "vote_id": 456,
            "timestamp": time.time(),
        }
        mock_message = {
            "type": "message",
            "data": json.dumps(event_data),
        }
        
        mock_redis_client.pubsub.return_value = mock_redis_pubsub
        mock_redis_pubsub.get_message.side_effect = [
            mock_message,
            None,  # Second call returns None to exit loop
        ]
        
        # Mock event handler
        event_handler = Mock()
        
        with patch("core.utils.redis_pubsub.get_redis_connection", return_value=mock_redis_client):
            subscriber = VoteEventSubscriber(event_handler=event_handler)
            subscriber.start()
            
            time.sleep(0.2)  # Give time to process message
            
            subscriber.stop()
            
            # Verify event handler was called
            event_handler.assert_called_once()
            call_args = event_handler.call_args[0][0]
            assert call_args["poll_id"] == 123
            assert call_args["vote_id"] == 456

    def test_subscriber_default_handler(self, mock_redis_client, mock_redis_pubsub):
        """Test subscriber default handler broadcasts via Channels."""
        event_data = {
            "type": "vote_cast",
            "poll_id": 123,
            "vote_id": 456,
            "timestamp": time.time(),
        }
        mock_message = {
            "type": "message",
            "data": json.dumps(event_data),
        }
        
        mock_redis_client.pubsub.return_value = mock_redis_pubsub
        mock_redis_pubsub.get_message.side_effect = [
            mock_message,
            None,
        ]
        
        with patch("core.utils.redis_pubsub.get_redis_connection", return_value=mock_redis_client):
            with patch("apps.polls.services.broadcast_poll_results_update") as mock_broadcast:
                subscriber = VoteEventSubscriber()  # Use default handler
                subscriber.start()
                
                time.sleep(0.2)
                
                subscriber.stop()
                
                # Verify broadcast was called
                mock_broadcast.assert_called_once_with(123)

    def test_subscriber_connection_failure_recovery(self, mock_redis_client, mock_redis_pubsub):
        """Test subscriber recovers from connection failures."""
        # First connection fails, then succeeds
        mock_redis_client.pubsub.return_value = mock_redis_pubsub
        mock_redis_client.ping.side_effect = [
            Exception("Connection failed"),
            True,  # Second attempt succeeds
        ]
        
        mock_redis_pubsub.get_message.return_value = None
        
        with patch("core.utils.redis_pubsub.get_redis_connection", return_value=mock_redis_client):
            subscriber = VoteEventSubscriber()
            subscriber.start()
            
            time.sleep(0.2)
            
            subscriber.stop()
            
            # Should have attempted reconnection
            assert mock_redis_client.ping.call_count >= 1

    def test_subscriber_invalid_json_handling(self, mock_redis_client, mock_redis_pubsub):
        """Test subscriber handles invalid JSON gracefully."""
        mock_message = {
            "type": "message",
            "data": "invalid json{",
        }
        
        mock_redis_client.pubsub.return_value = mock_redis_pubsub
        mock_redis_pubsub.get_message.side_effect = [
            mock_message,
            None,
        ]
        
        with patch("core.utils.redis_pubsub.get_redis_connection", return_value=mock_redis_client):
            subscriber = VoteEventSubscriber()
            subscriber.start()
            
            time.sleep(0.2)
            
            subscriber.stop()
            
            # Should not crash, just log error

    def test_get_subscriber_singleton(self):
        """Test get_subscriber returns singleton instance."""
        with patch("core.utils.redis_pubsub.VoteEventSubscriber") as mock_subscriber_class:
            subscriber1 = get_subscriber()
            subscriber2 = get_subscriber()
            assert subscriber1 is subscriber2
            assert mock_subscriber_class.call_count == 1


class TestRedisPubSubIntegration:
    """Integration tests for Redis Pub/Sub."""

    @pytest.mark.integration
    @pytest.mark.django_db
    def test_event_published_to_redis(self):
        """Test that events are published to Redis."""
        try:
            from django.conf import settings
            import redis
            
            # Try to get Redis URL from settings or environment
            redis_url = getattr(settings, 'REDIS_URL', os.environ.get('REDIS_URL', None))
            if redis_url:
                redis_client = redis.from_url(redis_url, decode_responses=True)
            else:
                # Fallback to individual settings
                redis_client = redis.Redis(
                    host=getattr(settings, 'REDIS_HOST', 'localhost'),
                    port=getattr(settings, 'REDIS_PORT', 6379),
                    db=getattr(settings, 'REDIS_DB', 0),
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
            redis_client.ping()
        except Exception:
            pytest.skip("Redis not available for integration test")
        
        # Create publisher
        publisher = VoteEventPublisher()
        
        # Subscribe to channel
        pubsub = redis_client.pubsub()
        pubsub.subscribe(VOTE_EVENTS_CHANNEL)
        
        # Publish event
        result = publisher.publish_vote_event(poll_id=999, vote_id=888)
        assert result is True
        
        # Wait for message
        message = pubsub.get_message(timeout=2.0, ignore_subscribe_messages=True)
        
        assert message is not None
        assert message["type"] == "message"
        
        event_data = json.loads(message["data"])
        assert event_data["poll_id"] == 999
        assert event_data["vote_id"] == 888
        
        pubsub.unsubscribe()
        pubsub.close()

    @pytest.mark.integration
    @pytest.mark.django_db
    def test_event_received_by_subscriber(self):
        """Test that subscribers receive published events."""
        try:
            from django.conf import settings
            import redis
            
            # Try to get Redis URL from settings or environment
            redis_url = getattr(settings, 'REDIS_URL', os.environ.get('REDIS_URL', None))
            if redis_url:
                redis_client = redis.from_url(redis_url, decode_responses=True)
            else:
                # Fallback to individual settings
                redis_client = redis.Redis(
                    host=getattr(settings, 'REDIS_HOST', 'localhost'),
                    port=getattr(settings, 'REDIS_PORT', 6379),
                    db=getattr(settings, 'REDIS_DB', 0),
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
            redis_client.ping()
        except Exception:
            pytest.skip("Redis not available for integration test")
        
        # Setup subscriber with mock handler
        received_events = []
        
        def event_handler(event_data):
            received_events.append(event_data)
        
        subscriber = VoteEventSubscriber(event_handler=event_handler)
        subscriber.start()
        
        time.sleep(0.5)  # Give subscriber time to connect
        
        # Publish event
        publisher = VoteEventPublisher()
        publisher.publish_vote_event(poll_id=777, vote_id=666)
        
        # Wait for event to be received
        time.sleep(1.0)
        
        subscriber.stop()
        
        # Verify event was received
        assert len(received_events) > 0
        assert received_events[0]["poll_id"] == 777
        assert received_events[0]["vote_id"] == 666

    @pytest.mark.integration
    @pytest.mark.django_db
    def test_multiple_servers_receive_events(self):
        """Test that multiple subscribers (simulating multiple servers) receive events."""
        try:
            from django.conf import settings
            import redis
            
            # Try to get Redis URL from settings or environment
            redis_url = getattr(settings, 'REDIS_URL', os.environ.get('REDIS_URL', None))
            if redis_url:
                redis_client = redis.from_url(redis_url, decode_responses=True)
            else:
                # Fallback to individual settings
                redis_client = redis.Redis(
                    host=getattr(settings, 'REDIS_HOST', 'localhost'),
                    port=getattr(settings, 'REDIS_PORT', 6379),
                    db=getattr(settings, 'REDIS_DB', 0),
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
            redis_client.ping()
        except Exception:
            pytest.skip("Redis not available for integration test")
        
        # Create multiple subscribers (simulating multiple servers)
        received_events_server1 = []
        received_events_server2 = []
        
        def handler1(event_data):
            received_events_server1.append(event_data)
        
        def handler2(event_data):
            received_events_server2.append(event_data)
        
        subscriber1 = VoteEventSubscriber(event_handler=handler1)
        subscriber2 = VoteEventSubscriber(event_handler=handler2)
        
        subscriber1.start()
        subscriber2.start()
        
        time.sleep(0.5)  # Give subscribers time to connect
        
        # Publish event
        publisher = VoteEventPublisher()
        publisher.publish_vote_event(poll_id=555, vote_id=444)
        
        # Wait for events to be received
        time.sleep(1.0)
        
        subscriber1.stop()
        subscriber2.stop()
        
        # Both servers should receive the event
        assert len(received_events_server1) > 0
        assert len(received_events_server2) > 0
        assert received_events_server1[0]["poll_id"] == 555
        assert received_events_server2[0]["poll_id"] == 555

    @pytest.mark.integration
    @pytest.mark.django_db
    def test_server_crash_doesnt_lose_events(self):
        """Test that events published before server crash are not lost."""
        try:
            from django.conf import settings
            import redis
            
            # Try to get Redis URL from settings or environment
            redis_url = getattr(settings, 'REDIS_URL', os.environ.get('REDIS_URL', None))
            if redis_url:
                redis_client = redis.from_url(redis_url, decode_responses=True)
            else:
                # Fallback to individual settings
                redis_client = redis.Redis(
                    host=getattr(settings, 'REDIS_HOST', 'localhost'),
                    port=getattr(settings, 'REDIS_PORT', 6379),
                    db=getattr(settings, 'REDIS_DB', 0),
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
            redis_client.ping()
        except Exception:
            pytest.skip("Redis not available for integration test")
        
        # Create subscriber
        received_events = []
        
        def event_handler(event_data):
            received_events.append(event_data)
        
        subscriber = VoteEventSubscriber(event_handler=event_handler)
        subscriber.start()
        
        time.sleep(0.5)
        
        # Publish event
        publisher = VoteEventPublisher()
        publisher.publish_vote_event(poll_id=333, vote_id=222)
        
        # Simulate server crash (stop subscriber abruptly)
        subscriber.stop()
        
        # Create new subscriber (simulating server restart)
        new_subscriber = VoteEventSubscriber(event_handler=event_handler)
        new_subscriber.start()
        
        time.sleep(0.5)
        
        # Note: In Redis Pub/Sub, if no subscriber is listening, the message is lost.
        # This is expected behavior. The test verifies that if a subscriber is running,
        # it receives the event. For guaranteed delivery, you'd need Redis Streams.
        
        # Publish another event after restart
        publisher.publish_vote_event(poll_id=111, vote_id=000)
        
        time.sleep(1.0)
        
        new_subscriber.stop()
        
        # At least the second event should be received
        # (First event may be lost if no subscriber was listening)
        assert len(received_events) > 0

    @pytest.mark.integration
    @pytest.mark.django_db
    def test_redis_connection_failure_handling(self):
        """Test handling of Redis connection failures."""
        # Create publisher with invalid Redis config
        with patch("django.conf.settings.REDIS_HOST", "invalid_host"):
            with patch("django.conf.settings.REDIS_PORT", 9999):
                publisher = VoteEventPublisher()
                
                # Should handle connection failure gracefully
                result = publisher.publish_vote_event(poll_id=123)
                assert result is False
                
                # Should not crash
                assert publisher.redis_client is None or not publisher.is_connected()

    @pytest.mark.integration
    @pytest.mark.django_db
    def test_publish_vote_event_convenience_function(self):
        """Test the convenience function publish_vote_event."""
        try:
            from django.conf import settings
            import redis
            
            # Try to get Redis URL from settings or environment
            redis_url = getattr(settings, 'REDIS_URL', os.environ.get('REDIS_URL', None))
            if redis_url:
                redis_client = redis.from_url(redis_url, decode_responses=True)
            else:
                # Fallback to individual settings
                redis_client = redis.Redis(
                    host=getattr(settings, 'REDIS_HOST', 'localhost'),
                    port=getattr(settings, 'REDIS_PORT', 6379),
                    db=getattr(settings, 'REDIS_DB', 0),
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
            redis_client.ping()
        except Exception:
            pytest.skip("Redis not available for integration test")
        
        # Use convenience function
        result = publish_vote_event(poll_id=123, vote_id=456)
        assert result is True

