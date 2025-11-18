"""
Celery tasks for polls app.
"""

import json
import logging
from typing import Optional

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
import pytz

from core.services.export_service import (
    estimate_export_size,
    export_analytics_report_pdf,
    export_audit_trail,
    export_poll_results_csv,
    export_poll_results_json,
    export_poll_results_pdf,
    export_vote_log,
)

logger = logging.getLogger(__name__)


@shared_task
def export_poll_data_task(
    poll_id: int,
    export_type: str,
    format: str,
    user_email: str,
    anonymize: bool = False,
    include_invalid: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Background task to export poll data and email the result.
    
    Args:
        poll_id: Poll ID
        export_type: Type of export ('results', 'vote_log', 'analytics', 'audit')
        format: Export format ('csv', 'json', 'pdf')
        user_email: Email address to send export to
        anonymize: Whether to anonymize data (for vote_log)
        include_invalid: Whether to include invalid votes (for vote_log)
        start_date: Start date for audit trail (ISO format string)
        end_date: End date for audit trail (ISO format string)
        
    Returns:
        dict: Task result with status and file info
    """
    from datetime import datetime
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    
    try:
        from apps.polls.models import Poll
        
        poll = Poll.objects.get(id=poll_id)
        
        logger.info(f"Starting export task: poll_id={poll_id}, type={export_type}, format={format}")
        
        # Generate export
        if export_type == "results":
            if format == "csv":
                content = export_poll_results_csv(poll_id)
                filename = f"poll_{poll_id}_results_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
                content_type = "text/csv"
            elif format == "json":
                content = json.dumps(export_poll_results_json(poll_id), indent=2)
                filename = f"poll_{poll_id}_results_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
                content_type = "application/json"
            elif format == "pdf":
                pdf_buffer = export_poll_results_pdf(poll_id)
                content = pdf_buffer.getvalue()
                filename = f"poll_{poll_id}_results_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                content_type = "application/pdf"
            else:
                raise ValueError(f"Unsupported format for results: {format}")
        
        elif export_type == "vote_log":
            content = export_vote_log(
                poll_id=poll_id,
                format=format,
                anonymize=anonymize,
                include_invalid=include_invalid
            )
            ext = format
            filename = f"poll_{poll_id}_vote_log_{timezone.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
            content_type = f"text/{format}" if format == "csv" else f"application/{format}"
        
        elif export_type == "analytics":
            if format != "pdf":
                raise ValueError("Analytics reports only support PDF format")
            pdf_buffer = export_analytics_report_pdf(poll_id)
            content = pdf_buffer.getvalue()
            filename = f"poll_{poll_id}_analytics_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            content_type = "application/pdf"
        
        elif export_type == "audit":
            start_dt = datetime.fromisoformat(start_date) if start_date else None
            end_dt = datetime.fromisoformat(end_date) if end_date else None
            content = export_audit_trail(
                poll_id=poll_id,
                format=format,
                start_date=start_dt,
                end_date=end_dt
            )
            ext = format
            filename = f"poll_{poll_id}_audit_{timezone.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
            content_type = f"text/{format}" if format == "csv" else f"application/{format}"
        
        else:
            raise ValueError(f"Unsupported export type: {export_type}")
        
        # Save to storage
        file_path = f"exports/{filename}"
        default_storage.save(file_path, ContentFile(content))
        
        # Generate download URL (this would be your actual URL generation logic)
        download_url = f"{settings.BASE_URL}/media/{file_path}" if hasattr(settings, 'BASE_URL') else file_path
        
        # Send email
        subject = f"Poll Export Ready: {poll.title}"
        message = f"""
Your poll export is ready!

Poll: {poll.title}
Export Type: {export_type}
Format: {format}
File: {filename}

Download: {download_url}

This link will be available for 7 days.
        """.strip()
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            fail_silently=False,
        )
        
        logger.info(f"Export task completed: poll_id={poll_id}, file={filename}")
        
        return {
            "success": True,
            "poll_id": poll_id,
            "export_type": export_type,
            "format": format,
            "filename": filename,
            "file_path": file_path,
            "download_url": download_url,
            "size_bytes": len(content) if isinstance(content, (str, bytes)) else 0,
        }
        
    except Exception as e:
        logger.error(f"Export task failed: poll_id={poll_id}, error={e}", exc_info=True)
        
        # Send error email
        try:
            send_mail(
                subject=f"Poll Export Failed: {poll.title if 'poll' in locals() else 'Unknown'}",
                message=f"An error occurred while generating your export:\n\n{str(e)}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user_email],
                fail_silently=False,
            )
        except Exception as email_error:
            logger.error(f"Failed to send error email: {email_error}")
        
        return {
            "success": False,
            "poll_id": poll_id,
            "error": str(e),
        }


@shared_task
def activate_scheduled_poll(poll_id: int):
    """
    Activate a poll that has reached its start time.
    
    Args:
        poll_id: Poll ID to activate
        
    Returns:
        dict: Task result with activation status
    """
    try:
        from apps.polls.models import Poll
        from core.services.poll_notifications import send_poll_opened_notification
        
        poll = Poll.objects.get(id=poll_id)
        now = timezone.now()
        
        # Check if poll should be activated
        if poll.starts_at <= now and not poll.is_active:
            poll.is_active = True
            poll.save(update_fields=["is_active"])
            
            logger.info(f"Activated scheduled poll: poll_id={poll_id}, starts_at={poll.starts_at}")
            
            # Send notification
            send_poll_opened_notification(poll)
            
            return {
                "success": True,
                "poll_id": poll_id,
                "action": "activated",
                "activated_at": now.isoformat(),
            }
        else:
            logger.debug(
                f"Poll {poll_id} not ready for activation: "
                f"is_active={poll.is_active}, starts_at={poll.starts_at}, now={now}"
            )
            return {
                "success": False,
                "poll_id": poll_id,
                "reason": "Poll already active or not yet ready",
            }
            
    except Poll.DoesNotExist:
        logger.error(f"Poll {poll_id} not found for activation")
        return {
            "success": False,
            "poll_id": poll_id,
            "error": "Poll not found",
        }
    except Exception as e:
        logger.error(f"Error activating poll {poll_id}: {e}", exc_info=True)
        return {
            "success": False,
            "poll_id": poll_id,
            "error": str(e),
        }


@shared_task
def close_scheduled_poll(poll_id: int):
    """
    Close a poll that has reached its end time.
    
    Args:
        poll_id: Poll ID to close
        
    Returns:
        dict: Task result with closing status
    """
    try:
        from apps.polls.models import Poll
        from core.services.poll_notifications import send_poll_closed_notification
        
        poll = Poll.objects.get(id=poll_id)
        now = timezone.now()
        
        # Check if poll should be closed
        if poll.ends_at and poll.ends_at <= now and poll.is_active:
            poll.is_active = False
            poll.save(update_fields=["is_active"])
            
            logger.info(f"Closed scheduled poll: poll_id={poll_id}, ends_at={poll.ends_at}")
            
            # Send notification
            send_poll_closed_notification(poll)
            
            return {
                "success": True,
                "poll_id": poll_id,
                "action": "closed",
                "closed_at": now.isoformat(),
            }
        else:
            logger.debug(
                f"Poll {poll_id} not ready for closing: "
                f"is_active={poll.is_active}, ends_at={poll.ends_at}, now={now}"
            )
            return {
                "success": False,
                "poll_id": poll_id,
                "reason": "Poll already closed or not yet ready",
            }
            
    except Poll.DoesNotExist:
        logger.error(f"Poll {poll_id} not found for closing")
        return {
            "success": False,
            "poll_id": poll_id,
            "error": "Poll not found",
        }
    except Exception as e:
        logger.error(f"Error closing poll {poll_id}: {e}", exc_info=True)
        return {
            "success": False,
            "poll_id": poll_id,
            "error": str(e),
        }


@shared_task
def process_scheduled_polls():
    """
    Periodic task to check and process scheduled polls.
    Checks for polls that need to be activated or closed.
    
    This task should run frequently (e.g., every minute) via Celery Beat.
    
    Returns:
        dict: Summary of processed polls
    """
    try:
        from apps.polls.models import Poll
        
        now = timezone.now()
        activated_count = 0
        closed_count = 0
        errors = []
        
        # Find polls that need to be activated
        # Polls where starts_at <= now and is_active=False
        polls_to_activate = Poll.objects.filter(
            starts_at__lte=now,
            is_active=False
        )
        
        for poll in polls_to_activate:
            try:
                # Call activation directly (not as a separate task) for efficiency
                result = activate_scheduled_poll.apply(args=(poll.id,))
                if result.result.get("success"):
                    activated_count += 1
            except Exception as e:
                logger.error(f"Error processing poll {poll.id} for activation: {e}")
                errors.append(f"Poll {poll.id}: {str(e)}")
        
        # Find polls that need to be closed
        # Polls where ends_at <= now and is_active=True
        polls_to_close = Poll.objects.filter(
            ends_at__lte=now,
            is_active=True
        )
        
        for poll in polls_to_close:
            try:
                # Call closing directly (not as a separate task) for efficiency
                result = close_scheduled_poll.apply(args=(poll.id,))
                if result.result.get("success"):
                    closed_count += 1
            except Exception as e:
                logger.error(f"Error processing poll {poll.id} for closing: {e}")
                errors.append(f"Poll {poll.id}: {str(e)}")
        
        logger.info(
            f"Processed scheduled polls: {activated_count} activated, "
            f"{closed_count} closed, {len(errors)} errors"
        )
        
        return {
            "success": True,
            "activated_count": activated_count,
            "closed_count": closed_count,
            "errors": errors,
            "processed_at": now.isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Error processing scheduled polls: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }

