"""
Notification service for poll events (open/close).
"""

import logging


from django.conf import settings
from django.core.mail import send_mail


logger = logging.getLogger(__name__)


def send_poll_opened_notification(poll) -> bool:
    """
    Send notification when a poll opens.

    Args:
        poll: Poll instance that was opened

    Returns:
        bool: True if notification sent successfully, False otherwise
    """
    try:
        # Get poll creator email
        creator_email = (
            poll.created_by.email if poll.created_by and poll.created_by.email else None
        )

        if not creator_email:
            logger.warning(
                f"Cannot send poll opened notification: no email for poll {poll.id} creator"
            )
            return False

        subject = f"Poll Opened: {poll.title}"
        message = f"""
Your poll "{poll.title}" has been opened and is now accepting votes.

Poll Details:
- Title: {poll.title}
- Description: {poll.description or 'No description'}
- Started: {poll.starts_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
- Ends: {poll.ends_at.strftime('%Y-%m-%d %H:%M:%S UTC') if poll.ends_at else 'No end date'}

You can view the poll and results at: {get_poll_url(poll.id)}

Thank you for using Provote!
        """.strip()

        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@provote.com"),
            recipient_list=[creator_email],
            fail_silently=False,
        )

        logger.info(
            f"Sent poll opened notification for poll {poll.id} to {creator_email}"
        )
        return True

    except Exception as e:
        logger.error(
            f"Error sending poll opened notification for poll {poll.id}: {e}",
            exc_info=True,
        )
        return False


def send_poll_closed_notification(poll) -> bool:
    """
    Send notification when a poll closes.

    Args:
        poll: Poll instance that was closed

    Returns:
        bool: True if notification sent successfully, False otherwise
    """
    try:
        # Use new notification system
        from apps.notifications.services import notify_poll_results_available

        # Notify poll creator that results are available
        notify_poll_results_available(poll, user=poll.created_by)

        logger.info(
            f"Sent poll closed notification for poll {poll.id} to {poll.created_by.username if poll.created_by else 'unknown'}"
        )
        return True

    except Exception as e:
        logger.error(
            f"Error sending poll closed notification for poll {poll.id}: {e}",
            exc_info=True,
        )
        return False


def get_poll_url(poll_id: int) -> str:
    """
    Generate URL for a poll.

    Args:
        poll_id: Poll ID

    Returns:
        str: Poll URL
    """
    base_url = getattr(settings, "BASE_URL", "http://localhost:8000")
    return f"{base_url}/api/v1/polls/{poll_id}/"
