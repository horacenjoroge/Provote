"""
Locust performance test for API endpoints.

Tests:
- API response times under load
- Database query performance
- Endpoint-specific performance
"""

import random
import time
from locust import HttpUser, task, between, events
from locust.contrib.fasthttp import FastHttpUser


class APIPerformanceUser(HttpUser):
    """
    Tests API performance across all endpoints.
    """
    
    wait_time = between(0.5, 2)
    
    def __init__(self, *args, **kwargs):
        """Initialize with load test header to bypass rate limiting."""
        super().__init__(*args, **kwargs)
        # Add header to bypass rate limiting during load tests
        self.client.headers.update({"X-Load-Test": "true"})
    
    def on_start(self):
        """Set up user (anonymous for load testing)."""
        # Note: API uses SessionAuthentication, no registration/login endpoints
        # We'll work as anonymous users for load testing
        self.username = f"perfuser_{random.randint(10000, 99999)}"
        
        # Cache poll IDs
        self.poll_ids = []
        self._load_polls()
    
    def _load_polls(self):
        """Load poll IDs for testing."""
        try:
            response = self.client.get("/api/v1/polls/")
            if response.status_code == 200:
                polls = response.json().get("results", response.json())
                self.poll_ids = [p.get("id") for p in polls[:20] if p.get("id")]
        except:
            pass
    
    @task(10)
    def test_poll_list_performance(self):
        """Test poll list endpoint performance."""
        with self.client.get(
            "/api/v1/polls/",
            catch_response=True,
            name="API: Poll List",
        ) as response:
            if response.status_code == 200:
                # Check response time
                if response.elapsed.total_seconds() > 1.0:
                    response.failure(f"Slow response: {response.elapsed.total_seconds():.2f}s")
                else:
                    response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(8)
    def test_poll_detail_performance(self):
        """Test poll detail endpoint performance."""
        if not self.poll_ids:
            return
        
        poll_id = random.choice(self.poll_ids)
        with self.client.get(
            f"/api/v1/polls/{poll_id}/",
            catch_response=True,
            name="API: Poll Detail",
        ) as response:
            if response.status_code == 200:
                if response.elapsed.total_seconds() > 0.5:
                    response.failure(f"Slow response: {response.elapsed.total_seconds():.2f}s")
                else:
                    response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(5)
    def test_vote_cast_performance(self):
        """Test vote casting endpoint performance."""
        if not self.poll_ids:
            return
        
        poll_id = random.choice(self.poll_ids)
        
        # Get poll options
        try:
            poll_response = self.client.get(f"/api/v1/polls/{poll_id}/")
            if poll_response.status_code == 200:
                options = poll_response.json().get("options", [])
                if not options:
                    return
                choice_id = random.choice([opt["id"] for opt in options])
                
                with self.client.post(
                    "/api/v1/votes/cast/",
                    json={
                        "poll_id": poll_id,
                        "choice_id": choice_id,
                        "idempotency_key": f"{self.username}_{poll_id}_{int(time.time() * 1000)}",
                    },
                    catch_response=True,
                    name="API: Cast Vote",
                ) as response:
                    if response.status_code in [200, 201, 409]:
                        if response.elapsed.total_seconds() > 1.0:
                            response.failure(f"Slow response: {response.elapsed.total_seconds():.2f}s")
                        else:
                            response.success()
                    else:
                        response.failure(f"Status: {response.status_code}")
        except:
            pass
    
    @task(3)
    def test_results_performance(self):
        """Test poll results endpoint performance."""
        if not self.poll_ids:
            return
        
        poll_id = random.choice(self.poll_ids)
        with self.client.get(
            f"/api/v1/polls/{poll_id}/results/",
            catch_response=True,
            name="API: Poll Results",
        ) as response:
            if response.status_code in [200, 403]:
                if response.elapsed.total_seconds() > 0.5:
                    response.failure(f"Slow response: {response.elapsed.total_seconds():.2f}s")
                else:
                    response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(2)
    def test_analytics_performance(self):
        """Test analytics endpoint performance."""
        if not self.poll_ids:
            return
        
        poll_id = random.choice(self.poll_ids)
        with self.client.get(
            f"/api/v1/polls/{poll_id}/analytics/",
            catch_response=True,
            name="API: Analytics",
        ) as response:
            if response.status_code in [200, 403, 404]:
                if response.elapsed.total_seconds() > 2.0:
                    response.failure(f"Slow response: {response.elapsed.total_seconds():.2f}s")
                else:
                    response.success()
            else:
                response.failure(f"Status: {response.status_code}")


class DatabaseQueryPerformanceUser(FastHttpUser):
    """
    Tests database query performance under load.
    """
    
    wait_time = between(0.1, 0.5)
    
    def __init__(self, *args, **kwargs):
        """Initialize with load test header to bypass rate limiting."""
        super().__init__(*args, **kwargs)
        # Add header to bypass rate limiting during load tests
        self.client.headers.update({"X-Load-Test": "true"})
    
    def on_start(self):
        """Set up user (anonymous for load testing)."""
        # Note: API uses SessionAuthentication, no registration/login endpoints
        # We'll work as anonymous users for load testing
        self.username = f"dbuser_{random.randint(10000, 99999)}"
    
    @task
    def test_complex_queries(self):
        """Test complex database queries."""
        # Test poll list with filters
        with self.client.get(
            "/api/v1/polls/?is_active=true&ordering=-created_at",
            catch_response=True,
            name="DB: Complex Query",
        ) as response:
            if response.status_code == 200:
                if response.elapsed.total_seconds() > 0.5:
                    response.failure(f"Slow query: {response.elapsed.total_seconds():.2f}s")
                else:
                    response.success()
            else:
                response.failure(f"Status: {response.status_code}")

