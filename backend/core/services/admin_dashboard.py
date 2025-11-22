"""
Admin dashboard service for system-wide statistics and monitoring.
"""

import logging
from datetime import timedelta
from typing import Dict, List, Optional

from apps.analytics.models import (
    AuditLog,
    FraudAlert,
    IPBlock,
    IPReputation,
    IPWhitelist,
)
from apps.polls.models import Poll
from apps.votes.models import Vote
from django.contrib.auth.models import User

from django.db.models import Avg, Count, Max
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_system_statistics() -> Dict:
    """
    Get system-wide statistics.

    Returns:
        dict: System statistics including:
            - total_polls: Total number of polls
            - active_polls: Number of active polls
            - total_votes: Total number of votes
            - total_users: Total number of users
            - total_fraud_alerts: Total number of fraud alerts
            - blocked_ips: Number of blocked IPs
    """
    now = timezone.now()

    stats = {
        "total_polls": Poll.objects.count(),
        "active_polls": Poll.objects.filter(
            is_active=True, starts_at__lte=now, ends_at__gte=now
        ).count(),
        "total_votes": Vote.objects.filter(is_valid=True).count(),
        "total_users": User.objects.count(),
        "active_users_30d": User.objects.filter(
            last_login__gte=now - timedelta(days=30)
        ).count()
        if hasattr(User, "last_login")
        else 0,
        "total_fraud_alerts": FraudAlert.objects.count(),
        "blocked_ips": IPBlock.objects.filter(is_active=True).count(),
        "whitelisted_ips": IPWhitelist.objects.filter(is_active=True).count(),
    }

    # Add vote statistics
    vote_stats = Vote.objects.filter(is_valid=True).aggregate(
        total_votes=Count("id"),
        avg_votes_per_poll=Avg("poll__cached_total_votes"),
    )
    stats.update(vote_stats)

    # Add poll statistics
    poll_stats = Poll.objects.aggregate(
        avg_votes_per_poll=Avg("cached_total_votes"),
        max_votes_per_poll=Max("cached_total_votes"),
    )
    stats.update(poll_stats)

    return stats


def get_recent_activity(limit: int = 50) -> List[Dict]:
    """
    Get recent activity feed.

    Args:
        limit: Maximum number of activities to return

    Returns:
        list: List of activity dictionaries with:
            - type: Activity type (vote, poll_created, fraud_alert, etc.)
            - timestamp: When the activity occurred
            - description: Human-readable description
            - user: User who performed the action (if applicable)
            - poll: Poll related to the activity (if applicable)
    """
    activities = []
    now = timezone.now()
    cutoff = now - timedelta(days=7)  # Last 7 days

    # Recent votes
    recent_votes = (
        Vote.objects.filter(created_at__gte=cutoff)
        .select_related("user", "poll", "option")
        .order_by("-created_at")[:limit]
    )

    for vote in recent_votes:
        activities.append(
            {
                "type": "vote",
                "timestamp": vote.created_at,
                "description": f"Vote cast on '{vote.poll.title}'",
                "user": vote.user.username if vote.user else "Anonymous",
                "poll_id": vote.poll.id,
                "poll_title": vote.poll.title,
                "is_valid": vote.is_valid,
            }
        )

    # Recent polls created
    recent_polls = (
        Poll.objects.filter(created_at__gte=cutoff)
        .select_related("created_by")
        .order_by("-created_at")[:limit]
    )

    for poll in recent_polls:
        activities.append(
            {
                "type": "poll_created",
                "timestamp": poll.created_at,
                "description": f"Poll '{poll.title}' created",
                "user": poll.created_by.username if poll.created_by else "System",
                "poll_id": poll.id,
                "poll_title": poll.title,
            }
        )

    # Recent fraud alerts
    recent_alerts = (
        FraudAlert.objects.filter(created_at__gte=cutoff)
        .select_related("user", "poll")
        .order_by("-created_at")[:limit]
    )

    for alert in recent_alerts:
        activities.append(
            {
                "type": "fraud_alert",
                "timestamp": alert.created_at,
                "description": f"Fraud detected: {alert.reasons}",
                "user": alert.user.username if alert.user else "Anonymous",
                "poll_id": alert.poll.id,
                "poll_title": alert.poll.title,
                "risk_score": alert.risk_score,
            }
        )

    # Recent IP blocks
    recent_blocks = (
        IPBlock.objects.filter(blocked_at__gte=cutoff)
        .select_related("blocked_by")
        .order_by("-blocked_at")[:limit]
    )

    for block in recent_blocks:
        activities.append(
            {
                "type": "ip_blocked",
                "timestamp": block.blocked_at,
                "description": f"IP {block.ip_address} blocked: {block.reason}",
                "user": block.blocked_by.username if block.blocked_by else "System",
                "ip_address": block.ip_address,
            }
        )

    # Sort by timestamp (most recent first) and limit
    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    return activities[:limit]


def get_fraud_alerts_summary(limit: int = 20) -> Dict:
    """
    Get fraud alerts summary.

    Args:
        limit: Maximum number of recent alerts to return

    Returns:
        dict: Fraud alerts summary with:
            - total: Total number of fraud alerts
            - recent: List of recent fraud alerts
            - by_risk_score: Count of alerts by risk score ranges
            - by_poll: Top polls with fraud alerts
    """
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    total = FraudAlert.objects.count()
    recent_24h = FraudAlert.objects.filter(created_at__gte=last_24h).count()
    recent_7d = FraudAlert.objects.filter(created_at__gte=last_7d).count()

    # Recent alerts
    recent_alerts = FraudAlert.objects.select_related("user", "poll", "vote").order_by(
        "-created_at"
    )[:limit]

    alerts_list = []
    for alert in recent_alerts:
        alerts_list.append(
            {
                "id": alert.id,
                "timestamp": alert.created_at,
                "poll_id": alert.poll.id,
                "poll_title": alert.poll.title,
                "user": alert.user.username if alert.user else "Anonymous",
                "ip_address": alert.ip_address,
                "reasons": alert.reasons,
                "risk_score": alert.risk_score,
                "vote_id": alert.vote.id,
            }
        )

    # Count by risk score ranges
    risk_ranges = {
        "critical": FraudAlert.objects.filter(risk_score__gte=80).count(),
        "high": FraudAlert.objects.filter(
            risk_score__gte=60, risk_score__lt=80
        ).count(),
        "medium": FraudAlert.objects.filter(
            risk_score__gte=40, risk_score__lt=60
        ).count(),
        "low": FraudAlert.objects.filter(risk_score__lt=40).count(),
    }

    # Top polls with fraud alerts
    top_polls = (
        FraudAlert.objects.values("poll_id", "poll__title")
        .annotate(alert_count=Count("id"))
        .order_by("-alert_count")[:10]
    )

    return {
        "total": total,
        "recent_24h": recent_24h,
        "recent_7d": recent_7d,
        "recent": alerts_list,
        "by_risk_score": risk_ranges,
        "top_polls": list(top_polls),
    }


def get_performance_metrics() -> Dict:
    """
    Get performance metrics.

    Note: This is a placeholder. In production, you would track metrics
    using middleware, APM tools, or database query logging.

    Returns:
        dict: Performance metrics including:
            - api_latency: Average API response time
            - db_queries: Database query statistics
            - cache_hit_rate: Cache hit rate
            - error_rate: Error rate
    """
    # This would typically come from monitoring tools like:
    # - Django Debug Toolbar (dev)
    # - APM tools (New Relic, Datadog, etc.)
    # - Custom middleware tracking

    # For now, return placeholder data
    # In production, implement actual metric collection
    return {
        "api_latency": {
            "avg_ms": 0,  # Would be calculated from request logs
            "p95_ms": 0,
            "p99_ms": 0,
        },
        "db_queries": {
            "avg_per_request": 0,
            "total_queries": 0,
            "slow_queries": 0,
        },
        "cache_hit_rate": {
            "rate": 0.0,  # Would be calculated from cache stats
            "hits": 0,
            "misses": 0,
        },
        "error_rate": {
            "rate": 0.0,
            "total_errors": 0,
            "errors_by_type": {},
        },
        "note": "Performance metrics collection not yet implemented. Use APM tools for production monitoring.",
    }


def get_active_polls_and_voters(limit: int = 20) -> Dict:
    """
    Get active polls and recent voters.

    Args:
        limit: Maximum number of polls/voters to return

    Returns:
        dict: Active polls and voters information:
            - active_polls: List of active polls
            - recent_voters: List of recent voters
            - top_polls: Top polls by vote count
    """
    now = timezone.now()

    # Active polls (currently open)
    active_polls = (
        Poll.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now)
        .select_related("created_by")
        .order_by("-cached_total_votes")[:limit]
    )

    polls_list = []
    for poll in active_polls:
        polls_list.append(
            {
                "id": poll.id,
                "title": poll.title,
                "created_by": poll.created_by.username if poll.created_by else "System",
                "total_votes": poll.cached_total_votes,
                "unique_voters": poll.cached_unique_voters,
                "starts_at": poll.starts_at,
                "ends_at": poll.ends_at,
                "is_active": poll.is_active,
            }
        )

    # Recent voters (last 24 hours)
    last_24h = now - timedelta(hours=24)
    recent_votes = (
        Vote.objects.filter(created_at__gte=last_24h, is_valid=True)
        .select_related("user", "poll")
        .order_by("-created_at")[:limit]
    )

    voters_list = []
    seen_users = set()
    for vote in recent_votes:
        if vote.user and vote.user.id not in seen_users:
            voters_list.append(
                {
                    "user_id": vote.user.id,
                    "username": vote.user.username,
                    "last_vote_at": vote.created_at,
                    "poll_id": vote.poll.id,
                    "poll_title": vote.poll.title,
                }
            )
            seen_users.add(vote.user.id)

    # Top polls by vote count
    top_polls = Poll.objects.filter(is_active=True).order_by("-cached_total_votes")[:10]

    top_polls_list = []
    for poll in top_polls:
        top_polls_list.append(
            {
                "id": poll.id,
                "title": poll.title,
                "total_votes": poll.cached_total_votes,
                "unique_voters": poll.cached_unique_voters,
            }
        )

    return {
        "active_polls": polls_list,
        "recent_voters": voters_list,
        "top_polls": top_polls_list,
    }


def get_dashboard_summary() -> Dict:
    """
    Get complete admin dashboard summary.

    Returns:
        dict: Complete dashboard data including all metrics
    """
    return {
        "statistics": get_system_statistics(),
        "recent_activity": get_recent_activity(limit=30),
        "fraud_alerts": get_fraud_alerts_summary(limit=10),
        "performance_metrics": get_performance_metrics(),
        "active_polls_and_voters": get_active_polls_and_voters(limit=10),
        "timestamp": timezone.now(),
    }
