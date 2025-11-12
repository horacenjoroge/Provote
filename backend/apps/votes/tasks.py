"""
Celery tasks for votes app.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def analyze_fingerprint_patterns(fingerprint: str, poll_id: int):
    """
    Async task to analyze fingerprint patterns for fraud detection.
    
    This task performs deep analysis of historical fingerprint data
    without blocking vote creation.
    
    Args:
        fingerprint: Browser fingerprint hash
        poll_id: Poll ID
    """
    if not fingerprint:
        return

    try:
        from apps.votes.models import Vote

        # Analyze historical data (longer time window than real-time check)
        analysis_window_hours = getattr(
            settings, "FINGERPRINT_ANALYSIS_WINDOW_HOURS", 168
        )  # 7 days default
        cutoff = timezone.now() - timedelta(hours=analysis_window_hours)

        # Query historical votes with this fingerprint
        historical_votes = (
            Vote.objects.filter(
                fingerprint=fingerprint,
                poll_id=poll_id,
                created_at__gte=cutoff,
            )
            .values("user_id", "ip_address", "created_at", "poll_id")
            .order_by("-created_at")
        )

        if not historical_votes:
            return

        # Analyze patterns
        distinct_users = set(v["user_id"] for v in historical_votes if v["user_id"])
        distinct_ips = set(
            v["ip_address"] for v in historical_votes if v["ip_address"]
        )
        vote_count = len(historical_votes)

        # Calculate statistics
        first_vote = historical_votes[-1]["created_at"]
        last_vote = historical_votes[0]["created_at"]
        time_span_hours = (last_vote - first_vote).total_seconds() / 3600

        # Determine risk level
        risk_factors = []
        risk_score = 0

        if len(distinct_users) >= getattr(
            settings, "FINGERPRINT_SUSPICIOUS_THRESHOLDS", {}
        ).get("different_users", 2):
            risk_factors.append("multiple_users")
            risk_score += 40

        if len(distinct_ips) >= getattr(
            settings, "FINGERPRINT_SUSPICIOUS_THRESHOLDS", {}
        ).get("different_ips", 2):
            risk_factors.append("multiple_ips")
            risk_score += 30

        if time_span_hours > 0:
            votes_per_hour = vote_count / time_span_hours
            if votes_per_hour > 10:  # More than 10 votes per hour
                risk_factors.append("high_frequency")
                risk_score += 20

        # Update Redis cache with analysis results
        cache_key = f"fp:activity:{fingerprint}:{poll_id}"
        cache_ttl = getattr(settings, "FINGERPRINT_CACHE_TTL", 3600)

        cached_data = cache.get(cache_key, {})
        cached_data.update(
            {
                "analysis_completed": True,
                "analysis_timestamp": timezone.now().isoformat(),
                "historical_vote_count": vote_count,
                "historical_user_count": len(distinct_users),
                "historical_ip_count": len(distinct_ips),
                "risk_factors": risk_factors,
                "risk_score": min(risk_score, 100),
            }
        )

        cache.set(cache_key, cached_data, cache_ttl)

        # Log critical findings
        if risk_score >= 70:
            logger.warning(
                f"High-risk fingerprint detected: {fingerprint} for poll {poll_id}. "
                f"Risk score: {risk_score}, Factors: {', '.join(risk_factors)}"
            )

    except Exception as e:
        logger.error(f"Error in async fingerprint analysis: {e}")

