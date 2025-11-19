"""
Load test for graceful degradation.

Tests:
- System behavior under extreme load
- Error handling
- Rate limiting behavior
- Service degradation patterns
"""

import random
import time
from locust import HttpUser, task, between, events
from locust.contrib.fasthttp import FastHttpUser


class DegradationTestUser(HttpUser):
    """
    Tests system behavior under stress and graceful degradation.
    """
    
    wait_time = between(0.1, 0.3)  # Aggressive load
    
    def on_start(self):
        """Set up user."""
        self.username = f"degrade_{random.randint(10000, 99999)}"
        self.password = "testpass123"
        
        try:
            self.client.post(
                "/api/v1/users/register/",
                json={
                    "username": self.username,
                    "email": f"{self.username}@degrade.com",
                    "password": self.password,
                },
            )
        except:
            pass
        
        try:
            response = self.client.post(
                "/api/v1/users/login/",
                json={"username": self.username, "password": self.password},
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token") or data.get("access")
                self.client.headers.update({"Authorization": f"Bearer {self.token}"})
        except:
            pass
    
    @task(10)
    def test_rate_limiting(self):
        """Test rate limiting behavior."""
        # Rapid requests to trigger rate limiting
        response = self.client.post(
            "/api/v1/votes/cast/",
            json={
                "poll_id": 1,  # May not exist, but tests rate limiting
                "choice_id": 1,
            },
            catch_response=True,
            name="Degradation: Rate Limit",
        )
        
        if response.status_code == 429:
            # Rate limited - this is expected graceful degradation
            response.success()
        elif response.status_code in [200, 201, 400, 404, 409]:
            response.success()
        else:
            response.failure(f"Unexpected status: {response.status_code}")
    
    @task(5)
    def test_error_handling(self):
        """Test error handling under load."""
        # Intentionally send invalid requests
        invalid_data = [
            {"poll_id": None, "choice_id": 1},
            {"poll_id": 999999, "choice_id": 1},
            {"poll_id": 1, "choice_id": 999999},
            {},  # Empty data
        ]
        
        data = random.choice(invalid_data)
        response = self.client.post(
            "/api/v1/votes/cast/",
            json=data,
            catch_response=True,
            name="Degradation: Error Handling",
        )
        
        # All error responses should be handled gracefully (4xx, not 5xx)
        if 400 <= response.status_code < 500:
            response.success()  # Graceful error handling
        elif response.status_code >= 500:
            response.failure(f"Server error: {response.status_code}")
        else:
            response.success()
    
    @task(3)
    def test_timeout_handling(self):
        """Test timeout handling."""
        # Request that might timeout
        try:
            response = self.client.get(
                "/api/v1/polls/",
                timeout=0.1,  # Very short timeout
                catch_response=True,
                name="Degradation: Timeout",
            )
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")
        except Exception as e:
            # Timeout is expected
            events.request.fire(
                request_type="GET",
                name="Degradation: Timeout",
                response_time=0,
                response_length=0,
                exception=str(e),
            )


class ExtremeLoadUser(FastHttpUser):
    """
    Extreme load user for stress testing.
    """
    
    wait_time = between(0.05, 0.2)  # Very aggressive
    
    def on_start(self):
        """Quick setup."""
        self.username = f"extreme_{random.randint(100000, 999999)}"
        self.password = "testpass123"
        
        try:
            self.client.post(
                "/api/v1/users/register/",
                json={
                    "username": self.username,
                    "email": f"{self.username}@extreme.com",
                    "password": self.password,
                },
            )
        except:
            pass
    
    @task
    def extreme_request(self):
        """Make extreme number of requests."""
        self.client.get("/api/v1/polls/", name="Extreme: Poll List")


# Degradation monitoring
degradation_metrics = {
    "error_rate": 0,
    "slow_requests": 0,
    "timeouts": 0,
}


@events.request.add_listener
def track_degradation(request_type, name, response_time, response_length, exception, **kwargs):
    """Track degradation metrics."""
    if exception:
        degradation_metrics["error_rate"] += 1
    
    if response_time > 5000:  # >5 seconds
        degradation_metrics["slow_requests"] += 1
    
    if "timeout" in str(exception).lower():
        degradation_metrics["timeouts"] += 1


@events.test_stop.add_listener
def report_degradation(environment, **kwargs):
    """Report degradation metrics."""
    stats = environment.stats
    total_requests = stats.total.num_requests
    
    if total_requests > 0:
        error_rate = (degradation_metrics["error_rate"] / total_requests) * 100
        slow_rate = (degradation_metrics["slow_requests"] / total_requests) * 100
        
        print("\n" + "=" * 80)
        print("GRACEFUL DEGRADATION REPORT")
        print("=" * 80)
        print(f"Total Requests: {total_requests}")
        print(f"Error Rate: {error_rate:.2f}%")
        print(f"Slow Requests (>5s): {slow_rate:.2f}%")
        print(f"Timeouts: {degradation_metrics['timeouts']}")
        print(f"Average Response Time: {stats.total.avg_response_time:.2f}ms")
        print(f"95th Percentile: {stats.total.get_response_time_percentile(0.95):.2f}ms")
        print(f"99th Percentile: {stats.total.get_response_time_percentile(0.99):.2f}ms")
        
        # Identify bottlenecks
        print("\nBottleneck Analysis:")
        for name, entry in stats.entries.items():
            if entry.num_requests > 100:  # Only show endpoints with significant traffic
                p95 = entry.get_response_time_percentile(0.95)
                if p95 > 1000:  # >1 second for 95th percentile
                    print(f"  {name}: P95={p95:.2f}ms, Avg={entry.avg_response_time:.2f}ms, Requests={entry.num_requests}")

