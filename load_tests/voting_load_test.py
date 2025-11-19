"""
Locust load test for voting API.

Targets:
- 1000 concurrent users voting
- 10k votes per second
- Test response times under load
- Test no data corruption
- Test graceful degradation
"""

import json
import random
import time
from locust import HttpUser, task, between, events
from locust.contrib.fasthttp import FastHttpUser


class VotingUser(HttpUser):
    """
    Simulates a user voting on polls.
    
    User behavior:
    1. Authenticate
    2. Browse polls
    3. Cast votes
    4. View results
    """
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    def on_start(self):
        """Called when a simulated user starts."""
        # Create or authenticate user
        self.username = f"loaduser_{random.randint(10000, 99999)}"
        self.password = "testpass123"
        
        # Register user
        try:
            response = self.client.post(
                "/api/v1/users/register/",
                json={
                    "username": self.username,
                    "email": f"{self.username}@loadtest.com",
                    "password": self.password,
                },
                catch_response=True,
            )
            if response.status_code in [201, 400]:  # 400 if user already exists
                response.success()
        except Exception as e:
            pass  # User might already exist
        
        # Login
        try:
            response = self.client.post(
                "/api/v1/users/login/",
                json={
                    "username": self.username,
                    "password": self.password,
                },
                catch_response=True,
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token") or data.get("access")
                self.client.headers.update({"Authorization": f"Bearer {self.token}"})
                response.success()
            else:
                response.failure(f"Login failed: {response.status_code}")
        except Exception as e:
            pass
        
        # Get available polls
        self.poll_ids = []
        self.poll_options = {}  # {poll_id: [option_ids]}
        self._load_polls()
    
    def _load_polls(self):
        """Load available polls and their options."""
        try:
            response = self.client.get("/api/v1/polls/", catch_response=True)
            if response.status_code == 200:
                polls = response.json().get("results", response.json())
                for poll in polls[:10]:  # Limit to first 10 polls
                    poll_id = poll.get("id")
                    if poll_id:
                        self.poll_ids.append(poll_id)
                        # Get poll details to get options
                        poll_detail = self.client.get(f"/api/v1/polls/{poll_id}/", catch_response=True)
                        if poll_detail.status_code == 200:
                            poll_data = poll_detail.json()
                            options = poll_data.get("options", [])
                            if options:
                                self.poll_options[poll_id] = [opt["id"] for opt in options]
                response.success()
            else:
                response.failure(f"Failed to load polls: {response.status_code}")
        except Exception as e:
            pass
    
    @task(3)
    def browse_polls(self):
        """Browse list of polls."""
        with self.client.get("/api/v1/polls/", catch_response=True, name="Browse Polls") as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(5)
    def cast_vote(self):
        """Cast a vote on a poll."""
        if not self.poll_ids or not self.poll_options:
            self._load_polls()
            return
        
        poll_id = random.choice(self.poll_ids)
        options = self.poll_options.get(poll_id, [])
        if not options:
            return
        
        choice_id = random.choice(options)
        idempotency_key = f"{self.username}_{poll_id}_{int(time.time() * 1000)}"
        
        with self.client.post(
            "/api/v1/votes/cast/",
            json={
                "poll_id": poll_id,
                "choice_id": choice_id,
                "idempotency_key": idempotency_key,
            },
            catch_response=True,
            name="Cast Vote",
        ) as response:
            if response.status_code in [200, 201, 409]:  # 409 = duplicate (expected)
                response.success()
            else:
                response.failure(f"Status: {response.status_code}, Response: {response.text[:100]}")
    
    @task(2)
    def view_poll_results(self):
        """View poll results."""
        if not self.poll_ids:
            return
        
        poll_id = random.choice(self.poll_ids)
        
        with self.client.get(
            f"/api/v1/polls/{poll_id}/results/",
            catch_response=True,
            name="View Results",
        ) as response:
            if response.status_code in [200, 403]:  # 403 = results hidden (expected)
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")
    
    @task(1)
    def view_poll_detail(self):
        """View poll details."""
        if not self.poll_ids:
            return
        
        poll_id = random.choice(self.poll_ids)
        
        with self.client.get(
            f"/api/v1/polls/{poll_id}/",
            catch_response=True,
            name="View Poll Detail",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")


class HighVolumeVotingUser(FastHttpUser):
    """
    High-volume voting user for 10k votes per second target.
    
    Uses FastHttpUser for better performance.
    Minimal wait time to maximize throughput.
    """
    
    wait_time = between(0.1, 0.5)  # Very short wait time
    
    def on_start(self):
        """Set up user for high-volume voting."""
        self.username = f"hvuser_{random.randint(100000, 999999)}"
        self.password = "testpass123"
        
        # Quick registration/login
        try:
            self.client.post(
                "/api/v1/users/register/",
                json={
                    "username": self.username,
                    "email": f"{self.username}@loadtest.com",
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
        
        # Pre-load a single poll for fast voting
        try:
            response = self.client.get("/api/v1/polls/")
            if response.status_code == 200:
                polls = response.json().get("results", response.json())
                if polls:
                    poll = polls[0]
                    self.poll_id = poll.get("id")
                    poll_detail = self.client.get(f"/api/v1/polls/{self.poll_id}/")
                    if poll_detail.status_code == 200:
                        options = poll_detail.json().get("options", [])
                        self.option_ids = [opt["id"] for opt in options] if options else []
        except:
            self.poll_id = None
            self.option_ids = []
    
    @task
    def rapid_vote(self):
        """Rapid voting for throughput testing."""
        if not self.poll_id or not self.option_ids:
            return
        
        choice_id = random.choice(self.option_ids)
        idempotency_key = f"{self.username}_{self.poll_id}_{int(time.time() * 1000000)}"
        
        with self.client.post(
            "/api/v1/votes/cast/",
            json={
                "poll_id": self.poll_id,
                "choice_id": choice_id,
                "idempotency_key": idempotency_key,
            },
            catch_response=True,
            name="Rapid Vote",
        ) as response:
            if response.status_code in [200, 201, 409]:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")


# Performance monitoring
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when the test starts."""
    print("=" * 80)
    print("LOAD TEST STARTED")
    print("=" * 80)
    print(f"Target: {environment.host}")
    print(f"Users: {environment.runner.target_user_count if hasattr(environment.runner, 'target_user_count') else 'N/A'}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when the test stops."""
    print("=" * 80)
    print("LOAD TEST COMPLETED")
    print("=" * 80)
    
    # Print statistics
    stats = environment.stats
    print("\nKey Metrics:")
    print(f"Total Requests: {stats.total.num_requests}")
    print(f"Total Failures: {stats.total.num_failures}")
    print(f"Failure Rate: {(stats.total.num_failures / stats.total.num_requests * 100) if stats.total.num_requests > 0 else 0:.2f}%")
    print(f"Average Response Time: {stats.total.avg_response_time:.2f}ms")
    print(f"Min Response Time: {stats.total.min_response_time:.2f}ms")
    print(f"Max Response Time: {stats.total.max_response_time:.2f}ms")
    print(f"Requests per Second: {stats.total.total_rps:.2f}")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Monitor individual requests for performance issues."""
    if response_time > 5000:  # Log slow requests (>5 seconds)
        print(f"SLOW REQUEST: {name} took {response_time:.2f}ms")
    
    if exception:
        print(f"REQUEST ERROR: {name} - {exception}")

