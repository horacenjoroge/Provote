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


def validate_fingerprint_format(fingerprint: str) -> tuple[bool, Optional[str]]:
    """
    Validate fingerprint format.
    
    Args:
        fingerprint: Browser fingerprint hash to validate
        
    Returns:
        tuple: (is_valid: bool, error_message: Optional[str])
    """
    if not fingerprint:
        return False, "Fingerprint is required"
    
    # SHA256 hex digest should be 64 characters
    if len(fingerprint) != 64:
        return False, f"Invalid fingerprint format: expected 64 characters, got {len(fingerprint)}"
    
    # Check if it's valid hexadecimal
    try:
        int(fingerprint, 16)
    except ValueError:
        return False, "Invalid fingerprint format: not hexadecimal"
    
    return True, None


def require_fingerprint_for_anonymous(user: Optional[object], fingerprint: Optional[str]) -> tuple[bool, Optional[str]]:
    """
    Check if fingerprint is required for anonymous votes.
    
    Args:
        user: User object (None for anonymous)
        fingerprint: Browser fingerprint hash
        
    Returns:
        tuple: (is_valid: bool, error_message: Optional[str])
    """
    # If user is authenticated, fingerprint is optional
    if user and user.is_authenticated:
        return True, None
    
    # For anonymous users, fingerprint is required
    if not fingerprint:
        return False, "Fingerprint is required for anonymous votes"
    
    # Validate format
    is_valid, error_message = validate_fingerprint_format(fingerprint)
    if not is_valid:
        return False, error_message
    
    return True, None


def detect_suspicious_fingerprint_changes(
    fingerprint: str,
    user_id: Optional[int],
    ip_address: Optional[str],
    poll_id: int,
) -> Dict:
    """
    Detect suspicious fingerprint changes for a user/IP combination.
    
    Tracks fingerprint history and flags rapid changes or changes from different IPs.
    
    Args:
        fingerprint: Current browser fingerprint hash
        user_id: User ID (None for anonymous)
        ip_address: Current IP address
        poll_id: Poll ID
        
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
    
    reasons = []
    risk_score = 0
    block_vote = False
    
    try:
        from apps.votes.models import Vote
        
        # Look for previous votes from this user/IP combination
        query = Vote.objects.filter(poll_id=poll_id)
        
        if user_id:
            # For authenticated users, check their vote history
            query = query.filter(user_id=user_id)
        elif ip_address:
            # For anonymous users, check by IP
            query = query.filter(ip_address=ip_address)
        else:
            # No way to identify voter, skip check
            return {"suspicious": False, "reasons": [], "risk_score": 0, "block_vote": False}
        
        # Get recent votes (last 24 hours)
        time_window_hours = getattr(settings, "FINGERPRINT_TIME_WINDOW_HOURS", 24)
        recent_cutoff = timezone.now() - timedelta(hours=time_window_hours)
        recent_votes = query.filter(created_at__gte=recent_cutoff).order_by("-created_at")[:10]
        
        if recent_votes:
            # Check for fingerprint changes
            distinct_fingerprints = set(v.fingerprint for v in recent_votes if v.fingerprint)
            
            if len(distinct_fingerprints) > 1:
                # Multiple fingerprints detected
                if fingerprint not in distinct_fingerprints:
                    # New fingerprint not seen before for this user/IP
                    reasons.append("Fingerprint changed from previous votes")
                    risk_score += 30
                    
                    # If user is authenticated and fingerprint changed, it's more suspicious
                    if user_id:
                        reasons.append("Authenticated user using different fingerprint")
                        risk_score += 20
                    
                    # Check if fingerprint is from a different IP
                    if ip_address:
                        fingerprint_votes = Vote.objects.filter(
                            fingerprint=fingerprint,
                            poll_id=poll_id,
                            created_at__gte=recent_cutoff,
                        ).exclude(ip_address=ip_address)
                        
                        if fingerprint_votes.exists():
                            reasons.append("Fingerprint previously seen from different IP")
                            risk_score += 40
                            block_vote = True  # Critical: same fingerprint from different IPs
            
            # Check for rapid fingerprint changes (multiple changes in short time)
            if len(recent_votes) >= 2:
                first_vote = recent_votes[-1]
                last_vote = recent_votes[0]
                time_diff_minutes = (last_vote.created_at - first_vote.created_at).total_seconds() / 60
                
                if time_diff_minutes <= 60 and len(distinct_fingerprints) >= 3:  # 3+ fingerprints in 1 hour
                    reasons.append(f"Rapid fingerprint changes: {len(distinct_fingerprints)} fingerprints in {time_diff_minutes:.1f} minutes")
                    risk_score += 50
                    block_vote = True
        
    except Exception as e:
        logger.error(f"Error detecting suspicious fingerprint changes: {e}")
        # On error, allow vote but log warning
        return {"suspicious": False, "reasons": [], "risk_score": 0, "block_vote": False}
    
    return {
        "suspicious": len(reasons) > 0,
        "reasons": reasons,
        "risk_score": min(risk_score, 100),
        "block_vote": block_vote,
    }


def check_fingerprint_ip_combination(
    fingerprint: str,
    ip_address: Optional[str],
    poll_id: int,
) -> Dict:
    """
    Check for suspicious patterns when same fingerprint is used from different IPs.
    
    Args:
        fingerprint: Browser fingerprint hash
        ip_address: Current IP address
        poll_id: Poll ID
        
    Returns:
        dict: {
            "suspicious": bool,
            "reasons": List[str],
            "risk_score": int (0-100),
            "block_vote": bool
        }
    """
    if not fingerprint or not ip_address:
        return {"suspicious": False, "reasons": [], "risk_score": 0, "block_vote": False}
    
    reasons = []
    risk_score = 0
    block_vote = False
    
    try:
        from apps.votes.models import Vote
        
        # Check if this fingerprint has been used from different IPs
        time_window_hours = getattr(settings, "FINGERPRINT_TIME_WINDOW_HOURS", 24)
        recent_cutoff = timezone.now() - timedelta(hours=time_window_hours)
        
        fingerprint_votes = Vote.objects.filter(
            fingerprint=fingerprint,
            poll_id=poll_id,
            created_at__gte=recent_cutoff,
        ).exclude(ip_address=ip_address).values_list("ip_address", flat=True).distinct()
        
        distinct_ips = [ip for ip in fingerprint_votes if ip]
        
        if distinct_ips:
            ip_count = len(distinct_ips)
            reasons.append(f"Same fingerprint used from {ip_count} different IP address(es)")
            risk_score += 40
            
            # If same fingerprint from 2+ different IPs, block vote
            if ip_count >= 2:
                block_vote = True
                reasons.append("Fingerprint appears to be shared across multiple IPs (potential fraud)")
                risk_score += 30
        
    except Exception as e:
        logger.error(f"Error checking fingerprint-IP combination: {e}")
        # On error, allow vote but log warning
        return {"suspicious": False, "reasons": [], "risk_score": 0, "block_vote": False}
    
    return {
        "suspicious": len(reasons) > 0,
        "reasons": reasons,
        "risk_score": min(risk_score, 100),
        "block_vote": block_vote,
    }


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

    # Tier 0: Check if fingerprint is permanently blocked (highest priority)
    try:
        from apps.analytics.models import FingerprintBlock

        blocked_fingerprint = FingerprintBlock.objects.filter(
            fingerprint=fingerprint, is_active=True
        ).first()

        if blocked_fingerprint:
            return {
                "suspicious": True,
                "reasons": [
                    f"Fingerprint is permanently blocked: {blocked_fingerprint.reason}"
                ],
                "risk_score": 100,
                "block_vote": True,
            }
    except Exception as e:
        logger.error(f"Error checking blocked fingerprints: {e}")
        # Continue with validation if check fails

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
                block_vote = True  # Critical: block vote and mark for permanent blocking
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
                        block_vote = True  # Critical: block vote and mark for permanent blocking

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
                # Convert to list to support negative indexing
                recent_votes_list = list(recent_votes)
                first_vote_time = recent_votes_list[-1]["created_at"]
                last_vote_time = recent_votes_list[0]["created_at"]
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

    result = {
        "suspicious": len(reasons) > 0,
        "reasons": reasons,
        "risk_score": min(risk_score, 100),
        "block_vote": block_vote,
    }

    # If vote is blocked due to critical suspicious pattern, mark fingerprint for permanent blocking
    if block_vote and "different users" in " ".join(reasons).lower():
        try:
            block_fingerprint_permanently(
                fingerprint=fingerprint,
                reason=", ".join(reasons),
                user_id=user_id,
                poll_id=poll_id,
            )
        except Exception as e:
            logger.error(f"Error blocking fingerprint permanently: {e}")
            # Don't fail validation if blocking fails

    return result


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


def block_fingerprint_permanently(
    fingerprint: str,
    reason: str,
    user_id: int,
    poll_id: int = None,
):
    """
    Permanently block a fingerprint due to suspicious activity.

    Args:
        fingerprint: Browser fingerprint hash to block
        reason: Reason for blocking
        user_id: User ID who triggered the block
        poll_id: Poll ID (optional)
    """
    if not fingerprint:
        return

    try:
        from apps.analytics.models import FingerprintBlock
        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        # Check if already blocked
        existing_block = FingerprintBlock.objects.filter(
            fingerprint=fingerprint, is_active=True
        ).first()

        if existing_block:
            # Already blocked, no need to create another
            return

        # Get statistics about this fingerprint
        user = User.objects.filter(id=user_id).first()
        fingerprint_votes = Vote.objects.filter(fingerprint=fingerprint)
        distinct_users = fingerprint_votes.values_list("user_id", flat=True).distinct()
        total_votes = fingerprint_votes.count()
        first_user = fingerprint_votes.order_by("created_at").first()

        # Create permanent block
        FingerprintBlock.objects.create(
            fingerprint=fingerprint,
            reason=reason,
            blocked_by=None,  # Auto-blocked by system
            first_seen_user=first_user.user if first_user else user,
            total_users=len(distinct_users),
            total_votes=total_votes,
        )

        logger.warning(
            f"Fingerprint {fingerprint[:16]}... permanently blocked. Reason: {reason}"
        )

    except Exception as e:
        logger.error(f"Error creating fingerprint block: {e}")
        # Don't fail if blocking fails

