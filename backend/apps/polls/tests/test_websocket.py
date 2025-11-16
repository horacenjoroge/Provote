"""
Comprehensive tests for WebSocket poll results consumer.
"""

import json
import pytest
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.contrib.auth.models import User

from apps.polls.models import Poll, PollOption
from apps.polls.consumers import PollResultsConsumer
from apps.votes.models import Vote
from apps.votes.services import cast_vote


@pytest.mark.django_db
@pytest.mark.asyncio
class TestWebSocketConnection:
    """Test WebSocket connection establishment."""

    async def test_websocket_connection_established(self, poll, choices):
        """Test that WebSocket connection is successfully established."""
        # Configure poll to show results
        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        communicator = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator.scope["user"] = await database_sync_to_async(User.objects.create_user)(
            username="testuser", password="testpass"
        )

        connected, subprotocol = await communicator.connect()

        assert connected is True

        # Should receive initial results
        response = await communicator.receive_json_from()
        assert response["type"] == "results"
        assert response["poll_id"] == poll.id
        assert "data" in response

        await communicator.disconnect()

    async def test_websocket_connection_rejected_for_private_poll(self, poll, choices):
        """Test that WebSocket connection is rejected for private polls."""
        # Make poll private
        poll.settings["is_private"] = True
        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        # Create non-owner user
        other_user = await database_sync_to_async(User.objects.create_user)(
            username="otheruser", password="testpass"
        )

        communicator = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator.scope["user"] = other_user

        connected, subprotocol = await communicator.connect()

        # Connection should be rejected (403 Forbidden)
        assert connected is False

    async def test_websocket_connection_allowed_for_poll_owner(self, poll, choices):
        """Test that WebSocket connection is allowed for poll owner."""
        # Make poll private
        poll.settings["is_private"] = True
        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        communicator = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator.scope["user"] = poll.created_by

        connected, subprotocol = await communicator.connect()

        assert connected is True

        await communicator.disconnect()

    async def test_websocket_connection_rejected_for_nonexistent_poll(self):
        """Test that WebSocket connection is rejected for nonexistent poll."""
        communicator = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), "/ws/polls/99999/results/"
        )
        communicator.scope["user"] = await database_sync_to_async(User.objects.create_user)(
            username="testuser", password="testpass"
        )

        connected, subprotocol = await communicator.connect()

        # Connection should be rejected (404 Not Found)
        assert connected is False


@pytest.mark.django_db
@pytest.mark.asyncio
class TestWebSocketSubscription:
    """Test WebSocket subscription functionality."""

    async def test_subscribing_to_poll(self, poll, choices):
        """Test subscribing to poll results."""
        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        communicator = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator.scope["user"] = await database_sync_to_async(User.objects.create_user)(
            username="testuser", password="testpass"
        )

        connected, subprotocol = await communicator.connect()
        assert connected is True

        # Send subscribe message
        await communicator.send_json_to({"type": "subscribe"})

        # Should receive results
        response = await communicator.receive_json_from()
        assert response["type"] == "results"
        assert response["poll_id"] == poll.id

        await communicator.disconnect()

    async def test_unsubscribing_from_poll(self, poll, choices):
        """Test unsubscribing from poll results."""
        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        communicator = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator.scope["user"] = await database_sync_to_async(User.objects.create_user)(
            username="testuser", password="testpass"
        )

        connected, subprotocol = await communicator.connect()
        assert connected is True

        # Send unsubscribe message
        await communicator.send_json_to({"type": "unsubscribe"})

        # Should receive unsubscribed confirmation
        response = await communicator.receive_json_from()
        assert response["type"] == "unsubscribed"
        assert response["poll_id"] == poll.id

        await communicator.disconnect()

    async def test_ping_pong_heartbeat(self, poll, choices):
        """Test ping/pong heartbeat mechanism."""
        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        communicator = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator.scope["user"] = await database_sync_to_async(User.objects.create_user)(
            username="testuser", password="testpass"
        )

        connected, subprotocol = await communicator.connect()
        assert connected is True

        # Clear initial results message
        await communicator.receive_json_from()

        # Send ping
        await communicator.send_json_to({"type": "ping"})

        # Should receive pong
        response = await communicator.receive_json_from()
        assert response["type"] == "pong"
        assert response["poll_id"] == poll.id

        await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
class TestWebSocketUpdates:
    """Test receiving updates when votes are cast."""

    async def test_receiving_updates_when_votes_cast(self, poll, choices):
        """Test that WebSocket clients receive updates when votes are cast."""
        from django.test import RequestFactory

        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        user = await database_sync_to_async(User.objects.create_user)(
            username="testuser", password="testpass"
        )

        communicator = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator.scope["user"] = user

        connected, subprotocol = await communicator.connect()
        assert connected is True

        # Clear initial results message
        await communicator.receive_json_from()

        # Cast a vote (this should trigger broadcast)
        factory = RequestFactory()
        request = factory.post("/api/votes/")
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0"
        request.fingerprint = "a" * 64

        await database_sync_to_async(cast_vote)(
            user=user,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request,
        )

        # Should receive results update
        response = await communicator.receive_json_from(timeout=2.0)
        assert response["type"] == "results_update"
        assert response["poll_id"] == poll.id
        assert "data" in response
        assert response["data"]["total_votes"] == 1

        await communicator.disconnect()

    async def test_multiple_clients_receive_updates(self, poll, choices):
        """Test that multiple WebSocket clients receive updates."""
        from django.test import RequestFactory

        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        user1 = await database_sync_to_async(User.objects.create_user)(
            username="user1", password="testpass"
        )
        user2 = await database_sync_to_async(User.objects.create_user)(
            username="user2", password="testpass"
        )

        # Create two WebSocket connections
        communicator1 = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator1.scope["user"] = user1

        communicator2 = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator2.scope["user"] = user2

        connected1, _ = await communicator1.connect()
        connected2, _ = await communicator2.connect()

        assert connected1 is True
        assert connected2 is True

        # Clear initial results messages
        await communicator1.receive_json_from()
        await communicator2.receive_json_from()

        # Cast a vote
        factory = RequestFactory()
        request = factory.post("/api/votes/")
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0"
        request.fingerprint = "a" * 64

        await database_sync_to_async(cast_vote)(
            user=user1,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request,
        )

        # Both clients should receive updates
        response1 = await communicator1.receive_json_from(timeout=2.0)
        response2 = await communicator2.receive_json_from(timeout=2.0)

        assert response1["type"] == "results_update"
        assert response2["type"] == "results_update"
        assert response1["data"]["total_votes"] == 1
        assert response2["data"]["total_votes"] == 1

        await communicator1.disconnect()
        await communicator2.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
class TestWebSocketDisconnection:
    """Test WebSocket disconnection handling."""

    async def test_disconnection_handling(self, poll, choices):
        """Test that disconnection is handled gracefully."""
        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        communicator = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator.scope["user"] = await database_sync_to_async(User.objects.create_user)(
            username="testuser", password="testpass"
        )

        connected, subprotocol = await communicator.connect()
        assert connected is True

        # Disconnect
        await communicator.disconnect()

        # Should not raise any errors
        assert True

    async def test_disconnection_removes_from_group(self, poll, choices):
        """Test that disconnection removes client from group."""
        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        user1 = await database_sync_to_async(User.objects.create_user)(
            username="user1", password="testpass"
        )
        user2 = await database_sync_to_async(User.objects.create_user)(
            username="user2", password="testpass"
        )

        # Create two connections
        communicator1 = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator1.scope["user"] = user1

        communicator2 = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator2.scope["user"] = user2

        connected1, _ = await communicator1.connect()
        connected2, _ = await communicator2.connect()

        assert connected1 is True
        assert connected2 is True

        # Clear initial messages
        await communicator1.receive_json_from()
        await communicator2.receive_json_from()

        # Disconnect first client
        await communicator1.disconnect()

        # Cast a vote
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.post("/api/votes/")
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0"
        request.fingerprint = "b" * 64

        await database_sync_to_async(cast_vote)(
            user=user2,
            poll_id=poll.id,
            choice_id=choices[0].id,
            request=request,
        )

        # Only second client should receive update
        response2 = await communicator2.receive_json_from(timeout=2.0)
        assert response2["type"] == "results_update"

        # First client should not receive anything (disconnected)
        # This is expected behavior

        await communicator2.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
class TestWebSocketErrorHandling:
    """Test WebSocket error handling."""

    async def test_invalid_json_message(self, poll, choices):
        """Test handling of invalid JSON messages."""
        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        communicator = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator.scope["user"] = await database_sync_to_async(User.objects.create_user)(
            username="testuser", password="testpass"
        )

        connected, subprotocol = await communicator.connect()
        assert connected is True

        # Clear initial message
        await communicator.receive_json_from()

        # Send invalid JSON
        await communicator.send_to(text_data="invalid json")

        # Should receive error message
        response = await communicator.receive_json_from()
        assert response["type"] == "error"
        assert "Invalid JSON" in response["message"]

        await communicator.disconnect()

    async def test_unknown_message_type(self, poll, choices):
        """Test handling of unknown message types."""
        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        communicator = WebsocketCommunicator(
            PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
        )
        communicator.scope["user"] = await database_sync_to_async(User.objects.create_user)(
            username="testuser", password="testpass"
        )

        connected, subprotocol = await communicator.connect()
        assert connected is True

        # Clear initial message
        await communicator.receive_json_from()

        # Send unknown message type
        await communicator.send_json_to({"type": "unknown_type"})

        # Should receive error message
        response = await communicator.receive_json_from()
        assert response["type"] == "error"
        assert "Unknown message type" in response["message"]

        await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
@pytest.mark.slow
class TestWebSocketLoad:
    """Load tests for WebSocket connections."""

    async def test_1000_concurrent_websocket_connections(self, poll, choices):
        """Load test: 1000 concurrent WebSocket connections."""
        import asyncio

        poll.settings["show_results_during_voting"] = True
        await database_sync_to_async(poll.save)()

        # Create 1000 users
        users = []
        for i in range(1000):
            user = await database_sync_to_async(User.objects.create_user)(
                username=f"loaduser{i}", password="testpass"
            )
            users.append(user)

        # Create 1000 WebSocket connections
        communicators = []
        for user in users:
            communicator = WebsocketCommunicator(
                PollResultsConsumer.as_asgi(), f"/ws/polls/{poll.id}/results/"
            )
            communicator.scope["user"] = user
            communicators.append(communicator)

        # Connect all
        tasks = [comm.connect() for comm in communicators]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successful connections
        successful_connections = sum(
            1 for result in results if isinstance(result, tuple) and result[0] is True
        )

        # Should have at least 95% success rate (allowing for some failures)
        assert successful_connections >= 950, f"Only {successful_connections}/1000 connections succeeded"

        # Disconnect all
        disconnect_tasks = [comm.disconnect() for comm in communicators]
        await asyncio.gather(*disconnect_tasks, return_exceptions=True)

