# Development Guide

**Last Updated:** 2025-11-22  
**Project:** Provote - Professional Voting Platform

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Development Setup](#2-development-setup)
3. [Code Style](#3-code-style)
4. [Testing](#4-testing)
5. [Project Structure](#5-project-structure)
6. [Common Tasks](#6-common-tasks)
7. [Debugging](#7-debugging)
8. [Git Workflow](#8-git-workflow)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Getting Started

### Prerequisites

- **Python:** 3.11+
- **PostgreSQL:** 15+ (or use Docker)
- **Redis:** 7+ (or use Docker)
- **Docker & Docker Compose:** 2.0+ (recommended)
- **Git:** Latest version

### Quick Start

```bash
# Clone repository
git clone https://github.com/yourusername/provote.git
cd provote

# Set up environment
cp .env.example .env
# Edit .env with your settings

# Start with Docker (recommended)
cd docker
docker-compose up --build

# Or set up locally (see below)
```

---

## 2. Development Setup

### Option A: Docker (Recommended)

**Advantages:**
- Consistent environment across team
- No local PostgreSQL/Redis setup needed
- Easy to reset database
- Matches production environment

**Steps:**

1. **Start services:**
   ```bash
   cd docker
   docker-compose up -d
   ```

2. **Run migrations:**
   ```bash
   docker-compose exec web python manage.py migrate
   ```

3. **Create superuser:**
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```

4. **Access services:**
   - Web: `http://localhost:8001`
   - Admin: `http://localhost:8001/admin/`
   - API: `http://localhost:8001/api/v1/`
   - API Docs: `http://localhost:8001/api/docs/`

5. **View logs:**
   ```bash
   docker-compose logs -f web
   docker-compose logs -f celery
   ```

### Option B: Local Development

**Steps:**

1. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements/development.txt
   ```

3. **Set up PostgreSQL and Redis:**
   ```bash
   # PostgreSQL
   createdb provote_dev
   
   # Redis (if not running as service)
   redis-server
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env:
   # DB_HOST=localhost
   # REDIS_HOST=localhost
   # DEBUG=True
   ```

5. **Run migrations:**
   ```bash
   cd backend
   python manage.py migrate
   ```

6. **Create superuser:**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run development server:**
   ```bash
   python manage.py runserver
   ```

8. **Run Celery worker (separate terminal):**
   ```bash
   celery -A config worker --loglevel=info
   ```

9. **Run Celery beat (separate terminal):**
   ```bash
   celery -A config beat --loglevel=info
   ```

### Environment Variables

**Required for development:**

```bash
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=provote_dev
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost  # or 'db' for Docker
DB_PORT=5432

# Redis
REDIS_HOST=localhost  # or 'redis' for Docker
REDIS_PORT=6379

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Optional
DISABLE_RATE_LIMITING=False  # Set to True for load testing
```

**Generate SECRET_KEY:**
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## 3. Code Style

### Black (Code Formatter)

Format code with Black:
```bash
# Format all Python files
black backend/

# Format specific file
black backend/apps/polls/views.py

# Check without formatting
black --check backend/
```

**Configuration:** `pyproject.toml`

### isort (Import Sorter)

Sort imports:
```bash
# Sort all imports
isort backend/

# Sort specific file
isort backend/apps/polls/views.py

# Check without sorting
isort --check-only backend/
```

### Flake8 (Linter)

Check code style:
```bash
# Check all files
flake8 backend/

# Check specific file
flake8 backend/apps/polls/views.py
```

**Configuration:** `.flake8` or `setup.cfg`

### Pre-commit Hooks

Install pre-commit hooks to automatically format code before commits:

```bash
# Install hooks
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

**Hooks configured:**
- Black (code formatting)
- isort (import sorting)
- Flake8 (linting)
- Trailing whitespace removal
- End-of-file fixes

---

## 4. Testing

### Running Tests

**All tests:**
```bash
# Docker
docker-compose exec web pytest

# Local
cd backend
pytest
```

**Specific test file:**
```bash
pytest backend/tests/test_integration.py
pytest backend/apps/polls/tests/test_views.py
```

**Specific test:**
```bash
pytest backend/tests/test_integration.py::TestDatabaseConnection -v
```

**With coverage:**
```bash
pytest --cov=backend --cov-report=html
# Open htmlcov/index.html in browser
```

**Test markers:**
```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Stress tests
pytest -m stress

# Skip slow tests
pytest -m "not slow"
```

### Test Categories

- **Unit Tests:** Fast, isolated tests (`@pytest.mark.unit`)
- **Integration Tests:** Test multiple components (`@pytest.mark.integration`)
- **Stress Tests:** Load and concurrency tests (`@pytest.mark.stress`)

### Test Database

**PostgreSQL (recommended):**
```bash
# Use PostgreSQL test settings
export DJANGO_SETTINGS_MODULE=config.settings.test_postgresql
pytest
```

**SQLite (default):**
- Automatically used if PostgreSQL not configured
- Some tests skip on SQLite (concurrency, transactions)

### Writing Tests

**Example test structure:**
```python
import pytest
from django.contrib.auth.models import User
from apps.polls.models import Poll

@pytest.mark.django_db
def test_create_poll(user):
    """Test creating a poll."""
    poll = Poll.objects.create(
        title="Test Poll",
        created_by=user,
        is_active=True
    )
    assert poll.title == "Test Poll"
    assert poll.created_by == user
```

**Fixtures:**
- `user` - Test user
- `poll` - Test poll
- `choices` - Test poll options
- `db` - Database access

**Code Reference:** `backend/tests/conftest.py`

---

## 5. Project Structure

```
provote/
├── backend/                    # Django project root
│   ├── apps/                  # Django applications
│   │   ├── polls/             # Poll management
│   │   │   ├── models.py      # Poll, PollOption, Category, Tag
│   │   │   ├── views.py       # PollViewSet
│   │   │   ├── serializers.py # Poll serializers
│   │   │   ├── services.py    # Business logic
│   │   │   ├── permissions.py # Custom permissions
│   │   │   ├── templates.py   # Poll templates
│   │   │   ├── urls.py        # URL routing
│   │   │   └── tests/         # Poll tests
│   │   ├── votes/             # Voting functionality
│   │   │   ├── models.py      # Vote, VoteAttempt
│   │   │   ├── views.py       # VoteViewSet
│   │   │   ├── services.py    # cast_vote service
│   │   │   └── tests/         # Vote tests
│   │   ├── users/             # User management
│   │   ├── analytics/         # Analytics and reporting
│   │   └── notifications/    # Notifications
│   ├── config/                # Django configuration
│   │   ├── settings/          # Environment settings
│   │   │   ├── base.py        # Base settings
│   │   │   ├── development.py # Development settings
│   │   │   ├── production.py  # Production settings
│   │   │   └── test.py        # Test settings
│   │   ├── urls.py            # Root URL configuration
│   │   ├── wsgi.py            # WSGI application
│   │   └── asgi.py            # ASGI application
│   ├── core/                  # Core utilities
│   │   ├── middleware/        # Custom middleware
│   │   │   ├── rate_limit.py  # Rate limiting
│   │   │   ├── audit_log.py   # Audit logging
│   │   │   └── fingerprint.py # Fingerprint extraction
│   │   ├── exceptions/        # Custom exceptions
│   │   ├── services/          # Core services
│   │   │   ├── export_service.py # Export functionality
│   │   │   └── poll_analytics.py  # Analytics
│   │   ├── utils/             # Utility functions
│   │   │   ├── geolocation.py # IP geolocation
│   │   │   └── idempotency.py # Idempotency helpers
│   │   ├── throttles.py       # Rate limit throttles
│   │   └── mixins.py          # View mixins
│   └── tests/                 # Integration tests
│       ├── test_integration.py
│       ├── test_concurrent_load.py
│       └── test_idempotency_stress.py
├── docker/                     # Docker configuration
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── nginx.conf
├── requirements/              # Python dependencies
│   ├── base.txt               # Base dependencies
│   ├── development.txt        # Development dependencies
│   └── production.txt         # Production dependencies
└── docs/                      # Documentation
    ├── api.md                 # API documentation
    ├── development.md         # This file
    ├── deployment-guide.md    # Deployment guide
    └── architecture-comprehensive.md # Architecture docs
```

### Adding a New App

1. **Create app:**
   ```bash
   cd backend
   python manage.py startapp myapp apps/myapp
   ```

2. **Add to `INSTALLED_APPS`:**
   ```python
   # backend/config/settings/base.py
   INSTALLED_APPS = [
       # ...
       "apps.myapp",
   ]
   ```

3. **Create URL configuration:**
   ```python
   # apps/myapp/urls.py
   from django.urls import path
   from . import views
   
   urlpatterns = [
       path("myapp/", views.MyView.as_view()),
   ]
   ```

4. **Include in root URLs:**
   ```python
   # backend/config/urls.py
   path("api/v1/", include("apps.myapp.urls")),
   ```

5. **Add tests:**
   ```python
   # apps/myapp/tests/test_views.py
   import pytest
   from django.test import Client
   
   @pytest.mark.django_db
   def test_my_view():
       client = Client()
       response = client.get("/api/v1/myapp/")
       assert response.status_code == 200
   ```

### Adding a New Model

1. **Create model:**
   ```python
   # apps/myapp/models.py
   from django.db import models
   
   class MyModel(models.Model):
       name = models.CharField(max_length=100)
       created_at = models.DateTimeField(auto_now_add=True)
   ```

2. **Create migration:**
   ```bash
   python manage.py makemigrations myapp
   ```

3. **Apply migration:**
   ```bash
   python manage.py migrate
   ```

4. **Register in admin (optional):**
   ```python
   # apps/myapp/admin.py
   from django.contrib import admin
   from .models import MyModel
   
   admin.site.register(MyModel)
   ```

5. **Create serializer:**
   ```python
   # apps/myapp/serializers.py
   from rest_framework import serializers
   from .models import MyModel
   
   class MyModelSerializer(serializers.ModelSerializer):
       class Meta:
           model = MyModel
           fields = "__all__"
   ```

6. **Create view/viewset:**
   ```python
   # apps/myapp/views.py
   from rest_framework import viewsets
   from .models import MyModel
   from .serializers import MyModelSerializer
   
   class MyModelViewSet(viewsets.ModelViewSet):
       queryset = MyModel.objects.all()
       serializer_class = MyModelSerializer
   ```

7. **Add URL route:**
   ```python
   # apps/myapp/urls.py
   from rest_framework.routers import DefaultRouter
   from .views import MyModelViewSet
   
   router = DefaultRouter()
   router.register(r"mymodels", MyModelViewSet)
   
   urlpatterns = router.urls
   ```

8. **Write tests:**
   ```python
   # apps/myapp/tests/test_models.py
   import pytest
   from .models import MyModel
   
   @pytest.mark.django_db
   def test_create_mymodel():
       obj = MyModel.objects.create(name="Test")
       assert obj.name == "Test"
   ```

---

## 6. Common Tasks

### Database Operations

**Create migration:**
```bash
python manage.py makemigrations
python manage.py makemigrations polls  # Specific app
```

**Apply migrations:**
```bash
python manage.py migrate
python manage.py migrate polls  # Specific app
```

**Show migrations:**
```bash
python manage.py showmigrations
```

**Reset migrations (development only):**
```bash
# Delete migration files
rm apps/polls/migrations/0*.py

# Create new initial migration
python manage.py makemigrations polls

# Fake apply
python manage.py migrate --fake-initial
```

### User Management

**Create superuser:**
```bash
python manage.py createsuperuser
```

**Create user (Django shell):**
```python
from django.contrib.auth.models import User
user = User.objects.create_user('username', 'email@example.com', 'password')
```

### Static Files

**Collect static files:**
```bash
python manage.py collectstatic --noinput
```

**Find static files:**
```bash
python manage.py findstatic admin/css/base.css
```

### Celery Tasks

**Run Celery worker:**
```bash
celery -A config worker --loglevel=info
```

**Run Celery beat (scheduler):**
```bash
celery -A config beat --loglevel=info
```

**Run both (development):**
```bash
celery -A config worker --beat --loglevel=info
```

**Monitor Celery:**
```bash
celery -A config inspect active
celery -A config inspect scheduled
```

### Django Shell

**Standard shell:**
```bash
python manage.py shell
```

**IPython shell (if installed):**
```bash
python manage.py shell -i ipython
```

**Example usage:**
```python
from apps.polls.models import Poll
from django.contrib.auth.models import User

# Create poll
user = User.objects.first()
poll = Poll.objects.create(
    title="Test Poll",
    created_by=user,
    is_active=True
)

# Query polls
polls = Poll.objects.filter(is_active=True)
```

---

## 7. Debugging

### Django Debug Toolbar

Enabled in development. Access at `/admin/` or any page.

**Features:**
- SQL queries
- Templates
- Request/response
- Performance profiling

### Logging

**View logs:**
```bash
# Docker
docker-compose logs -f web

# Local
# Logs go to console (stdout)
```

**Configure logging:**
```python
# backend/config/settings/development.py
LOGGING = {
    "version": 1,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "apps.polls": {
            "level": "DEBUG",
        },
    },
}
```

**Use in code:**
```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

### IPython

**Use IPython shell:**
```bash
python manage.py shell -i ipython
```

**Features:**
- Syntax highlighting
- Auto-completion
- Better error messages

### Debugging Tools

**pdb (Python debugger):**
```python
import pdb; pdb.set_trace()  # Breakpoint
```

**ipdb (IPython debugger):**
```python
import ipdb; ipdb.set_trace()  # Better breakpoint
```

**Django Debug Toolbar:**
- Automatically enabled in development
- Shows SQL queries, templates, etc.

---

## 8. Git Workflow

### Branch Strategy

1. **Create feature branch:**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make changes and commit:**
   ```bash
   git add .
   git commit -m "Add feature: description"
   ```

3. **Run tests and format:**
   ```bash
   pytest
   black .
   isort .
   ```

4. **Push and create PR:**
   ```bash
   git push origin feature/my-feature
   # Create Pull Request on GitHub
   ```

### Commit Messages

**Format:**
```
Type: Short description

Longer description if needed.

- Bullet point 1
- Bullet point 2
```

**Types:**
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `test:` Tests
- `refactor:` Code refactoring
- `style:` Code style (formatting)
- `chore:` Maintenance tasks

**Examples:**
```
feat: Add geographic restrictions for voting

- Add IP geolocation utility
- Integrate with cast_vote service
- Add comprehensive tests

fix: Resolve idempotency race condition

- Use database-level unique constraint
- Add proper error handling
```

### Pre-commit Checklist

- [ ] Code formatted with Black
- [ ] Imports sorted with isort
- [ ] No Flake8 errors
- [ ] All tests passing
- [ ] Documentation updated (if needed)
- [ ] Migration created (if model changes)

---

## 9. Troubleshooting

### Database Connection Issues

**Symptoms:**
- `OperationalError: could not connect to server`
- `FATAL: password authentication failed`

**Solutions:**
```bash
# Check PostgreSQL is running
pg_isready

# Check .env file
grep -E "DB_NAME|DB_USER|DB_PASSWORD" .env

# Test connection
python manage.py dbshell
```

### Redis Connection Issues

**Symptoms:**
- `ConnectionError: Error connecting to Redis`
- Rate limiting not working

**Solutions:**
```bash
# Check Redis is running
redis-cli ping

# Check .env file
grep -E "REDIS_HOST|REDIS_PORT" .env

# Test connection
python manage.py shell
>>> from django.core.cache import cache
>>> cache.set('test', 'value')
>>> cache.get('test')
```

### Import Errors

**Symptoms:**
- `ModuleNotFoundError: No module named 'apps.polls'`
- `ImportError: cannot import name 'X'`

**Solutions:**
```bash
# Ensure virtual environment is activated
which python

# Check PYTHONPATH
export PYTHONPATH=/path/to/project/backend:$PYTHONPATH

# Reinstall dependencies
pip install -r requirements/development.txt
```

### Migration Issues

**Symptoms:**
- `Migration ... is applied but missing`
- `django.db.utils.OperationalError` during migrations

**Solutions:**
```bash
# Check migration status
python manage.py showmigrations

# Show migration plan
python manage.py migrate --plan

# Fake migration (careful!)
python manage.py migrate --fake app_name migration_name
```

### Static Files Not Loading

**Symptoms:**
- 404 errors for `/static/` URLs
- CSS/JS not loading

**Solutions:**
```bash
# Recollect static files
python manage.py collectstatic --noinput

# Check STATIC_ROOT
python manage.py shell
>>> from django.conf import settings
>>> print(settings.STATIC_ROOT)

# Check Nginx configuration (if using)
```

### Celery Not Working

**Symptoms:**
- Tasks not executing
- `ConnectionError` in Celery logs

**Solutions:**
```bash
# Check Celery worker is running
celery -A config inspect active

# Check Redis connection
redis-cli ping

# Check CELERY_BROKER_URL
python manage.py shell
>>> from django.conf import settings
>>> print(settings.CELERY_BROKER_URL)
```

### Port Already in Use

**Symptoms:**
- `Address already in use`
- `Port 8000 is already in use`

**Solutions:**
```bash
# Find process using port
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill process
kill -9 <PID>  # macOS/Linux
taskkill /PID <PID> /F  # Windows

# Or use different port
python manage.py runserver 8001
```

---

## Additional Resources

- **API Documentation:** `docs/api.md`
- **Deployment Guide:** `docs/deployment-guide.md`
- **Architecture Docs:** `docs/architecture-comprehensive.md`
- **SSL Setup:** `docs/SSL_SETUP_QUICKSTART.md`
- **Security Notes:** `docs/SECURITY_NOTES.md`

---

**Last Updated:** 2025-11-22
