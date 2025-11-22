# Developer Guide: Extending the System

**Version:** 1.0  
**Last Updated:** 2025-11-22  
**Project:** Provote - Professional Voting Platform

## Table of Contents

1. [Quick Start for New Developers](#1-quick-start-for-new-developers)
2. [Project Structure Deep Dive](#2-project-structure-deep-dive)
3. [Adding New Features](#3-adding-new-features)
4. [Testing Guide](#4-testing-guide)
5. [Code Style and Patterns](#5-code-style-and-patterns)
6. [Git Workflow](#6-git-workflow)
7. [Common Extension Patterns](#7-common-extension-patterns)
8. [Best Practices](#8-best-practices)

---

## 1. Quick Start for New Developers

### 1.1 Initial Setup

**Prerequisites:**
- Python 3.11+
- Docker & Docker Compose 2.0+
- Git
- Code editor (VS Code, PyCharm, etc.)

**First-Time Setup:**

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/provote.git
cd provote

# 2. Create .env file
cp .env.example .env
# Edit .env with your local settings (see below)

# 3. Start services with Docker
cd docker
docker-compose up -d

# 4. Run migrations
docker-compose exec web python manage.py migrate

# 5. Create superuser
docker-compose exec web python manage.py createsuperuser

# 6. Verify setup
docker-compose exec web python manage.py check
```

**Environment Variables (.env):**

```bash
# Minimum required for development
SECRET_KEY=dev-secret-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (Docker uses service names)
DB_NAME=provote_db
DB_USER=provote_user
DB_PASSWORD=provote_password
DB_HOST=db
DB_PORT=5432

# Redis (Docker uses service names)
REDIS_HOST=redis
REDIS_PORT=6379

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

**Verify Installation:**

```bash
# Check services are running
docker-compose ps

# Test API
curl http://localhost:8001/api/v1/

# Run tests
docker-compose exec web pytest backend/tests/test_integration.py -v
```

### 1.2 Development Workflow

**Daily Workflow:**

```bash
# 1. Start services
cd docker
docker-compose up -d

# 2. Check logs
docker-compose logs -f web

# 3. Run tests before committing
docker-compose exec web pytest

# 4. Format code
docker-compose exec web black backend/
docker-compose exec web isort backend/

# 5. Stop services (when done)
docker-compose down
```

---

## 2. Project Structure Deep Dive

### 2.1 Architecture Overview

```
provote/
├── backend/                    # Django project root
│   ├── apps/                  # Django applications (business logic)
│   │   ├── polls/             # Poll management
│   │   ├── votes/             # Voting functionality
│   │   ├── users/             # User management
│   │   ├── analytics/         # Analytics and reporting
│   │   └── notifications/     # Notifications
│   ├── config/                # Django configuration
│   │   └── settings/          # Environment-specific settings
│   ├── core/                  # Shared utilities (reusable across apps)
│   │   ├── middleware/        # Custom middleware
│   │   ├── exceptions/        # Custom exceptions
│   │   ├── services/          # Core services
│   │   ├── utils/             # Utility functions
│   │   ├── throttles.py       # Rate limiting
│   │   └── mixins.py          # View mixins
│   └── tests/                 # Integration tests
├── docker/                     # Docker configuration
├── requirements/              # Python dependencies
└── docs/                      # Documentation
```

### 2.2 Application Structure Pattern

Each Django app follows this structure:

```
apps/myapp/
├── __init__.py
├── apps.py                    # App configuration
├── models.py                  # Database models
├── serializers.py             # DRF serializers
├── views.py                   # ViewSets and views
├── urls.py                    # URL routing
├── services.py                # Business logic (if complex)
├── permissions.py             # Custom permissions (if needed)
├── admin.py                   # Django admin configuration
├── factories.py               # Factory Boy factories for tests
├── tests/                     # App-specific tests
│   ├── test_models.py
│   ├── test_views.py
│   └── test_services.py
└── migrations/                # Database migrations
```

### 2.3 Core Utilities

**Location:** `backend/core/`

**Purpose:** Shared code used across multiple apps

**Key Components:**

1. **Middleware** (`core/middleware/`):
   - `rate_limit.py` - Rate limiting
   - `audit_log.py` - Request logging
   - `fingerprint.py` - Browser fingerprinting

2. **Exceptions** (`core/exceptions/`):
   - Custom exception classes
   - Error handling patterns

3. **Services** (`core/services/`):
   - Reusable business logic
   - Export services
   - Analytics services

4. **Utils** (`core/utils/`):
   - Helper functions
   - Geolocation
   - Idempotency helpers

**When to Use Core:**
- Code used by 2+ apps
- Shared utilities
- Common business logic
- Reusable services

**When NOT to Use Core:**
- App-specific logic (put in app's `services.py`)
- Model-specific methods (put in model class)

---

## 3. Adding New Features

### 3.1 Feature Development Checklist

Before starting a new feature:

- [ ] Understand the requirement
- [ ] Check existing code for similar functionality
- [ ] Design the feature (models, API, tests)
- [ ] Create feature branch
- [ ] Implement feature
- [ ] Write tests
- [ ] Update documentation
- [ ] Run all tests
- [ ] Code review

### 3.2 Adding a New Django App

**Example: Adding a "Comments" Feature**

**Step 1: Create the App**

```bash
cd backend
python manage.py startapp comments apps/comments
```

**Step 2: Add to INSTALLED_APPS**

```python
# backend/config/settings/base.py
INSTALLED_APPS = [
    # ... existing apps
    "apps.comments",  # Add here
]
```

**Step 3: Create Models**

```python
# apps/comments/models.py
from django.contrib.auth.models import User
from django.db import models
from apps.polls.models import Poll


class Comment(models.Model):
    """Comment on a poll."""
    
    poll = models.ForeignKey(
        Poll,
        on_delete=models.CASCADE,
        related_name="comments"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="comments"
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["poll", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]
    
    def __str__(self):
        return f"Comment by {self.user.username} on {self.poll.title}"
```

**Step 4: Create Migration**

```bash
python manage.py makemigrations comments
python manage.py migrate
```

**Step 5: Create Serializer**

```python
# apps/comments/serializers.py
from rest_framework import serializers
from .models import Comment


class CommentSerializer(serializers.ModelSerializer):
    """Serializer for Comment model."""
    
    user = serializers.StringRelatedField(read_only=True)
    poll = serializers.StringRelatedField(read_only=True)
    
    class Meta:
        model = Comment
        fields = ["id", "poll", "user", "text", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
    
    def validate_text(self, value):
        """Validate comment text."""
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Comment must be at least 3 characters.")
        if len(value) > 1000:
            raise serializers.ValidationError("Comment cannot exceed 1000 characters.")
        return value
```

**Step 6: Create ViewSet**

```python
# apps/comments/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from core.mixins import RateLimitHeadersMixin
from .models import Comment
from .serializers import CommentSerializer


@extend_schema(tags=["Comments"])
class CommentViewSet(RateLimitHeadersMixin, viewsets.ModelViewSet):
    """ViewSet for Comment model."""
    
    queryset = Comment.objects.filter(is_deleted=False)
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter comments by poll if poll_id provided."""
        queryset = super().get_queryset()
        poll_id = self.request.query_params.get("poll_id")
        if poll_id:
            queryset = queryset.filter(poll_id=poll_id)
        return queryset
    
    def perform_create(self, serializer):
        """Set user to current user when creating comment."""
        serializer.save(user=self.request.user)
    
    @extend_schema(
        summary="Soft delete comment",
        description="Marks comment as deleted instead of removing it.",
    )
    @action(detail=True, methods=["post"])
    def soft_delete(self, request, pk=None):
        """Soft delete a comment."""
        comment = self.get_object()
        if comment.user != request.user:
            return Response(
                {"error": "You can only delete your own comments."},
                status=status.HTTP_403_FORBIDDEN
            )
        comment.is_deleted = True
        comment.save()
        return Response({"message": "Comment deleted."}, status=status.HTTP_200_OK)
```

**Step 7: Create URLs**

```python
# apps/comments/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import CommentViewSet

router = DefaultRouter()
router.register(r"comments", CommentViewSet, basename="comment")

urlpatterns = [
    path("", include(router.urls)),
]
```

**Step 8: Include in Root URLs**

```python
# backend/config/urls.py
urlpatterns = [
    # ... existing patterns
    path("api/v1/", include("apps.comments.urls")),  # Add this
]
```

**Step 9: Register in Admin (Optional)**

```python
# apps/comments/admin.py
from django.contrib import admin
from .models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["poll", "user", "text", "created_at", "is_deleted"]
    list_filter = ["is_deleted", "created_at"]
    search_fields = ["text", "user__username", "poll__title"]
    readonly_fields = ["created_at", "updated_at"]
```

**Step 10: Write Tests**

```python
# apps/comments/tests/test_views.py
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from apps.polls.models import Poll
from .models import Comment


@pytest.fixture
def api_client():
    """API client for testing."""
    return APIClient()


@pytest.fixture
def user(db):
    """Create test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123"
    )


@pytest.fixture
def poll(db, user):
    """Create test poll."""
    from apps.polls.models import Poll
    return Poll.objects.create(
        title="Test Poll",
        description="Test Description",
        created_by=user,
        is_active=True
    )


@pytest.mark.django_db
class TestCommentViewSet:
    """Tests for CommentViewSet."""
    
    def test_create_comment(self, api_client, user, poll):
        """Test creating a comment."""
        api_client.force_authenticate(user=user)
        response = api_client.post(
            "/api/v1/comments/",
            {"poll": poll.id, "text": "Great poll!"}
        )
        assert response.status_code == 201
        assert Comment.objects.count() == 1
        assert Comment.objects.first().user == user
        assert Comment.objects.first().poll == poll
    
    def test_list_comments(self, api_client, user, poll):
        """Test listing comments."""
        Comment.objects.create(poll=poll, user=user, text="Comment 1")
        Comment.objects.create(poll=poll, user=user, text="Comment 2")
        
        api_client.force_authenticate(user=user)
        response = api_client.get("/api/v1/comments/")
        
        assert response.status_code == 200
        assert len(response.data["results"]) == 2
    
    def test_filter_by_poll(self, api_client, user, poll):
        """Test filtering comments by poll."""
        other_poll = Poll.objects.create(
            title="Other Poll",
            created_by=user,
            is_active=True
        )
        Comment.objects.create(poll=poll, user=user, text="Comment on poll 1")
        Comment.objects.create(poll=other_poll, user=user, text="Comment on poll 2")
        
        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/v1/comments/?poll_id={poll.id}")
        
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["text"] == "Comment on poll 1"
    
    def test_soft_delete_comment(self, api_client, user, poll):
        """Test soft deleting a comment."""
        comment = Comment.objects.create(poll=poll, user=user, text="To be deleted")
        
        api_client.force_authenticate(user=user)
        response = api_client.post(f"/api/v1/comments/{comment.id}/soft_delete/")
        
        assert response.status_code == 200
        comment.refresh_from_db()
        assert comment.is_deleted is True
        # Comment should not appear in list
        list_response = api_client.get("/api/v1/comments/")
        assert len(list_response.data["results"]) == 0
```

**Step 11: Run Tests**

```bash
# Run all comment tests
pytest apps/comments/tests/ -v

# Run specific test
pytest apps/comments/tests/test_views.py::TestCommentViewSet::test_create_comment -v
```

**Step 12: Test the API**

```bash
# Start server
docker-compose up -d

# Create comment
curl -X POST http://localhost:8001/api/v1/comments/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"poll": 1, "text": "Great poll!"}'

# List comments
curl http://localhost:8001/api/v1/comments/
```

### 3.3 Adding a Custom Action to Existing ViewSet

**Example: Add "archive" action to PollViewSet**

```python
# apps/polls/views.py

@extend_schema(
    summary="Archive poll",
    description="Archive a poll (soft delete). Archived polls are not visible publicly.",
)
@action(detail=True, methods=["post"])
def archive(self, request, pk=None):
    """Archive a poll."""
    poll = self.get_object()
    
    # Check permissions
    if poll.created_by != request.user and not request.user.is_staff:
        return Response(
            {"error": "You can only archive your own polls."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Archive poll
    poll.is_active = False
    poll.save(update_fields=["is_active"])
    
    # Log action
    logger.info(f"Poll {poll.id} archived by user {request.user.id}")
    
    return Response(
        {"message": "Poll archived successfully."},
        status=status.HTTP_200_OK
    )
```

**Test the Action:**

```python
# apps/polls/tests/test_views.py

def test_archive_poll(self, api_client, user, poll):
    """Test archiving a poll."""
    api_client.force_authenticate(user=user)
    response = api_client.post(f"/api/v1/polls/{poll.id}/archive/")
    
    assert response.status_code == 200
    poll.refresh_from_db()
    assert poll.is_active is False
```

### 3.4 Adding a Custom Service Function

**Example: Add comment moderation service**

```python
# apps/comments/services.py
import logging
from typing import Optional
from .models import Comment

logger = logging.getLogger(__name__)


def moderate_comment(comment_id: int, action: str, moderator_id: Optional[int] = None) -> Comment:
    """
    Moderate a comment (approve, reject, or flag).
    
    Args:
        comment_id: ID of comment to moderate
        action: One of 'approve', 'reject', 'flag'
        moderator_id: ID of user performing moderation
    
    Returns:
        Updated Comment instance
    
    Raises:
        Comment.DoesNotExist: If comment not found
        ValueError: If invalid action
    """
    comment = Comment.objects.get(id=comment_id)
    
    if action == "approve":
        comment.is_approved = True
        comment.moderated_by_id = moderator_id
        logger.info(f"Comment {comment_id} approved by {moderator_id}")
    elif action == "reject":
        comment.is_deleted = True
        comment.moderated_by_id = moderator_id
        logger.info(f"Comment {comment_id} rejected by {moderator_id}")
    elif action == "flag":
        comment.is_flagged = True
        comment.flag_count = (comment.flag_count or 0) + 1
        logger.info(f"Comment {comment_id} flagged (count: {comment.flag_count})")
    else:
        raise ValueError(f"Invalid action: {action}. Must be 'approve', 'reject', or 'flag'")
    
    comment.save()
    return comment
```

**Use in ViewSet:**

```python
# apps/comments/views.py
from .services import moderate_comment

@action(detail=True, methods=["post"])
def moderate(self, request, pk=None):
    """Moderate a comment."""
    comment = self.get_object()
    action = request.data.get("action")
    
    try:
        moderate_comment(comment.id, action, request.user.id)
        return Response({"message": f"Comment {action}ed successfully."})
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
```

**Test the Service:**

```python
# apps/comments/tests/test_services.py
import pytest
from .models import Comment
from .services import moderate_comment

@pytest.mark.django_db
def test_moderate_comment_approve(user, poll):
    """Test approving a comment."""
    comment = Comment.objects.create(poll=poll, user=user, text="Test comment")
    
    moderate_comment(comment.id, "approve", user.id)
    
    comment.refresh_from_db()
    assert comment.is_approved is True
    assert comment.moderated_by == user

@pytest.mark.django_db
def test_moderate_comment_invalid_action(user, poll):
    """Test invalid moderation action."""
    comment = Comment.objects.create(poll=poll, user=user, text="Test comment")
    
    with pytest.raises(ValueError, match="Invalid action"):
        moderate_comment(comment.id, "invalid_action")
```

### 3.5 Adding Custom Middleware

**Example: Add request timing middleware**

```python
# core/middleware/timing.py
import time
import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class RequestTimingMiddleware(MiddlewareMixin):
    """Middleware to log request processing time."""
    
    def process_request(self, request):
        """Store request start time."""
        request._start_time = time.time()
    
    def process_response(self, request, response):
        """Log request processing time."""
        if hasattr(request, "_start_time"):
            duration = time.time() - request._start_time
            logger.info(
                f"{request.method} {request.path} - {response.status_code} - {duration:.3f}s"
            )
            # Add timing header
            response["X-Process-Time"] = f"{duration:.3f}"
        return response
```

**Add to Settings:**

```python
# backend/config/settings/base.py
MIDDLEWARE = [
    # ... existing middleware
    "core.middleware.timing.RequestTimingMiddleware",  # Add here
]
```

### 3.6 Adding Custom Permissions

**Example: Add comment moderation permission**

```python
# apps/comments/permissions.py
from rest_framework import permissions


class CanModerateComments(permissions.BasePermission):
    """Permission to moderate comments."""
    
    def has_permission(self, request, view):
        """Check if user can moderate comments."""
        if view.action in ["moderate", "bulk_moderate"]:
            return request.user.is_authenticated and (
                request.user.is_staff or request.user.has_perm("comments.moderate_comment")
            )
        return True
    
    def has_object_permission(self, request, view, obj):
        """Check object-level permission."""
        if view.action in ["moderate", "bulk_moderate"]:
            return request.user.is_staff or request.user.has_perm("comments.moderate_comment")
        return True
```

**Use in ViewSet:**

```python
# apps/comments/views.py
from .permissions import CanModerateComments

class CommentViewSet(RateLimitHeadersMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, CanModerateComments]
    # ...
```

---

## 4. Testing Guide

### 4.1 Testing Philosophy

**Principles:**
- **Test behavior, not implementation**
- **Write tests first (TDD) when possible**
- **Test edge cases and error conditions**
- **Keep tests fast and isolated**
- **Use fixtures for common setup**

### 4.2 Test Structure

**Test File Organization:**

```
apps/myapp/tests/
├── __init__.py
├── test_models.py          # Model tests
├── test_views.py           # ViewSet/View tests
├── test_services.py        # Service function tests
├── test_serializers.py     # Serializer tests
├── test_permissions.py     # Permission tests
└── conftest.py            # App-specific fixtures
```

### 4.3 Writing Model Tests

**Example:**

```python
# apps/comments/tests/test_models.py
import pytest
from django.core.exceptions import ValidationError
from .models import Comment

@pytest.mark.django_db
class TestCommentModel:
    """Tests for Comment model."""
    
    def test_create_comment(self, user, poll):
        """Test creating a comment."""
        comment = Comment.objects.create(
            poll=poll,
            user=user,
            text="Test comment"
        )
        assert comment.poll == poll
        assert comment.user == user
        assert comment.text == "Test comment"
        assert comment.is_deleted is False
    
    def test_comment_str(self, user, poll):
        """Test comment string representation."""
        comment = Comment.objects.create(
            poll=poll,
            user=user,
            text="Test comment"
        )
        assert str(comment) == f"Comment by {user.username} on {poll.title}"
    
    def test_comment_ordering(self, user, poll):
        """Test comments are ordered by created_at descending."""
        comment1 = Comment.objects.create(poll=poll, user=user, text="First")
        comment2 = Comment.objects.create(poll=poll, user=user, text="Second")
        
        comments = Comment.objects.all()
        assert comments[0] == comment2  # Newest first
        assert comments[1] == comment1
```

### 4.4 Writing ViewSet Tests

**Example:**

```python
# apps/comments/tests/test_views.py
import pytest
from rest_framework.test import APIClient
from rest_framework import status
from .models import Comment

@pytest.mark.django_db
class TestCommentViewSet:
    """Tests for CommentViewSet."""
    
    @pytest.fixture
    def api_client(self):
        return APIClient()
    
    def test_list_comments_requires_auth(self, api_client):
        """Test listing comments requires authentication."""
        response = api_client.get("/api/v1/comments/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_create_comment_success(self, api_client, user, poll):
        """Test successfully creating a comment."""
        api_client.force_authenticate(user=user)
        response = api_client.post(
            "/api/v1/comments/",
            {"poll": poll.id, "text": "Great poll!"},
            format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert Comment.objects.count() == 1
        assert response.data["text"] == "Great poll!"
        assert response.data["user"] == user.username
    
    def test_create_comment_validation_error(self, api_client, user, poll):
        """Test comment validation errors."""
        api_client.force_authenticate(user=user)
        
        # Too short
        response = api_client.post(
            "/api/v1/comments/",
            {"poll": poll.id, "text": "Hi"},
            format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        # Too long
        long_text = "x" * 1001
        response = api_client.post(
            "/api/v1/comments/",
            {"poll": poll.id, "text": long_text},
            format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_filter_comments_by_poll(self, api_client, user, poll):
        """Test filtering comments by poll."""
        other_poll = Poll.objects.create(
            title="Other Poll",
            created_by=user,
            is_active=True
        )
        Comment.objects.create(poll=poll, user=user, text="Comment 1")
        Comment.objects.create(poll=other_poll, user=user, text="Comment 2")
        
        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/v1/comments/?poll_id={poll.id}")
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["text"] == "Comment 1"
```

### 4.5 Writing Service Tests

**Example:**

```python
# apps/comments/tests/test_services.py
import pytest
from .models import Comment
from .services import moderate_comment

@pytest.mark.django_db
class TestCommentServices:
    """Tests for comment services."""
    
    def test_moderate_approve(self, user, poll):
        """Test approving a comment."""
        comment = Comment.objects.create(poll=poll, user=user, text="Test")
        
        result = moderate_comment(comment.id, "approve", user.id)
        
        assert result.is_approved is True
        assert result.moderated_by == user
    
    def test_moderate_reject(self, user, poll):
        """Test rejecting a comment."""
        comment = Comment.objects.create(poll=poll, user=user, text="Test")
        
        result = moderate_comment(comment.id, "reject", user.id)
        
        assert result.is_deleted is True
        assert result.moderated_by == user
    
    def test_moderate_invalid_action(self, user, poll):
        """Test invalid moderation action raises error."""
        comment = Comment.objects.create(poll=poll, user=user, text="Test")
        
        with pytest.raises(ValueError, match="Invalid action"):
            moderate_comment(comment.id, "invalid", user.id)
```

### 4.6 Test Fixtures

**Project-Level Fixtures** (`backend/tests/conftest.py`):

```python
import pytest
from django.contrib.auth.models import User
from apps.polls.models import Poll, PollOption

@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123"
    )

@pytest.fixture
def poll(db, user):
    """Create a test poll."""
    return Poll.objects.create(
        title="Test Poll",
        description="Test Description",
        created_by=user,
        is_active=True
    )

@pytest.fixture
def poll_options(db, poll):
    """Create test poll options."""
    option1 = PollOption.objects.create(poll=poll, text="Option 1", order=0)
    option2 = PollOption.objects.create(poll=poll, text="Option 2", order=1)
    return [option1, option2]
```

**App-Level Fixtures** (`apps/comments/tests/conftest.py`):

```python
import pytest
from .models import Comment

@pytest.fixture
def comment(db, user, poll):
    """Create a test comment."""
    return Comment.objects.create(
        poll=poll,
        user=user,
        text="Test comment"
    )
```

### 4.7 Running Tests

**Run All Tests:**
```bash
pytest
```

**Run Specific App:**
```bash
pytest apps/comments/tests/
```

**Run Specific Test File:**
```bash
pytest apps/comments/tests/test_views.py
```

**Run Specific Test:**
```bash
pytest apps/comments/tests/test_views.py::TestCommentViewSet::test_create_comment
```

**Run with Coverage:**
```bash
pytest --cov=apps.comments --cov-report=html
```

**Run with Verbose Output:**
```bash
pytest -v
```

**Run with Markers:**
```bash
pytest -m unit
pytest -m integration
pytest -m "not slow"
```

### 4.8 Test Best Practices

1. **Use descriptive test names:**
   ```python
   # Good
   def test_create_comment_sets_user_to_current_user(self):
       pass
   
   # Bad
   def test_create(self):
       pass
   ```

2. **One assertion per test concept:**
   ```python
   # Good
   def test_comment_has_correct_poll(self, comment, poll):
       assert comment.poll == poll
   
   def test_comment_has_correct_user(self, comment, user):
       assert comment.user == user
   
   # Acceptable (related assertions)
   def test_comment_creation(self, comment, poll, user):
       assert comment.poll == poll
       assert comment.user == user
       assert comment.text == "Test"
   ```

3. **Use fixtures for setup:**
   ```python
   # Good
   def test_comment(self, comment):
       assert comment.text == "Test"
   
   # Bad
   def test_comment(self):
       user = User.objects.create_user(...)
       poll = Poll.objects.create(...)
       comment = Comment.objects.create(...)
       assert comment.text == "Test"
   ```

4. **Test edge cases:**
   ```python
   def test_create_comment_empty_text(self):
       """Test creating comment with empty text fails."""
       pass
   
   def test_create_comment_very_long_text(self):
       """Test creating comment with very long text fails."""
       pass
   
   def test_create_comment_nonexistent_poll(self):
       """Test creating comment for nonexistent poll fails."""
       pass
   ```

---

## 5. Code Style and Patterns

### 5.1 Code Formatting

**Black (Automatic Formatting):**
```bash
# Format all code
black backend/

# Format specific file
black backend/apps/comments/views.py

# Check without formatting
black --check backend/
```

**isort (Import Sorting):**
```bash
# Sort imports
isort backend/

# Check without sorting
isort --check-only backend/
```

**Flake8 (Linting):**
```bash
# Check code style
flake8 backend/
```

### 5.2 Import Organization

**Standard Import Order:**
```python
# 1. Standard library
import os
import logging
from datetime import datetime

# 2. Third-party
from django.db import models
from rest_framework import viewsets
from drf_spectacular.utils import extend_schema

# 3. Local imports
from apps.polls.models import Poll
from core.mixins import RateLimitHeadersMixin
from .models import Comment
from .serializers import CommentSerializer
```

### 5.3 Naming Conventions

**Models:**
- PascalCase: `Comment`, `PollOption`, `VoteAttempt`

**Views/ViewSets:**
- PascalCase: `CommentViewSet`, `PollViewSet`

**Functions:**
- snake_case: `create_comment`, `moderate_comment`

**Variables:**
- snake_case: `comment_id`, `user_count`

**Constants:**
- UPPER_SNAKE_CASE: `MAX_COMMENT_LENGTH`, `DEFAULT_PAGE_SIZE`

### 5.4 Docstrings

**Function Docstrings:**
```python
def moderate_comment(comment_id: int, action: str, moderator_id: Optional[int] = None) -> Comment:
    """
    Moderate a comment (approve, reject, or flag).
    
    Args:
        comment_id: ID of comment to moderate
        action: One of 'approve', 'reject', 'flag'
        moderator_id: ID of user performing moderation
    
    Returns:
        Updated Comment instance
    
    Raises:
        Comment.DoesNotExist: If comment not found
        ValueError: If invalid action
    
    Example:
        >>> comment = moderate_comment(1, "approve", moderator_id=5)
        >>> comment.is_approved
        True
    """
    pass
```

**Class Docstrings:**
```python
class CommentViewSet(RateLimitHeadersMixin, viewsets.ModelViewSet):
    """
    ViewSet for Comment model.
    
    Provides CRUD operations for comments on polls.
    Supports filtering by poll and soft deletion.
    
    Endpoints:
    - GET /api/v1/comments/ - List comments
    - POST /api/v1/comments/ - Create comment
    - GET /api/v1/comments/{id}/ - Get comment detail
    - PATCH /api/v1/comments/{id}/ - Update comment
    - DELETE /api/v1/comments/{id}/ - Delete comment
    - POST /api/v1/comments/{id}/soft_delete/ - Soft delete comment
    """
    pass
```

### 5.5 Type Hints

**Use Type Hints:**
```python
from typing import Optional, List, Dict

def get_comments(
    poll_id: int,
    user_id: Optional[int] = None,
    limit: int = 20
) -> List[Comment]:
    """Get comments for a poll."""
    pass

def create_comment_data(
    text: str,
    poll_id: int
) -> Dict[str, any]:
    """Create comment data dictionary."""
    pass
```

### 5.6 Error Handling

**Use Custom Exceptions:**
```python
# core/exceptions/comments.py
from core.exceptions import BaseAPIException

class CommentNotFoundError(BaseAPIException):
    """Raised when comment is not found."""
    default_status_code = 404
    default_message = "Comment not found"

class CommentModerationError(BaseAPIException):
    """Raised when comment moderation fails."""
    default_status_code = 400
    default_message = "Comment moderation failed"
```

**Handle Errors in Views:**
```python
from core.exceptions.comments import CommentNotFoundError

@action(detail=True, methods=["post"])
def moderate(self, request, pk=None):
    """Moderate a comment."""
    try:
        comment = Comment.objects.get(id=pk)
    except Comment.DoesNotExist:
        raise CommentNotFoundError()
    
    try:
        moderate_comment(comment.id, request.data["action"], request.user.id)
    except ValueError as e:
        raise CommentModerationError(str(e))
```

---

## 6. Git Workflow

### 6.1 Branch Naming

**Conventions:**
- `feature/description` - New features
- `fix/description` - Bug fixes
- `refactor/description` - Code refactoring
- `docs/description` - Documentation updates
- `test/description` - Test additions/updates

**Examples:**
- `feature/add-comments`
- `fix/comment-validation-bug`
- `refactor/comment-service`
- `docs/update-api-docs`

### 6.2 Commit Messages

**Format:**
```
Type: Short description (50 chars max)

Longer description if needed (wrap at 72 chars).

- Bullet point 1
- Bullet point 2

Closes #123
```

**Types:**
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `test:` - Tests
- `refactor:` - Code refactoring
- `style:` - Code style (formatting)
- `chore:` - Maintenance tasks
- `perf:` - Performance improvements

**Examples:**
```
feat: Add comment moderation feature

- Add moderate_comment service function
- Add moderation action to CommentViewSet
- Add moderation permissions
- Add comprehensive tests

Closes #45
```

```
fix: Resolve comment validation bug

- Fix text length validation
- Add proper error messages
- Update tests

Fixes #67
```

### 6.3 Pull Request Process

1. **Create Feature Branch:**
   ```bash
   git checkout -b feature/add-comments
   ```

2. **Make Changes:**
   ```bash
   # Make your changes
   git add .
   git commit -m "feat: Add comment model and serializer"
   ```

3. **Run Tests:**
   ```bash
   pytest
   black backend/
   isort backend/
   flake8 backend/
   ```

4. **Push Branch:**
   ```bash
   git push origin feature/add-comments
   ```

5. **Create Pull Request:**
   - Use descriptive title
   - Add detailed description
   - Link related issues
   - Request reviewers

6. **Address Review Comments:**
   ```bash
   # Make changes
   git add .
   git commit -m "fix: Address review comments"
   git push
   ```

### 6.4 Pre-Commit Checklist

Before committing:

- [ ] Code formatted with Black
- [ ] Imports sorted with isort
- [ ] No Flake8 errors
- [ ] All tests passing
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] Migration created (if model changes)
- [ ] Migration tested
- [ ] API documentation updated (if API changes)
- [ ] No hardcoded secrets or credentials
- [ ] No debug print statements
- [ ] No commented-out code

---

## 7. Common Extension Patterns

### 7.1 Adding a Custom Action to ViewSet

**Pattern:**
```python
@extend_schema(
    summary="Action description",
    description="Detailed description of what the action does.",
)
@action(detail=True, methods=["post"])
def custom_action(self, request, pk=None):
    """Custom action implementation."""
    obj = self.get_object()
    # Perform action
    return Response({"message": "Action completed"}, status=status.HTTP_200_OK)
```

### 7.2 Adding a Custom Service Function

**Pattern:**
```python
# apps/myapp/services.py
import logging
from typing import Optional
from .models import MyModel

logger = logging.getLogger(__name__)


def my_service_function(
    obj_id: int,
    param: str,
    optional_param: Optional[int] = None
) -> MyModel:
    """
    Service function description.
    
    Args:
        obj_id: Description
        param: Description
        optional_param: Description
    
    Returns:
        Description
    
    Raises:
        MyModel.DoesNotExist: If object not found
        ValueError: If invalid parameter
    """
    obj = MyModel.objects.get(id=obj_id)
    # Business logic
    obj.save()
    logger.info(f"Action performed on {obj_id}")
    return obj
```

### 7.3 Adding Custom Permissions

**Pattern:**
```python
# apps/myapp/permissions.py
from rest_framework import permissions


class MyCustomPermission(permissions.BasePermission):
    """Custom permission description."""
    
    def has_permission(self, request, view):
        """Check view-level permission."""
        # Check permission logic
        return request.user.is_authenticated and request.user.has_perm("myapp.custom_permission")
    
    def has_object_permission(self, request, view, obj):
        """Check object-level permission."""
        # Check object-level permission logic
        return obj.owner == request.user or request.user.is_staff
```

### 7.4 Adding Custom Middleware

**Pattern:**
```python
# core/middleware/my_middleware.py
from django.utils.deprecation import MiddlewareMixin
import logging

logger = logging.getLogger(__name__)


class MyCustomMiddleware(MiddlewareMixin):
    """Custom middleware description."""
    
    def process_request(self, request):
        """Process request."""
        # Request processing logic
        pass
    
    def process_response(self, request, response):
        """Process response."""
        # Response processing logic
        return response
```

### 7.5 Adding Background Tasks

**Pattern:**
```python
# apps/myapp/tasks.py
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def my_background_task(obj_id: int):
    """
    Background task description.
    
    Args:
        obj_id: ID of object to process
    """
    from .models import MyModel
    
    try:
        obj = MyModel.objects.get(id=obj_id)
        # Process object
        logger.info(f"Processed {obj_id}")
    except MyModel.DoesNotExist:
        logger.error(f"Object {obj_id} not found")
```

**Call from View:**
```python
from .tasks import my_background_task

@action(detail=True, methods=["post"])
def trigger_task(self, request, pk=None):
    """Trigger background task."""
    obj = self.get_object()
    my_background_task.delay(obj.id)
    return Response({"message": "Task queued"}, status=status.HTTP_202_ACCEPTED)
```

---

## 8. Best Practices

### 8.1 Code Organization

1. **Keep functions small and focused**
2. **Use services for complex business logic**
3. **Keep views thin (delegate to services)**
4. **Use type hints for clarity**
5. **Document complex logic**

### 8.2 Security

1. **Always validate user input**
2. **Use permissions for authorization**
3. **Never trust client data**
4. **Use parameterized queries (Django ORM does this)**
5. **Sanitize user-generated content**

### 8.3 Performance

1. **Use `select_related` and `prefetch_related` for queries**
2. **Cache expensive operations**
3. **Use database indexes appropriately**
4. **Consider pagination for large datasets**
5. **Use background tasks for long-running operations**

### 8.4 Testing

1. **Write tests for all new features**
2. **Test edge cases and error conditions**
3. **Keep tests fast and isolated**
4. **Use fixtures for common setup**
5. **Test behavior, not implementation**

### 8.5 Documentation

1. **Update API documentation when adding endpoints**
2. **Document complex algorithms**
3. **Add docstrings to all public functions**
4. **Update README if setup changes**
5. **Keep architecture docs up to date**

---

## Quick Reference

### Common Commands

```bash
# Setup
docker-compose up -d
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser

# Development
docker-compose exec web python manage.py runserver
docker-compose exec web python manage.py shell

# Testing
docker-compose exec web pytest
docker-compose exec web pytest apps/myapp/tests/ -v

# Code Quality
docker-compose exec web black backend/
docker-compose exec web isort backend/
docker-compose exec web flake8 backend/

# Database
docker-compose exec web python manage.py makemigrations
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py showmigrations
```

### File Locations

- **Models:** `apps/myapp/models.py`
- **Views:** `apps/myapp/views.py`
- **Serializers:** `apps/myapp/serializers.py`
- **Services:** `apps/myapp/services.py`
- **URLs:** `apps/myapp/urls.py`
- **Tests:** `apps/myapp/tests/`
- **Settings:** `backend/config/settings/`
- **Core Utils:** `backend/core/`

---

**Last Updated:** 2025-11-22  
**For Questions:** See `docs/development.md` or `docs/api.md`

