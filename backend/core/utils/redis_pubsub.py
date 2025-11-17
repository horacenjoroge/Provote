"""
Redis Pub/Sub utilities for scaling WebSockets across multiple servers.

This module provides:
- Publisher: Publishes vote events to Redis
- Subscriber: Subscribes to Redis events and broadcasts to local WebSocket clients
- Graceful shutdown handling
- Connection failure recovery
"""

import json
import logging
import signal
import threading
import time
from typing import Any, Callable, Dict, Optional

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

# Redis Pub/Sub channel name for vote events
VOTE_EVENTS_CHANNEL = "provote:vote_events"

# Redis connection pool (shared across publisher and subscriber)
_redis_pool: Optional[redis.ConnectionPool] = None
_shutdown_event = threading.Event()


def get_redis_connection() -> redis.Redis:
    """
    Get a Redis connection from the pool.
    
    Returns:
        Redis client instance
    """
    global _redis_pool
    
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
    
    return redis.Redis(connection_pool=_redis_pool)


class VoteEventPublisher:
    """
    Publisher for vote events to Redis Pub/Sub.
    
    Publishes vote events that can be consumed by multiple server instances.
    """
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self._connect()
    
    def _connect(self):
        """Establish Redis connection."""
        try:
            self.redis_client = get_redis_connection()
            # Test connection
            self.redis_client.ping()
            logger.info("VoteEventPublisher: Connected to Redis")
        except redis.ConnectionError as e:
            logger.error(f"VoteEventPublisher: Failed to connect to Redis: {e}")
            self.redis_client = None
        except Exception as e:
            logger.error(f"VoteEventPublisher: Unexpected error connecting to Redis: {e}")
            self.redis_client = None
    
    def publish_vote_event(self, poll_id: int, vote_id: Optional[int] = None) -> bool:
        """
        Publish a vote event to Redis Pub/Sub.
        
        Args:
            poll_id: The poll ID that received a vote
            vote_id: Optional vote ID (for logging/debugging)
            
        Returns:
            True if published successfully, False otherwise
        """
        if not self.redis_client:
            try:
                self._connect()
            except Exception as e:
                logger.error(f"VoteEventPublisher: Failed to reconnect: {e}")
                return False
        
        if not self.redis_client:
            logger.warning("VoteEventPublisher: Redis not available, skipping publish")
            return False
        
        try:
            event_data = {
                "type": "vote_cast",
                "poll_id": poll_id,
                "vote_id": vote_id,
                "timestamp": time.time(),
            }
            
            message = json.dumps(event_data)
            subscribers = self.redis_client.publish(VOTE_EVENTS_CHANNEL, message)
            
            logger.debug(
                f"VoteEventPublisher: Published vote event for poll {poll_id} "
                f"(vote_id={vote_id}, subscribers={subscribers})"
            )
            return True
            
        except redis.ConnectionError:
            logger.warning("VoteEventPublisher: Connection lost, attempting reconnect")
            self._connect()
            return False
        except Exception as e:
            logger.error(f"VoteEventPublisher: Error publishing vote event: {e}")
            return False
    
    def is_connected(self) -> bool:
        """Check if publisher is connected to Redis."""
        if not self.redis_client:
            return False
        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False


# Global publisher instance
_publisher_instance: Optional[VoteEventPublisher] = None


def get_publisher() -> VoteEventPublisher:
    """Get or create the global VoteEventPublisher instance."""
    global _publisher_instance
    if _publisher_instance is None:
        _publisher_instance = VoteEventPublisher()
    return _publisher_instance


class VoteEventSubscriber:
    """
    Subscriber for vote events from Redis Pub/Sub.
    
    Listens for vote events and broadcasts them to local WebSocket clients
    via Django Channels.
    """
    
    def __init__(self, event_handler: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Initialize the subscriber.
        
        Args:
            event_handler: Optional callback function to handle events.
                          If None, uses default handler that broadcasts via Channels.
        """
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.event_handler = event_handler or self._default_event_handler
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.reconnect_delay = 5  # seconds
        self.max_reconnect_delay = 60  # seconds
        self.current_reconnect_delay = self.reconnect_delay
        
    def _default_event_handler(self, event_data: Dict[str, Any]):
        """
        Default event handler that broadcasts to local WebSocket clients.
        
        Args:
            event_data: Event data dictionary
        """
        try:
            poll_id = event_data.get("poll_id")
            if not poll_id:
                logger.warning("VoteEventSubscriber: Received event without poll_id")
                return
            
            # Import here to avoid circular imports
            from apps.polls.services import broadcast_poll_results_update
            
            # Broadcast to local WebSocket clients
            broadcast_poll_results_update(poll_id)
            
            logger.debug(
                f"VoteEventSubscriber: Broadcasted results update for poll {poll_id}"
            )
        except Exception as e:
            logger.error(f"VoteEventSubscriber: Error in event handler: {e}")
    
    def _connect(self) -> bool:
        """Establish Redis connection and subscribe to channel."""
        try:
            self.redis_client = get_redis_connection()
            self.redis_client.ping()
            
            self.pubsub = self.redis_client.pubsub()
            self.pubsub.subscribe(VOTE_EVENTS_CHANNEL)
            
            logger.info("VoteEventSubscriber: Connected to Redis and subscribed to channel")
            self.current_reconnect_delay = self.reconnect_delay
            return True
        except redis.ConnectionError as e:
            logger.error(f"VoteEventSubscriber: Failed to connect to Redis: {e}")
            self.pubsub = None
            self.redis_client = None
            return False
        except Exception as e:
            logger.error(f"VoteEventSubscriber: Unexpected error connecting: {e}")
            self.pubsub = None
            self.redis_client = None
            return False
    
    def _disconnect(self):
        """Close Redis connection."""
        try:
            if self.pubsub:
                self.pubsub.unsubscribe()
                self.pubsub.close()
                self.pubsub = None
            if self.redis_client:
                self.redis_client.close()
                self.redis_client = None
            logger.info("VoteEventSubscriber: Disconnected from Redis")
        except Exception as e:
            logger.error(f"VoteEventSubscriber: Error disconnecting: {e}")
    
    def _listen_loop(self):
        """Main listening loop for Redis Pub/Sub messages."""
        logger.info("VoteEventSubscriber: Starting listen loop")
        
        while self.running and not _shutdown_event.is_set():
            try:
                if not self.pubsub:
                    if not self._connect():
                        # Exponential backoff for reconnection
                        logger.warning(
                            f"VoteEventSubscriber: Reconnecting in {self.current_reconnect_delay}s"
                        )
                        time.sleep(self.current_reconnect_delay)
                        self.current_reconnect_delay = min(
                            self.current_reconnect_delay * 2,
                            self.max_reconnect_delay
                        )
                        continue
                
                # Get message with timeout
                message = self.pubsub.get_message(timeout=1.0, ignore_subscribe_messages=True)
                
                if message is None:
                    # Timeout - check connection health
                    try:
                        if self.redis_client:
                            self.redis_client.ping()
                    except Exception:
                        logger.warning("VoteEventSubscriber: Connection lost, reconnecting")
                        self._disconnect()
                        continue
                    continue
                
                if message["type"] == "message":
                    try:
                        event_data = json.loads(message["data"])
                        self.event_handler(event_data)
                    except json.JSONDecodeError as e:
                        logger.error(f"VoteEventSubscriber: Invalid JSON in message: {e}")
                    except Exception as e:
                        logger.error(f"VoteEventSubscriber: Error processing message: {e}")
                
            except redis.ConnectionError:
                logger.warning("VoteEventSubscriber: Connection error, reconnecting")
                self._disconnect()
                self.current_reconnect_delay = min(
                    self.current_reconnect_delay * 2,
                    self.max_reconnect_delay
                )
            except Exception as e:
                logger.error(f"VoteEventSubscriber: Unexpected error in listen loop: {e}")
                time.sleep(1)
        
        logger.info("VoteEventSubscriber: Listen loop stopped")
        self._disconnect()
    
    def start(self):
        """Start the subscriber in a background thread."""
        if self.running:
            logger.warning("VoteEventSubscriber: Already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        logger.info("VoteEventSubscriber: Started")
    
    def stop(self):
        """Stop the subscriber."""
        if not self.running:
            return
        
        logger.info("VoteEventSubscriber: Stopping...")
        self.running = False
        
        if self.thread:
            self.thread.join(timeout=5)
        
        self._disconnect()
        logger.info("VoteEventSubscriber: Stopped")
    
    def is_running(self) -> bool:
        """Check if subscriber is running."""
        return self.running


# Global subscriber instance
_subscriber_instance: Optional[VoteEventSubscriber] = None


def get_subscriber() -> VoteEventSubscriber:
    """Get or create the global VoteEventSubscriber instance."""
    global _subscriber_instance
    if _subscriber_instance is None:
        _subscriber_instance = VoteEventSubscriber()
    return _subscriber_instance


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        _shutdown_event.set()
        if _subscriber_instance:
            _subscriber_instance.stop()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def publish_vote_event(poll_id: int, vote_id: Optional[int] = None) -> bool:
    """
    Convenience function to publish a vote event.
    
    Args:
        poll_id: The poll ID that received a vote
        vote_id: Optional vote ID
        
    Returns:
        True if published successfully, False otherwise
    """
    publisher = get_publisher()
    return publisher.publish_vote_event(poll_id, vote_id)

