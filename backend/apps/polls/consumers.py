"""
WebSocket consumers for poll results.
"""

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

from apps.polls.models import Poll
from apps.polls.services import calculate_poll_results, can_view_results, get_poll_group_name

logger = logging.getLogger(__name__)


class PollResultsConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time poll results.
    
    Handles:
    - Connection/disconnection
    - Subscribing to poll results
    - Unsubscribing from poll results
    - Broadcasting vote updates
    """

    async def connect(self):
        """Handle WebSocket connection."""
        self.poll_id = self.scope["url_route"]["kwargs"]["poll_id"]
        self.group_name = get_poll_group_name(self.poll_id)
        self.user = self.scope.get("user", AnonymousUser())

        # Check if poll exists and user can view results
        poll = await self.get_poll()
        if not poll:
            await self.close(code=4004)  # Not Found
            return

        if not await self.can_view_results(poll):
            await self.close(code=4003)  # Forbidden
            return

        # Join room group
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        # Accept connection
        await self.accept()

        # Send initial results
        await self.send_initial_results()

        logger.info(
            f"WebSocket connected: poll_id={self.poll_id}, user={self.user.username if self.user.is_authenticated else 'anonymous'}"
        )

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave room group
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

        logger.info(
            f"WebSocket disconnected: poll_id={self.poll_id}, close_code={close_code}"
        )

    async def receive(self, text_data):
        """Handle messages received from WebSocket."""
        try:
            data = json.loads(text_data)
            message_type = data.get("type")

            if message_type == "subscribe":
                # Already subscribed on connect, but send current results
                await self.send_initial_results()
            elif message_type == "unsubscribe":
                # Leave group
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "unsubscribed",
                            "poll_id": self.poll_id,
                            "message": "Unsubscribed from poll results",
                        }
                    )
                )
            elif message_type == "ping":
                # Heartbeat/ping
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "pong",
                            "poll_id": self.poll_id,
                        }
                    )
                )
            else:
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": f"Unknown message type: {message_type}",
                        }
                    )
                )
        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Invalid JSON format",
                    }
                )
            )
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Internal server error",
                    }
                )
            )

    async def send_initial_results(self):
        """Send initial poll results to the client."""
        try:
            results = await self.get_poll_results()
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "results",
                        "poll_id": self.poll_id,
                        "data": results,
                    }
                )
            )
        except Exception as e:
            logger.error(f"Error sending initial results: {e}")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Failed to fetch poll results",
                    }
                )
            )

    async def poll_results_update(self, event):
        """
        Handle poll results update broadcast.
        
        This method is called when a vote is cast and results are broadcast.
        """
        try:
            results = event.get("results")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "results_update",
                        "poll_id": self.poll_id,
                        "data": results,
                    }
                )
            )
        except Exception as e:
            logger.error(f"Error sending results update: {e}")

    @database_sync_to_async
    def get_poll(self):
        """Get poll from database."""
        try:
            return Poll.objects.get(id=self.poll_id)
        except Poll.DoesNotExist:
            return None

    @database_sync_to_async
    def can_view_results(self, poll):
        """Check if user can view poll results."""
        return can_view_results(poll, self.user)

    @database_sync_to_async
    def get_poll_results(self):
        """Get poll results from database."""
        return calculate_poll_results(self.poll_id, use_cache=False)

