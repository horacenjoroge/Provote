"""
Export service for poll data in multiple formats.
Supports CSV, JSON, and PDF exports with anonymization options.
"""

import csv
import hashlib
import json
import logging
from datetime import datetime
from io import BytesIO, StringIO
from typing import Dict, Optional

from apps.analytics.models import AuditLog
from apps.polls.models import Poll
from apps.votes.models import Vote
from core.services.poll_analytics import get_comprehensive_analytics


from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


def anonymize_ip(ip_address: Optional[str]) -> str:
    """
    Anonymize IP address by masking last octet.

    Args:
        ip_address: IP address to anonymize

    Returns:
        str: Anonymized IP (e.g., "192.168.1.xxx")
    """
    if not ip_address:
        return "N/A"

    parts = ip_address.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
    return "xxx"


def anonymize_email(email: Optional[str]) -> str:
    """
    Anonymize email address by masking domain.

    Args:
        email: Email address to anonymize

    Returns:
        str: Anonymized email (e.g., "user@xxx.com")
    """
    if not email:
        return "N/A"

    if "@" in email:
        local, domain = email.split("@", 1)
        return f"{local}@xxx"
    return "xxx"


def anonymize_user_id(user_id: Optional[int]) -> str:
    """
    Anonymize user ID by hashing.

    Args:
        user_id: User ID to anonymize

    Returns:
        str: Hashed user ID
    """
    if not user_id:
        return "anonymous"

    return hashlib.sha256(str(user_id).encode()).hexdigest()[:8]


def export_poll_results_csv(poll_id: int) -> str:
    """
    Export poll results to CSV format.

    Args:
        poll_id: Poll ID

    Returns:
        str: CSV content
    """
    from apps.polls.services import export_results_to_csv

    # Use existing export function
    return export_results_to_csv(poll_id)


def export_poll_results_json(poll_id: int) -> Dict:
    """
    Export poll results to JSON format.

    Args:
        poll_id: Poll ID

    Returns:
        dict: Results as dictionary
    """
    from apps.polls.services import export_results_to_json

    # Use existing export function
    results = export_results_to_json(poll_id)
    results["exported_at"] = timezone.now().isoformat()
    return results


def export_poll_results_pdf(poll_id: int) -> BytesIO:
    """
    Export poll results to PDF format.

    Args:
        poll_id: Poll ID

    Returns:
        BytesIO: PDF content as bytes
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        raise ImportError(
            "reportlab is required for PDF exports. Install with: pip install reportlab"
        )

    from apps.polls.services import calculate_poll_results

    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        raise ValueError(f"Poll {poll_id} not found")

    results = calculate_poll_results(poll_id, use_cache=True)

    # Create PDF buffer
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()

    # Title
    title = Paragraph(f"Poll Results: {results['poll_title']}", styles["Title"])
    story.append(title)
    story.append(Spacer(1, 0.2 * inch))

    # Poll information
    info_data = [
        ["Poll ID:", str(poll.id)],
        ["Total Votes:", str(results["total_votes"])],
        ["Unique Voters:", str(results["unique_voters"])],
        ["Participation Rate:", f"{results['participation_rate']}%"],
        ["Exported At:", timezone.now().strftime("%Y-%m-%d %H:%M:%S")],
    ]

    info_table = Table(info_data, colWidths=[2 * inch, 4 * inch])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 0.3 * inch))

    # Results table
    results_data = [["Option", "Votes", "Percentage", "Winner"]]
    for option in results["options"]:
        results_data.append(
            [
                option["option_text"],
                str(option["votes"]),
                f"{option['percentage']}%",
                "✓" if option["is_winner"] else "",
            ]
        )

    results_table = Table(
        results_data, colWidths=[3 * inch, 1 * inch, 1.5 * inch, 0.8 * inch]
    )
    results_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ALIGN", (1, 0), (2, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]
        )
    )
    story.append(results_table)

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


def export_vote_log(
    poll_id: int,
    format: str = "csv",
    anonymize: bool = False,
    include_invalid: bool = False,
) -> str:
    """
    Export vote log for a poll.

    Args:
        poll_id: Poll ID
        format: Export format ('csv' or 'json')
        anonymize: Whether to anonymize user data
        include_invalid: Whether to include invalid votes

    Returns:
        str: Export content (CSV string or JSON string)
    """
    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        raise ValueError(f"Poll {poll_id} not found")

    # Get votes
    votes_query = Vote.objects.filter(poll_id=poll_id).select_related("user", "option")
    if not include_invalid:
        votes_query = votes_query.filter(is_valid=True)

    votes = votes_query.order_by("-created_at")

    if format == "csv":
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["Vote Log Export"])
        writer.writerow([f"Poll ID: {poll.id}"])
        writer.writerow([f"Poll Title: {poll.title}"])
        writer.writerow([f"Exported At: {timezone.now().isoformat()}"])
        writer.writerow([f"Anonymized: {anonymize}"])
        writer.writerow([])

        # Column headers
        headers = [
            "Vote ID",
            "Timestamp",
            "Option",
            "User",
            "IP Address",
            "User Agent",
            "Valid",
        ]
        if not anonymize:
            headers.extend(["Fingerprint", "Voter Token"])
        writer.writerow(headers)

        # Vote data
        for vote in votes:
            user_info = (
                vote.user.username
                if vote.user and not anonymize
                else (anonymize_user_id(vote.user.id) if vote.user else "Anonymous")
            )
            ip_info = (
                vote.ip_address if not anonymize else anonymize_ip(vote.ip_address)
            )

            row = [
                vote.id,
                vote.created_at.isoformat(),
                vote.option.text,
                user_info,
                ip_info,
                vote.user_agent[:50] if vote.user_agent else "N/A",  # Truncate long UAs
                "Yes" if vote.is_valid else "No",
            ]

            if not anonymize:
                row.extend(
                    [
                        vote.fingerprint[:16] + "..." if vote.fingerprint else "N/A",
                        vote.voter_token[:16] + "..." if vote.voter_token else "N/A",
                    ]
                )

            writer.writerow(row)

        return output.getvalue()

    elif format == "json":
        votes_data = []
        for vote in votes:
            vote_dict = {
                "vote_id": vote.id,
                "timestamp": vote.created_at.isoformat(),
                "option_id": vote.option.id,
                "option_text": vote.option.text,
                "is_valid": vote.is_valid,
            }

            if anonymize:
                vote_dict["user"] = (
                    anonymize_user_id(vote.user.id) if vote.user else "anonymous"
                )
                vote_dict["ip_address"] = anonymize_ip(vote.ip_address)
                vote_dict["user_agent"] = "anonymized" if vote.user_agent else None
            else:
                vote_dict["user"] = vote.user.username if vote.user else None
                vote_dict["user_id"] = vote.user.id if vote.user else None
                vote_dict["ip_address"] = vote.ip_address
                vote_dict["user_agent"] = vote.user_agent
                vote_dict["fingerprint"] = vote.fingerprint
                vote_dict["voter_token"] = vote.voter_token

            votes_data.append(vote_dict)

        export_data = {
            "poll_id": poll.id,
            "poll_title": poll.title,
            "exported_at": timezone.now().isoformat(),
            "anonymized": anonymize,
            "include_invalid": include_invalid,
            "total_votes": len(votes_data),
            "votes": votes_data,
        }

        return json.dumps(export_data, indent=2)

    else:
        raise ValueError(f"Unsupported format: {format}")


def export_analytics_report_pdf(poll_id: int) -> BytesIO:
    """
    Export analytics report as PDF.

    Args:
        poll_id: Poll ID

    Returns:
        BytesIO: PDF content as bytes
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        raise ImportError(
            "reportlab is required for PDF exports. Install with: pip install reportlab"
        )

    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        raise ValueError(f"Poll {poll_id} not found")

    analytics = get_comprehensive_analytics(poll_id)

    # Create PDF buffer
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()

    # Title
    title = Paragraph(f"Analytics Report: {poll.title}", styles["Title"])
    story.append(title)
    story.append(Spacer(1, 0.2 * inch))

    # Summary
    summary_data = [
        ["Metric", "Value"],
        ["Total Votes", str(analytics.get("total_votes", 0))],
        ["Unique Voters", str(analytics.get("unique_voters", 0))],
        [
            "Participation Rate",
            f"{analytics.get('participation_rate', {}).get('rate', 0)}%",
        ],
    ]

    if "average_time_to_vote" in analytics:
        summary_data.append(
            ["Avg Time to Vote", f"{analytics['average_time_to_vote']:.2f} hours"]
        )

    summary_table = Table(summary_data, colWidths=[3 * inch, 3 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 0.3 * inch))

    # Vote distribution
    if "vote_distribution" in analytics:
        dist_data = [["Option", "Votes", "Percentage"]]
        for dist in analytics["vote_distribution"]:
            dist_data.append(
                [
                    dist.get("option_text", "N/A"),
                    str(dist.get("votes", 0)),
                    f"{dist.get('percentage', 0)}%",
                ]
            )

        dist_table = Table(dist_data, colWidths=[3 * inch, 1.5 * inch, 1.5 * inch])
        dist_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ALIGN", (1, 0), (2, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )
        story.append(dist_table)

    # Footer
    story.append(Spacer(1, 0.3 * inch))
    footer = Paragraph(
        f"Generated on {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]
    )
    story.append(footer)

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


def export_audit_trail(
    poll_id: Optional[int] = None,
    format: str = "csv",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> str:
    """
    Export audit trail for polls or system-wide.

    Args:
        poll_id: Poll ID (None for system-wide, filters by path containing poll ID)
        format: Export format ('csv' or 'json')
        start_date: Start date filter
        end_date: End date filter

    Returns:
        str: Export content
    """
    # Get audit logs
    audit_query = AuditLog.objects.all()

    if poll_id:
        # Filter by path containing poll ID
        audit_query = audit_query.filter(path__contains=f"/polls/{poll_id}/")

    if start_date:
        audit_query = audit_query.filter(created_at__gte=start_date)

    if end_date:
        audit_query = audit_query.filter(created_at__lte=end_date)

    audit_logs = audit_query.select_related("user").order_by("-created_at")

    if format == "csv":
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["Audit Trail Export"])
        if poll_id:
            writer.writerow([f"Poll ID: {poll_id}"])
        else:
            writer.writerow(["Scope: System-wide"])
        writer.writerow([f"Exported At: {timezone.now().isoformat()}"])
        if start_date:
            writer.writerow([f"Start Date: {start_date.isoformat()}"])
        if end_date:
            writer.writerow([f"End Date: {end_date.isoformat()}"])
        writer.writerow([])

        # Column headers
        writer.writerow(
            [
                "ID",
                "Timestamp",
                "Method",
                "Path",
                "User",
                "IP Address",
                "Status Code",
                "Response Time (s)",
            ]
        )

        # Audit log data
        for log in audit_logs:
            writer.writerow(
                [
                    log.id,
                    log.created_at.isoformat(),
                    log.method,
                    log.path,
                    log.user.username if log.user else "Anonymous",
                    log.ip_address or "N/A",
                    log.status_code,
                    f"{log.response_time:.3f}",
                ]
            )

        return output.getvalue()

    elif format == "json":
        logs_data = []
        for log in audit_logs:
            logs_data.append(
                {
                    "id": log.id,
                    "timestamp": log.created_at.isoformat(),
                    "method": log.method,
                    "path": log.path,
                    "user": log.user.username if log.user else None,
                    "user_id": log.user.id if log.user else None,
                    "ip_address": log.ip_address,
                    "status_code": log.status_code,
                    "response_time": log.response_time,
                    "user_agent": log.user_agent,
                    "request_id": log.request_id,
                }
            )

        export_data = {
            "scope": f"poll_{poll_id}" if poll_id else "system-wide",
            "exported_at": timezone.now().isoformat(),
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "total_logs": len(logs_data),
            "logs": logs_data,
        }

        return json.dumps(export_data, indent=2)

    else:
        raise ValueError(f"Unsupported format: {format}")


def estimate_export_size(poll_id: int, export_type: str) -> int:
    """
    Estimate export size in bytes.

    Args:
        poll_id: Poll ID
        export_type: Type of export ('results', 'vote_log', 'analytics', 'audit')

    Returns:
        int: Estimated size in bytes
    """
    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        return 0

    if export_type == "results":
        # Estimate based on number of options
        return poll.options.count() * 200  # ~200 bytes per option

    elif export_type == "vote_log":
        # Estimate based on number of votes
        vote_count = Vote.objects.filter(poll_id=poll_id).count()
        return vote_count * 500  # ~500 bytes per vote

    elif export_type == "analytics":
        # Analytics reports are typically small
        return 10000  # ~10KB

    elif export_type == "audit":
        # Estimate based on audit logs
        log_count = AuditLog.objects.filter(poll_id=poll_id).count()
        return log_count * 300  # ~300 bytes per log

    return 0
