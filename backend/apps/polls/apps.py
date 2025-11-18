import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class PollsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.polls"
    label = "polls"

    def ready(self):
        """
        Initialize Redis Pub/Sub subscriber when app is ready.
        This starts the subscriber in a background thread to listen for vote events.
        Also import translations to register them with modeltranslation.
        """
        # Import translations to register with modeltranslation
        try:
            from . import translation  # noqa: F401
        except ImportError:
            pass  # Translation module may not exist in all environments
        
        # Only start subscriber in non-test environments
        import sys
        from django.conf import settings
        
        # Skip if running tests, migrations, or in test settings
        if (
            "test" in sys.argv
            or "migrate" in sys.argv
            or "makemigrations" in sys.argv
            or "pytest" in sys.modules
            or getattr(settings, "TESTING", False)
        ):
            return
        
        try:
            from core.utils.redis_pubsub import get_subscriber, setup_signal_handlers
            
            # Setup signal handlers for graceful shutdown
            setup_signal_handlers()
            
            # Start the subscriber
            subscriber = get_subscriber()
            if not subscriber.is_running():
                subscriber.start()
                logger.info("PollsConfig: Redis Pub/Sub subscriber started")
        except Exception as e:
            logger.error(f"PollsConfig: Failed to start Redis Pub/Sub subscriber: {e}")
