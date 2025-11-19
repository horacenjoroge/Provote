"""
Main Locust configuration file.

Run with:
    locust -f locustfile.py --host=http://localhost:8001

Or with specific user classes:
    locust -f locustfile.py --host=http://localhost:8001 VotingUser HighVolumeVotingUser
"""

from voting_load_test import VotingUser, HighVolumeVotingUser
from api_performance_test import APIPerformanceUser, DatabaseQueryPerformanceUser
from data_integrity_test import DataIntegrityUser
from graceful_degradation_test import DegradationTestUser, ExtremeLoadUser

# Default user classes for general load testing
# Override with --users flag when running Locust
# Example: locust -f locustfile.py --users VotingUser HighVolumeVotingUser

