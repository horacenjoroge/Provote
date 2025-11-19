"""
Async WebSocket load test using asyncio.

For testing 1000 concurrent WebSocket connections.
Run separately from Locust tests.
"""

import asyncio
import json
import time
import websockets
from typing import List, Dict


class WebSocketLoadTest:
    """Async WebSocket load test."""
    
    def __init__(self, host: str, poll_id: int, num_connections: int = 1000):
        self.host = host.replace("http://", "ws://").replace("https://", "wss://")
        self.poll_id = poll_id
        self.num_connections = num_connections
        self.connections: List[websockets.WebSocketClientProtocol] = []
        self.stats = {
            "connected": 0,
            "failed": 0,
            "messages_received": 0,
            "errors": [],
            "connection_times": [],
            "message_times": [],
        }
    
    async def connect_websocket(self, index: int):
        """Connect a single WebSocket."""
        url = f"{self.host}/ws/polls/{self.poll_id}/results/"
        start_time = time.time()
        
        try:
            ws = await asyncio.wait_for(
                websockets.connect(url),
                timeout=10.0
            )
            connection_time = (time.time() - start_time) * 1000
            self.stats["connection_times"].append(connection_time)
            self.stats["connected"] += 1
            self.connections.append(ws)
            
            # Receive initial message
            try:
                msg_start = time.time()
                message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                msg_time = (time.time() - msg_start) * 1000
                self.stats["message_times"].append(msg_time)
                self.stats["messages_received"] += 1
            except asyncio.TimeoutError:
                pass
            
            return ws
        except Exception as e:
            self.stats["failed"] += 1
            self.stats["errors"].append(str(e))
            return None
    
    async def receive_messages(self, ws: websockets.WebSocketClientProtocol, duration: int = 60):
        """Receive messages from WebSocket."""
        end_time = time.time() + duration
        
        while time.time() < end_time:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                msg_time = time.time()
                self.stats["messages_received"] += 1
                self.stats["message_times"].append((time.time() - msg_time) * 1000)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.stats["errors"].append(str(e))
                break
    
    async def run_test(self, duration: int = 60):
        """Run the load test."""
        print(f"Starting WebSocket load test: {self.num_connections} connections")
        print(f"Poll ID: {self.poll_id}")
        print(f"Duration: {duration} seconds")
        print("=" * 80)
        
        # Connect all WebSockets
        print("Connecting WebSockets...")
        start_time = time.time()
        
        tasks = [self.connect_websocket(i) for i in range(self.num_connections)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        connect_time = time.time() - start_time
        print(f"Connected {self.stats['connected']}/{self.num_connections} in {connect_time:.2f}s")
        
        # Receive messages for duration
        print("Receiving messages...")
        receive_tasks = [
            self.receive_messages(ws, duration)
            for ws in self.connections
            if ws is not None
        ]
        
        if receive_tasks:
            await asyncio.gather(*receive_tasks, return_exceptions=True)
        
        # Close all connections
        print("Closing connections...")
        close_tasks = [ws.close() for ws in self.connections if ws is not None]
        await asyncio.gather(*close_tasks, return_exceptions=True)
        
        # Print statistics
        self.print_statistics()
    
    def print_statistics(self):
        """Print test statistics."""
        print("\n" + "=" * 80)
        print("WEBSOCKET LOAD TEST RESULTS")
        print("=" * 80)
        print(f"Total Connections Attempted: {self.num_connections}")
        print(f"Successful Connections: {self.stats['connected']}")
        print(f"Failed Connections: {self.stats['failed']}")
        print(f"Success Rate: {(self.stats['connected'] / self.num_connections) * 100:.2f}%")
        print(f"Messages Received: {self.stats['messages_received']}")
        
        if self.stats["connection_times"]:
            avg_conn = sum(self.stats["connection_times"]) / len(self.stats["connection_times"])
            max_conn = max(self.stats["connection_times"])
            min_conn = min(self.stats["connection_times"])
            print(f"\nConnection Times:")
            print(f"  Average: {avg_conn:.2f}ms")
            print(f"  Min: {min_conn:.2f}ms")
            print(f"  Max: {max_conn:.2f}ms")
        
        if self.stats["message_times"]:
            avg_msg = sum(self.stats["message_times"]) / len(self.stats["message_times"])
            max_msg = max(self.stats["message_times"])
            min_msg = min(self.stats["message_times"])
            print(f"\nMessage Receive Times:")
            print(f"  Average: {avg_msg:.2f}ms")
            print(f"  Min: {min_msg:.2f}ms")
            print(f"  Max: {max_msg:.2f}ms")
        
        if self.stats["errors"]:
            print(f"\nErrors: {len(self.stats['errors'])}")
            unique_errors = {}
            for error in self.stats["errors"]:
                unique_errors[error] = unique_errors.get(error, 0) + 1
            for error, count in unique_errors.items():
                print(f"  {error}: {count}")


async def main():
    """Main entry point."""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python websocket_load_async.py <host> <poll_id> [num_connections] [duration]")
        print("Example: python websocket_load_async.py http://localhost:8001 1 1000 60")
        sys.exit(1)
    
    host = sys.argv[1]
    poll_id = int(sys.argv[2])
    num_connections = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    duration = int(sys.argv[4]) if len(sys.argv) > 4 else 60
    
    test = WebSocketLoadTest(host, poll_id, num_connections)
    await test.run_test(duration)


if __name__ == "__main__":
    asyncio.run(main())

