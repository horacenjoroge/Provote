"""
Pytest configuration and fixtures for all tests.
This file makes fixtures available to all tests in backend/.
"""

import pytest
from apps.polls.models import Poll, PollOption
from django.contrib.auth.models import User

# Ensure pytest-django is loaded
pytest_plugins = ["pytest_django"]


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Override django_db_setup to ensure all migrations are applied."""
    # Let pytest-django do its initial setup first
    # This creates the test database and runs migrations

    # Then ensure all migrations are applied (in case some were missed)
    with django_db_blocker.unblock():
        from django.apps import apps
        from django.core.management import call_command

        # Ensure all apps are loaded
        apps.check_apps_ready()

        # Run migrations explicitly to ensure all apps' migrations are applied
        # This will apply any migrations that weren't applied during initial setup
        call_command("migrate", verbosity=1, interactive=False)


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture
def poll(db, user):
    """Create a test poll."""
    return Poll.objects.create(
        title="Test Poll",
        description="This is a test poll",
        created_by=user,
        is_active=True,
    )


@pytest.fixture
def choices(db, poll):
    """Create test choices for a poll."""
    choice1 = PollOption.objects.create(poll=poll, text="Choice 1", order=0)
    choice2 = PollOption.objects.create(poll=poll, text="Choice 2", order=1)
    return [choice1, choice2]


@pytest.fixture
def api_client():
    """Create a DRF API client."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def authenticated_client(api_client, user):
    """Create an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client
