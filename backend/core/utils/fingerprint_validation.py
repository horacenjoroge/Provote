"""
Fingerprint validation utilities for efficient fraud detection.
Uses Redis caching and time-windowed database queries to handle millions of votes.
"""

import json
import logging
from datetime import timedelta
from typing import Dict, List, Optional

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_fingerprint_cache_key(fingerprint: str, poll_id: int) -> str:
    """Generate Redis cache key for fingerprint activity."""
    return f"fp:activity:{fingerprint}:{poll_id}"


def check_fingerprint_suspicious(
    fingerprint: str,
    poll_id: int,
    user_id: int,
    ip_address: Optional[str] = None,
    request=None,
) -> Dict:
    """
    Check if fingerprint shows suspicious patterns using multi-tier validation.

    Args:
        fingerprint: Browser fingerprint hash
        poll_id: Poll ID
        user_id: Current user ID
        ip_address: Current IP address
        request: Django request object (optional)

    Returns:
        dict: {
            "suspicious": bool,
            "reasons": List[str],
            "risk_score": int (0-100),
            "block_vote": bool
        }
    """
    if not fingerprint:
        return {"suspicious": False, "reasons": [], "risk_score": 0, "block_vote": False}

    # Check if fingerprint validation is enabled
    if not getattr(settings, "FINGERPRINT_CHECK_ENABLED", True):
        return {"suspicious": False, "reasons": [], "risk_score": 0, "block_vote": False}

    reasons = []
    risk_score = 0
    block_vote = False

    # Tier 1: Check Redis cache (fast)
    cache_key = get_fingerprint_cache_key(fingerprint, poll_id)
    cached_data = cache.get(cache_key)

    if cached_data:
        # Use cached data for fast check
        user_count = cached_data.get("user_count", 0)
        ip_count = cached_data.get("ip_count", 0)
        count = cached_data.get("count", 0)
        first_seen = cached_data.get("first_seen")
        last_seen = cached_data.get("last_seen")

        # Check for different users
        cached_users = set(cached_data.get("users", []))
        if user_count >= getattr(
            settings, "FINGERPRINT_SUSPICIOUS_THRESHOLDS", {}
        ).get("different_users", 2):
            # Only block if current user is not in the cached users set
            if user_id not in cached_users:
                reasons.append(
                    f"Same fingerprint used by {user_count} different users"
                )
                risk_score += 40
                block_vote = True  # Critical: block vote
            elif user_count > 1:
                # Current user is in set, but there are other users - suspicious but don't block
                reasons.append(
                    f"Same fingerprint used by {user_count} different users"
                )
                risk_score += 20

        # Check for different IPs
        if ip_count >= getattr(
            settings, "FINGERPRINT_SUSPICIOUS_THRESHOLDS", {}
        ).get("different_ips", 2):
            reasons.append(f"Same fingerprint from {ip_count} different IPs")
            risk_score += 30

        # Check for rapid votes
        if first_seen and last_seen:
            try:
                from datetime import datetime
                if isinstance(last_seen, str):
                    last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                    if timezone.is_naive(last_seen_dt):
                        last_seen_dt = timezone.make_aware(last_seen_dt)
                else:
                    last_seen_dt = last_seen
                time_diff = (timezone.now() - last_seen_dt).total_seconds() / 60
            except (ValueError, AttributeError):
                # If parsing fails, skip rapid vote check
                time_diff = None
            rapid_threshold_minutes = getattr(
                settings, "FINGERPRINT_SUSPICIOUS_THRESHOLDS", {}
            ).get("rapid_votes_minutes", 5)
            rapid_threshold_count = getattr(
                settings, "FINGERPRINT_SUSPICIOUS_THRESHOLDS", {}
            ).get("rapid_votes_count", 3)

            if time_diff is not None and time_diff <= rapid_threshold_minutes and count >= rapid_threshold_count:
                reasons.append(
                    f"{count} votes from same fingerprint within {rapid_threshold_minutes} minutes"
                )
                risk_score += 30

        # If we have cached data and it's suspicious, return early
        if reasons:
            return {
                "suspicious": True,
                "reasons": reasons,
                "risk_score": min(risk_score, 100),
                "block_vote": block_vote,
            }

    # Tier 2: Time-windowed database query (if cache miss or needs verification)
    time_window_hours = getattr(settings, "FINGERPRINT_TIME_WINDOW_HOURS", 24)
    recent_cutoff = timezone.now() - timedelta(hours=time_window_hours)

    try:
        from apps.votes.models import Vote

        # Query only recent votes using composite index
        recent_votes = (
            Vote.objects.filter(
                fingerprint=fingerprint,
                poll_id=poll_id,
                created_at__gte=recent_cutoff,
            )
            .values("user_id", "ip_address", "created_at")
            .order_by("-created_at")[:1000]  # Limit to prevent excessive memory
        )

        if recent_votes:
            # Analyze patterns
            distinct_users = set(v["user_id"] for v in recent_votes if v["user_id"])
            distinct_ips = set(
                v["ip_address"] for v in recent_votes if v["ip_address"]
            )
            vote_count = len(recent_votes)

            # Check for different users
            if len(distinct_users) >= getattr(
                settings, "FINGERPRINT_SUSPICIOUS_THRESHOLDS", {}
            ).get("different_users", 2):
                # If current user is not in the set, or there are multiple users, it's suspicious
                if user_id not in distinct_users or len(distinct_users) > 1:
                    reasons.append(
                        f"Same fingerprint used by {len(distinct_users)} different users"
                    )
                    risk_score += 40
                    # Only block if current user is different from existing users
                    if user_id not in distinct_users:
                        block_vote = True  # Critical: block vote

            # Check for different IPs
            if ip_address and len(distinct_ips) >= getattr(
                settings, "FINGERPRINT_SUSPICIOUS_THRESHOLDS", {}
            ).get("different_ips", 2):
                reasons.append(
                    f"Same fingerprint from {len(distinct_ips)} different IPs"
                )
                risk_score += 30

            # Check for rapid votes
            if vote_count >= 2:
                first_vote_time = recent_votes[-1]["created_at"]
                last_vote_time = recent_votes[0]["created_at"]
                time_diff_minutes = (
                    (last_vote_time - first_vote_time).total_seconds() / 60
                )

                rapid_threshold_minutes = getattr(
                    settings, "FINGERPRINT_SUSPICIOUS_THRESHOLDS", {}
                ).get("rapid_votes_minutes", 5)
                rapid_threshold_count = getattr(
                    settings, "FINGERPRINT_SUSPICIOUS_THRESHOLDS", {}
                ).get("rapid_votes_count", 3)

                if (
                    time_diff_minutes <= rapid_threshold_minutes
                    and vote_count >= rapid_threshold_count
                ):
                    reasons.append(
                        f"{vote_count} votes from same fingerprint within {time_diff_minutes:.1f} minutes"
                    )
                    risk_score += 30

            # Update Redis cache with findings
            update_fingerprint_cache(
                fingerprint=fingerprint,
                poll_id=poll_id,
                user_id=user_id,
                ip_address=ip_address,
                vote_count=vote_count,
                distinct_users=distinct_users,
                distinct_ips=distinct_ips,
            )

    except Exception as e:
        logger.error(f"Error checking fingerprint in database: {e}")
        # On error, allow vote but log warning
        return {"suspicious": False, "reasons": [], "risk_score": 0, "block_vote": False}

    return {
        "suspicious": len(reasons) > 0,
        "reasons": reasons,
        "risk_score": min(risk_score, 100),
        "block_vote": block_vote,
    }


def update_fingerprint_cache(
    fingerprint: str,
    poll_id: int,
    user_id: int,
    ip_address: Optional[str] = None,
    vote_count: Optional[int] = None,
    distinct_users: Optional[set] = None,
    distinct_ips: Optional[set] = None,
):
    """
    Update Redis cache with fingerprint activity.

    Args:
        fingerprint: Browser fingerprint hash
        poll_id: Poll ID
        user_id: User ID
        ip_address: IP address
        vote_count: Number of votes (if known from DB query)
        distinct_users: Set of user IDs (if known from DB query)
        distinct_ips: Set of IP addresses (if known from DB query)
    """
    if not fingerprint:
        return

    cache_key = get_fingerprint_cache_key(fingerprint, poll_id)
    cache_ttl = getattr(settings, "FINGERPRINT_CACHE_TTL", 3600)  # 1 hour default

    try:
        cached_data = cache.get(cache_key)

        if cached_data:
            # Update existing cache
            cached_data["count"] = cached_data.get("count", 0) + 1
            cached_data["last_seen"] = timezone.now().isoformat()

            # Update user set (limit to recent 10)
            users_set = set(cached_data.get("users", []))
            users_set.add(user_id)
            cached_data["users"] = list(users_set)[:10]
            cached_data["user_count"] = len(users_set)

            # Update IP set (limit to recent 10)
            if ip_address:
                ips_set = set(cached_data.get("ips", []))
                ips_set.add(ip_address)
                cached_data["ips"] = list(ips_set)[:10]
                cached_data["ip_count"] = len(ips_set)

            if not cached_data.get("first_seen"):
                cached_data["first_seen"] = timezone.now().isoformat()
        else:
            # Create new cache entry
            cached_data = {
                "count": vote_count or 1,
                "first_seen": timezone.now().isoformat(),
                "last_seen": timezone.now().isoformat(),
                "user_count": len(distinct_users) if distinct_users else 1,
                "ip_count": len(distinct_ips) if distinct_ips else (1 if ip_address else 0),
                "users": list(distinct_users)[:10] if distinct_users else [user_id],
                "ips": list(distinct_ips)[:10] if distinct_ips else ([ip_address] if ip_address else []),
            }

        # Store in cache with TTL
        cache.set(cache_key, cached_data, cache_ttl)

    except Exception as e:
        logger.error(f"Error updating fingerprint cache: {e}")
        # Don't fail vote creation if cache update fails

