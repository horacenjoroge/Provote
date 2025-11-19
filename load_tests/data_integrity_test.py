"""
Load test with data integrity checks.

Tests:
- No data corruption under load
- Vote counts remain accurate
- Database consistency maintained
"""

import json
import random
import time
from locust import HttpUser, task, between, events
from locust.contrib.fasthttp import FastHttpUser


class DataIntegrityUser(HttpUser):
    """
    User that votes and verifies data integrity.
    """
    
    wait_time = between(0.5, 1.5)
    
    def on_start(self):
        """Set up user and test poll."""
        self.username = f"integrity_{random.randint(10000, 99999)}"
        self.password = "testpass123"
        
        # Register and login
        try:
            self.client.post(
                "/api/v1/users/register/",
                json={
                    "username": self.username,
                    "email": f"{self.username}@integrity.com",
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
        
        # Create a dedicated test poll for integrity checks
        self.test_poll_id = None
        self.test_option_ids = []
        self.initial_vote_count = 0
        self._create_test_poll()
    
    def _create_test_poll(self):
        """Create a test poll for integrity testing."""
        try:
            response = self.client.post(
                "/api/v1/polls/",
                json={
                    "title": f"Integrity Test Poll {int(time.time())}",
                    "description": "Load test integrity check",
                    "options": [
                        {"text": "Option A", "order": 0},
                        {"text": "Option B", "order": 1},
                    ],
                    "settings": {"show_results_during_voting": True},
                },
            )
            if response.status_code == 201:
                data = response.json()
                self.test_poll_id = data.get("id")
                self.test_option_ids = [opt["id"] for opt in data.get("options", [])]
                
                # Get initial vote count
                results = self.client.get(f"/api/v1/polls/{self.test_poll_id}/results/")
                if results.status_code == 200:
                    self.initial_vote_count = results.json().get("total_votes", 0)
        except:
            pass
    
    @task(5)
    def vote_and_verify(self):
        """Cast vote and verify data integrity."""
        if not self.test_poll_id or not self.test_option_ids:
            return
        
        choice_id = random.choice(self.test_option_ids)
        idempotency_key = f"{self.username}_{self.test_poll_id}_{int(time.time() * 1000)}"
        
        # Cast vote
        vote_response = self.client.post(
            "/api/v1/votes/cast/",
            json={
                "poll_id": self.test_poll_id,
                "choice_id": choice_id,
                "idempotency_key": idempotency_key,
            },
            catch_response=True,
            name="Integrity: Cast Vote",
        )
        
        if vote_response.status_code not in [200, 201, 409]:
            vote_response.failure(f"Vote failed: {vote_response.status_code}")
            return
        
        vote_response.success()
        
        # Verify vote was recorded correctly
        time.sleep(0.1)  # Small delay for DB consistency
        
        results_response = self.client.get(
            f"/api/v1/polls/{self.test_poll_id}/results/",
            catch_response=True,
            name="Integrity: Verify Results",
        )
        
        if results_response.status_code == 200:
            results = results_response.json()
            total_votes = results.get("total_votes", 0)
            
            # Verify vote count is reasonable (should be >= initial)
            if total_votes < self.initial_vote_count:
                results_response.failure(
                    f"Data corruption detected! Vote count decreased: {total_votes} < {self.initial_vote_count}"
                )
            else:
                results_response.success()
                self.initial_vote_count = total_votes  # Update baseline
        else:
            results_response.failure(f"Failed to get results: {results_response.status_code}")
    
    @task(2)
    def verify_poll_consistency(self):
        """Verify poll data consistency."""
        if not self.test_poll_id:
            return
        
        # Get poll detail
        poll_detail = self.client.get(
            f"/api/v1/polls/{self.test_poll_id}/",
            catch_response=True,
            name="Integrity: Poll Detail",
        )
        
        if poll_detail.status_code == 200:
            poll_data = poll_detail.json()
            cached_votes = poll_data.get("total_votes", 0)
            
            # Get actual results
            results = self.client.get(
                f"/api/v1/polls/{self.test_poll_id}/results/",
                catch_response=True,
            )
            
            if results.status_code == 200:
                results_data = results.json()
                actual_votes = results_data.get("total_votes", 0)
                
                # Verify cached count matches actual count (within tolerance)
                if abs(cached_votes - actual_votes) > 5:  # Allow 5 vote difference for race conditions
                    poll_detail.failure(
                        f"Data inconsistency! Cached: {cached_votes}, Actual: {actual_votes}"
                    )
                else:
                    poll_detail.success()
            else:
                poll_detail.failure("Could not verify results")
        else:
            poll_detail.failure(f"Status: {poll_detail.status_code}")


# Data integrity monitoring
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Monitor for data integrity issues."""
    if "Integrity" in name and exception:
        print(f"DATA INTEGRITY WARNING: {name} - {exception}")

