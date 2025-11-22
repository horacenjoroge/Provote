"""
Basic fraud detection utilities for voting system.
Detects suspicious voting patterns and marks votes as invalid.
"""

import logging
import re
from datetime import timedelta
from typing import Dict, List, Optional



from django.db.models import Count
from django.utils import timezone

logger = logging.getLogger(__name__)

# Bot user agent patterns
BOT_USER_AGENTS = [
    r"bot",
    r"crawler",
    r"spider",
    r"scraper",
    r"curl",
    r"wget",
    r"python-requests",
    r"go-http-client",
    r"java/",
    r"apache-httpclient",
    r"postman",
    r"insomnia",
    r"httpie",
    r"^$",  # Empty user agent
]

# Suspicious user agent patterns (case-insensitive)
SUSPICIOUS_USER_AGENTS = [
    r"^$",  # Empty
    r"^Mozilla$",  # Too generic
    r"^curl",  # Command line tool
    r"^wget",  # Command line tool
    r"^python",  # Script
    r"^go-http",  # Script
    r"^java",  # Script
]


def detect_fraud(
    poll_id: int,
    option_id: int,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    fingerprint: Optional[str] = None,
    request=None,
) -> Dict:
    """
    Detect fraud patterns in a vote attempt.

    Args:
        poll_id: Poll ID
        option_id: Option ID being voted for
        user_id: User ID (if authenticated)
        ip_address: IP address of voter
        user_agent: User agent string
        fingerprint: Browser fingerprint
        request: Django request object (optional)

    Returns:
        dict: {
            "is_fraud": bool,
            "reasons": List[str],
            "risk_score": int (0-100),
            "should_mark_invalid": bool
        }
    """
    reasons = []
    risk_score = 0
    should_mark_invalid = False

    # Rule 1: Multiple votes from same IP in short time
    if ip_address:
        rapid_votes = check_rapid_votes_from_ip(poll_id, ip_address)
        if rapid_votes["suspicious"]:
            reasons.extend(rapid_votes["reasons"])
            risk_score += rapid_votes["risk_score"]
            if rapid_votes["should_block"]:
                should_mark_invalid = True

    # Rule 2: Suspicious voting patterns (all votes to one option)
    if ip_address or user_id:
        suspicious_pattern = check_suspicious_voting_pattern(
            poll_id, ip_address, user_id
        )
        if suspicious_pattern["suspicious"]:
            reasons.extend(suspicious_pattern["reasons"])
            risk_score += suspicious_pattern["risk_score"]
            if suspicious_pattern["should_block"]:
                should_mark_invalid = True

    # Rule 3: Missing/invalid fingerprints
    fingerprint_check = check_fingerprint_validity(fingerprint)
    if fingerprint_check["suspicious"]:
        reasons.extend(fingerprint_check["reasons"])
        risk_score += fingerprint_check["risk_score"]
        # Missing fingerprint is suspicious but not necessarily fraud
        if fingerprint_check["should_block"]:
            should_mark_invalid = True

    # Rule 4: Suspicious user agents (bots)
    if user_agent:
        bot_check = check_bot_user_agent(user_agent)
        if bot_check["suspicious"]:
            reasons.extend(bot_check["reasons"])
            risk_score += bot_check["risk_score"]
            if bot_check["should_block"]:
                should_mark_invalid = True

    # Rule 5: Votes outside normal hours (for certain polls)
    if request:
        hours_check = check_voting_hours(poll_id, request)
        if hours_check["suspicious"]:
            reasons.extend(hours_check["reasons"])
            risk_score += hours_check["risk_score"]
            if hours_check["should_block"]:
                should_mark_invalid = True

    is_fraud = should_mark_invalid or risk_score >= 70

    return {
        "is_fraud": is_fraud,
        "reasons": reasons,
        "risk_score": min(risk_score, 100),
        "should_mark_invalid": should_mark_invalid or is_fraud,
    }


def check_rapid_votes_from_ip(
    poll_id: int, ip_address: str, time_window_minutes: int = 5, max_votes: int = 3
) -> Dict:
    """
    Check for multiple votes from same IP in short time.

    Args:
        poll_id: Poll ID
        ip_address: IP address to check
        time_window_minutes: Time window in minutes
        max_votes: Maximum votes allowed in time window

    Returns:
        dict: Detection result
    """
    from apps.votes.models import Vote

    cutoff = timezone.now() - timedelta(minutes=time_window_minutes)

    # Count recent votes from this IP
    recent_vote_count = Vote.objects.filter(
        poll_id=poll_id,
        ip_address=ip_address,
        created_at__gte=cutoff,
    ).count()

    if recent_vote_count >= max_votes:
        return {
            "suspicious": True,
            "reasons": [
                f"Multiple votes ({recent_vote_count}) from same IP ({ip_address}) in {time_window_minutes} minutes"
            ],
            "risk_score": 50,
            "should_block": True,
        }

    return {"suspicious": False, "reasons": [], "risk_score": 0, "should_block": False}


def check_suspicious_voting_pattern(
    poll_id: int, ip_address: Optional[str] = None, user_id: Optional[int] = None
) -> Dict:
    """
    Check for suspicious voting patterns (all votes to one option).

    Args:
        poll_id: Poll ID
        ip_address: IP address to check (optional)
        user_id: User ID to check (optional)

    Returns:
        dict: Detection result
    """
    from apps.polls.models import Poll, PollOption
    from apps.votes.models import Vote

    try:
        poll = Poll.objects.get(id=poll_id)
        options = PollOption.objects.filter(poll=poll)
        option_count = options.count()

        if option_count < 2:
            return {
                "suspicious": False,
                "reasons": [],
                "risk_score": 0,
                "should_block": False,
            }

        # Check votes from this IP or user
        vote_filter = {"poll_id": poll_id}
        if ip_address:
            vote_filter["ip_address"] = ip_address
        if user_id:
            vote_filter["user_id"] = user_id

        votes = (
            Vote.objects.filter(**vote_filter)
            .values("option_id")
            .annotate(count=Count("id"))
        )

        if not votes:
            return {
                "suspicious": False,
                "reasons": [],
                "risk_score": 0,
                "should_block": False,
            }

        # Check if all votes go to one option
        if len(votes) == 1:
            vote_count = votes[0]["count"]
            if vote_count >= 5:  # Threshold for suspicious pattern
                return {
                    "suspicious": True,
                    "reasons": [
                        f"All {vote_count} votes from {'IP' if ip_address else 'user'} go to single option"
                    ],
                    "risk_score": 40,
                    "should_block": vote_count >= 10,  # Block if very suspicious
                }

    except Exception as e:
        logger.error(f"Error checking suspicious voting pattern: {e}")

    return {"suspicious": False, "reasons": [], "risk_score": 0, "should_block": False}


def check_fingerprint_validity(fingerprint: Optional[str]) -> Dict:
    """
    Check if fingerprint is missing or invalid.

    Args:
        fingerprint: Browser fingerprint

    Returns:
        dict: Detection result
    """
    if not fingerprint:
        return {
            "suspicious": True,
            "reasons": ["Missing browser fingerprint"],
            "risk_score": 20,
            "should_block": False,  # Don't block, just mark suspicious
        }

    # Check if fingerprint is too short or invalid format
    if len(fingerprint) < 32:  # SHA256 should be 64 chars
        return {
            "suspicious": True,
            "reasons": ["Invalid fingerprint format (too short)"],
            "risk_score": 30,
            "should_block": True,
        }

    # Check if fingerprint is valid hex
    try:
        int(fingerprint, 16)
    except ValueError:
        return {
            "suspicious": True,
            "reasons": ["Invalid fingerprint format (not hexadecimal)"],
            "risk_score": 30,
            "should_block": True,
        }

    return {"suspicious": False, "reasons": [], "risk_score": 0, "should_block": False}


def check_bot_user_agent(user_agent: str) -> Dict:
    """
    Check if user agent indicates a bot.

    Args:
        user_agent: User agent string

    Returns:
        dict: Detection result
    """
    if not user_agent:
        return {
            "suspicious": True,
            "reasons": ["Missing user agent"],
            "risk_score": 40,
            "should_block": True,
        }

    user_agent_lower = user_agent.lower()

    # Check against bot patterns
    for pattern in BOT_USER_AGENTS:
        if re.search(pattern, user_agent_lower, re.IGNORECASE):
            return {
                "suspicious": True,
                "reasons": [f"Bot user agent detected: {user_agent[:50]}"],
                "risk_score": 60,
                "should_block": True,
            }

    # Check against suspicious patterns
    for pattern in SUSPICIOUS_USER_AGENTS:
        if re.match(pattern, user_agent, re.IGNORECASE):
            return {
                "suspicious": True,
                "reasons": [f"Suspicious user agent: {user_agent[:50]}"],
                "risk_score": 30,
                "should_block": False,  # Mark suspicious but don't block
            }

    return {"suspicious": False, "reasons": [], "risk_score": 0, "should_block": False}


def check_voting_hours(poll_id: int, request) -> Dict:
    """
    Check if vote is outside normal hours (for certain polls).

    Args:
        poll_id: Poll ID
        request: Django request object

    Returns:
        dict: Detection result
    """
    from apps.polls.models import Poll

    try:
        poll = Poll.objects.get(id=poll_id)

        # Check if poll has voting hours restriction
        voting_hours = poll.settings.get("voting_hours", None)
        if not voting_hours:
            return {
                "suspicious": False,
                "reasons": [],
                "risk_score": 0,
                "should_block": False,
            }

        # Get current time
        now = timezone.now()
        current_hour = now.hour

        # Check if current hour is within allowed hours
        allowed_hours = voting_hours.get("allowed_hours", [])
        if allowed_hours and current_hour not in allowed_hours:
            return {
                "suspicious": True,
                "reasons": [
                    f"Vote outside allowed hours. Current hour: {current_hour}"
                ],
                "risk_score": 25,
                "should_block": voting_hours.get(
                    "strict", False
                ),  # Block if strict mode
            }

    except Exception as e:
        logger.error(f"Error checking voting hours: {e}")

    return {"suspicious": False, "reasons": [], "risk_score": 0, "should_block": False}


def log_fraud_alert(
    vote_id: int,
    reasons: List[str],
    risk_score: int,
    poll_id: int,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
):
    """
    Log fraud alert for investigation.

    Args:
        vote_id: Vote ID
        reasons: List of fraud reasons
        risk_score: Risk score (0-100)
        poll_id: Poll ID
        user_id: User ID (optional)
        ip_address: IP address (optional)
    """
    try:
        from apps.analytics.models import FraudAlert
        from apps.polls.models import Poll
        from apps.votes.models import Vote
        from django.contrib.auth.models import User

        vote = Vote.objects.get(id=vote_id)
        poll = Poll.objects.get(id=poll_id)
        user = User.objects.get(id=user_id) if user_id else None

        FraudAlert.objects.create(
            vote=vote,
            poll=poll,
            user=user,
            ip_address=ip_address,
            reasons=", ".join(reasons),
            risk_score=risk_score,
        )
    except Exception as e:
        logger.error(f"Error logging fraud alert: {e}")
