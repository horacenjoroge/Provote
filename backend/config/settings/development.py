"""
Development settings for Provote project.
"""

from .base import *  # noqa: F403, F401

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Development-specific apps
INSTALLED_APPS += [  # noqa: F405
    "debug_toolbar",
    "django_extensions",
]

# Development-specific middleware
MIDDLEWARE += [  # noqa: F405
    "debug_toolbar.middleware.DebugToolbarMiddleware",
]

# Debug Toolbar
INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
]

# Email backend for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable security features for development
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Logging for development
LOGGING["loggers"]["django"]["level"] = "DEBUG"  # noqa: F405
