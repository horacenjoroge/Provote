"""
Locust load test for WebSocket connections.

Targets:
- 1000 concurrent WebSocket connections
- Test WebSocket message handling under load
- Test connection stability
"""

import asyncio
import json
import random
import time
from locust import User, task, between, events
from locust.contrib.fasthttp import FastHttpUser
import websockets
from websockets.client import WebSocketClientProtocol


class WebSocketUser(User):
    """
    Simulates a user with WebSocket connection for real-time poll results.
    """
    
    wait_time = between(1, 5)
    abstract = True
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ws: WebSocketClientProtocol = None
        self.poll_id = None
        self.connected = False
    
    def on_start(self):
        """Establish WebSocket connection."""
        # Get a poll ID first via HTTP
        try:
            response = self.client.get("/api/v1/polls/")
            if response.status_code == 200:
                polls = response.json().get("results", response.json())
                if polls:
                    self.poll_id = polls[0].get("id")
        except:
            pass
        
        if not self.poll_id:
            return
        
        # Connect WebSocket
        try:
            ws_url = self.host.replace("http://", "ws://").replace("https://", "wss://")
            ws_path = f"/ws/polls/{self.poll_id}/results/"
            
            # Run async connection in event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.ws = loop.run_until_complete(
                websockets.connect(f"{ws_url}{ws_path}")
            )
            self.connected = True
            
            # Receive initial message
            try:
                initial_msg = loop.run_until_complete(asyncio.wait_for(self.ws.recv(), timeout=2.0))
                data = json.loads(initial_msg)
                if data.get("type") == "results":
                    events.request.fire(
                        request_type="WS",
                        name="WebSocket Connect",
                        response_time=0,
                        response_length=len(initial_msg),
                        exception=None,
                    )
            except asyncio.TimeoutError:
                pass
        except Exception as e:
            self.connected = False
            events.request.fire(
                request_type="WS",
                name="WebSocket Connect",
                response_time=0,
                response_length=0,
                exception=str(e),
            )
    
    def on_stop(self):
        """Close WebSocket connection."""
        if self.ws and self.connected:
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.ws.close())
            except:
                pass
    
    @task
    def receive_updates(self):
        """Receive WebSocket updates."""
        if not self.connected or not self.ws:
            return
        
        try:
            loop = asyncio.get_event_loop()
            start_time = time.time()
            message = loop.run_until_complete(
                asyncio.wait_for(self.ws.recv(), timeout=5.0)
            )
            response_time = (time.time() - start_time) * 1000
            
            data = json.loads(message)
            events.request.fire(
                request_type="WS",
                name="WebSocket Receive",
                response_time=response_time,
                response_length=len(message),
                exception=None,
            )
        except asyncio.TimeoutError:
            # No message received (normal)
            pass
        except Exception as e:
            events.request.fire(
                request_type="WS",
                name="WebSocket Receive",
                response_time=0,
                response_length=0,
                exception=str(e),
            )


class WebSocketLoadUser(WebSocketUser):
    """WebSocket user for load testing."""
    pass


# Note: WebSocket testing with Locust requires additional setup
# For production load testing, consider using dedicated WebSocket load testing tools
# or extending Locust with custom WebSocket support

