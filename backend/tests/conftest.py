"""
Pytest configuration and fixtures.
"""

import pytest
from apps.polls.models import Choice, Poll
from django.contrib.auth.models import User

# Ensure pytest-django is loaded
pytest_plugins = ["pytest_django"]


@pytest.fixture(scope="session", autouse=True)
def django_db_setup_ensure_migrations(django_db_setup, django_db_blocker):
    """Ensure all migrations are applied, including custom apps."""
    with django_db_blocker.unblock():
        from django.core.management import call_command

        # Run migrations explicitly to ensure all apps' migrations are applied
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
    choice1 = Choice.objects.create(poll=poll, text="Choice 1")
    choice2 = Choice.objects.create(poll=poll, text="Choice 2")
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
