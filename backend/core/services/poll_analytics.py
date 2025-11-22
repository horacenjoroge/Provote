"""
Comprehensive poll analytics service.
Calculates various metrics for poll performance analysis.
"""

import logging

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from django.db.models import Count
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_total_votes_over_time(
    poll_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    interval: str = "hour",
) -> List[Dict]:
    """
    Get total votes over time as a time series.

    Args:
        poll_id: Poll ID
        start_date: Start date for time series (default: poll start)
        end_date: End date for time series (default: now)
        interval: Time interval ('hour' or 'day')

    Returns:
        List of dicts: [{"timestamp": datetime, "count": int}, ...]
    """
    from apps.polls.models import Poll
    from apps.votes.models import Vote

    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        return []

    # Default to poll start/end dates
    if start_date is None:
        start_date = poll.starts_at
    if end_date is None:
        end_date = timezone.now()

    # Filter valid votes only
    votes = Vote.objects.filter(
        poll_id=poll_id,
        created_at__gte=start_date,
        created_at__lte=end_date,
        is_valid=True,
    )

    # Truncate by interval
    if interval == "hour":
        trunc_func = TruncHour("created_at")
    elif interval == "day":
        trunc_func = TruncDate("created_at")
    else:
        trunc_func = TruncHour("created_at")

    # Aggregate by time interval
    time_series = (
        votes.annotate(time_bucket=trunc_func)
        .values("time_bucket")
        .annotate(count=Count("id"))
        .order_by("time_bucket")
    )

    return [
        {"timestamp": item["time_bucket"], "count": item["count"]}
        for item in time_series
    ]


def get_votes_by_hour(poll_id: int, date: Optional[datetime] = None) -> List[Dict]:
    """
    Get votes grouped by hour for a specific day.

    Args:
        poll_id: Poll ID
        date: Date to analyze (default: today)

    Returns:
        List of dicts: [{"hour": int, "count": int}, ...]
    """
    from apps.votes.models import Vote

    if date is None:
        date = timezone.now()

    start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    votes = Vote.objects.filter(
        poll_id=poll_id,
        created_at__gte=start_of_day,
        created_at__lt=end_of_day,
        is_valid=True,
    )

    hourly_counts = (
        votes.annotate(hour=TruncHour("created_at"))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("hour")
    )

    # Format as hour (0-23) and count
    result = []
    for item in hourly_counts:
        hour = (
            item["hour"].hour
            if hasattr(item["hour"], "hour")
            else item["hour"].time().hour
        )
        result.append({"hour": hour, "count": item["count"]})

    return result


def get_votes_by_day(poll_id: int, days: int = 30) -> List[Dict]:
    """
    Get votes grouped by day for the last N days.

    Args:
        poll_id: Poll ID
        days: Number of days to analyze (default: 30)

    Returns:
        List of dicts: [{"date": date, "count": int}, ...]
    """
    from apps.votes.models import Vote

    start_date = timezone.now() - timedelta(days=days)

    votes = Vote.objects.filter(
        poll_id=poll_id,
        created_at__gte=start_date,
        is_valid=True,
    )

    daily_counts = (
        votes.annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )

    return [{"date": item["date"], "count": item["count"]} for item in daily_counts]


def get_voter_demographics(poll_id: int) -> Dict:
    """
    Get voter demographics if available.

    Currently tracks:
    - Authenticated vs anonymous voters
    - Unique IP addresses
    - Geographic distribution (if IP geolocation available)

    Args:
        poll_id: Poll ID

    Returns:
        dict: Demographics data
    """
    from apps.votes.models import Vote

    votes = Vote.objects.filter(poll_id=poll_id, is_valid=True)

    # Authenticated vs anonymous
    authenticated_count = (
        votes.exclude(user__isnull=True).values("user").distinct().count()
    )
    anonymous_count = votes.filter(user__isnull=True).count()

    # Unique IPs
    unique_ips = (
        votes.exclude(ip_address__isnull=True).values("ip_address").distinct().count()
    )

    # User agent distribution (top 5)
    user_agents = (
        votes.exclude(user_agent="")
        .values("user_agent")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    return {
        "authenticated_voters": authenticated_count,
        "anonymous_voters": anonymous_count,
        "unique_ip_addresses": unique_ips,
        "top_user_agents": [
            {"user_agent": ua["user_agent"][:100], "count": ua["count"]}
            for ua in user_agents
        ],
    }


def get_participation_rate(poll_id: int) -> Dict:
    """
    Calculate participation rate.

    Participation rate = (unique voters / total potential voters) * 100

    For now, we use unique voters as the numerator.
    Denominator would need to be tracked separately (e.g., poll views).

    Args:
        poll_id: Poll ID

    Returns:
        dict: Participation metrics
    """
    from apps.polls.models import Poll
    from apps.votes.models import Vote

    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        return {
            "participation_rate": 0,
            "unique_voters": 0,
            "total_potential_voters": 0,
        }

    # Get unique voters
    unique_voters = (
        Vote.objects.filter(poll_id=poll_id, is_valid=True)
        .values("user", "voter_token")
        .distinct()
        .count()
    )

    # For now, we can't calculate true participation rate without view tracking
    # This would require a separate PollView model
    # For now, return what we can calculate
    return {
        "participation_rate": None,  # Requires view tracking
        "unique_voters": unique_voters,
        "total_votes": poll.cached_total_votes,
        "note": "Participation rate requires view tracking to be implemented",
    }


def get_average_time_to_vote(poll_id: int) -> Optional[float]:
    """
    Calculate average time to vote.

    Time to vote = time between poll start and vote creation.

    Args:
        poll_id: Poll ID

    Returns:
        Average time in seconds, or None if no votes
    """
    from apps.polls.models import Poll
    from apps.votes.models import Vote

    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        return None

    votes = Vote.objects.filter(poll_id=poll_id, is_valid=True)

    if not votes.exists():
        return None

    # Calculate time difference for each vote
    time_diffs = []
    for vote in votes:
        time_diff = (vote.created_at - poll.starts_at).total_seconds()
        if time_diff >= 0:  # Only count votes after poll started
            time_diffs.append(time_diff)

    if not time_diffs:
        return None

    return sum(time_diffs) / len(time_diffs)


def get_drop_off_rate(poll_id: int) -> Dict:
    """
    Calculate drop-off rate (viewed but didn't vote).

    Drop-off rate = (views - votes) / views * 100

    This requires tracking poll views separately.
    For now, we can use VoteAttempt to estimate.

    Args:
        poll_id: Poll ID

    Returns:
        dict: Drop-off metrics
    """
    from apps.votes.models import Vote, VoteAttempt

    # Get successful votes
    successful_votes = Vote.objects.filter(poll_id=poll_id, is_valid=True).count()

    # Get all vote attempts (including failed)
    total_attempts = VoteAttempt.objects.filter(poll_id=poll_id).count()

    # Failed attempts = drop-offs
    failed_attempts = VoteAttempt.objects.filter(poll_id=poll_id, success=False).count()

    # Calculate drop-off rate
    if total_attempts > 0:
        drop_off_rate = (failed_attempts / total_attempts) * 100
    else:
        drop_off_rate = 0

    return {
        "drop_off_rate": round(drop_off_rate, 2),
        "total_attempts": total_attempts,
        "successful_votes": successful_votes,
        "failed_attempts": failed_attempts,
        "note": "Based on vote attempts. True drop-off rate requires view tracking.",
    }


def get_vote_distribution(poll_id: int) -> List[Dict]:
    """
    Get vote distribution across options.

    Args:
        poll_id: Poll ID

    Returns:
        List of dicts: [{"option_id": int, "option_text": str, "vote_count": int, "percentage": float}, ...]
    """
    from apps.polls.models import PollOption
    from apps.votes.models import Vote

    # Get all options for the poll
    options = PollOption.objects.filter(poll_id=poll_id).order_by("order", "id")

    # Get total valid votes
    total_votes = Vote.objects.filter(poll_id=poll_id, is_valid=True).count()

    distribution = []
    for option in options:
        vote_count = Vote.objects.filter(
            poll_id=poll_id, option_id=option.id, is_valid=True
        ).count()

        percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0

        distribution.append(
            {
                "option_id": option.id,
                "option_text": option.text,
                "vote_count": vote_count,
                "percentage": round(percentage, 2),
            }
        )

    return distribution


def get_comprehensive_analytics(poll_id: int) -> Dict:
    """
    Get comprehensive analytics for a poll.

    Combines all analytics metrics into a single response.

    Args:
        poll_id: Poll ID

    Returns:
        dict: Complete analytics data
    """
    from apps.polls.models import Poll

    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        return {"error": "Poll not found"}

    # Calculate all metrics
    analytics = {
        "poll_id": poll_id,
        "poll_title": poll.title,
        "generated_at": timezone.now().isoformat(),
        "total_votes": poll.cached_total_votes,
        "unique_voters": poll.cached_unique_voters,
        "time_series": {
            "hourly": get_votes_by_hour(poll_id),
            "daily": get_votes_by_day(poll_id, days=30),
            "over_time": get_total_votes_over_time(poll_id, interval="hour"),
        },
        "demographics": get_voter_demographics(poll_id),
        "participation": get_participation_rate(poll_id),
        "average_time_to_vote_seconds": get_average_time_to_vote(poll_id),
        "drop_off_rate": get_drop_off_rate(poll_id),
        "vote_distribution": get_vote_distribution(poll_id),
        "poll_metadata": {
            "created_at": poll.created_at.isoformat(),
            "starts_at": poll.starts_at.isoformat(),
            "ends_at": poll.ends_at.isoformat() if poll.ends_at else None,
            "is_active": poll.is_active,
            "is_open": poll.is_open,
        },
    }

    return analytics


def get_analytics_summary(poll_id: int) -> Dict:
    """
    Get a summary of key analytics metrics.

    Lightweight version for quick overview.

    Args:
        poll_id: Poll ID

    Returns:
        dict: Summary metrics
    """
    from apps.polls.models import Poll

    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        return {"error": "Poll not found"}

    distribution = get_vote_distribution(poll_id)
    avg_time = get_average_time_to_vote(poll_id)

    return {
        "poll_id": poll_id,
        "poll_title": poll.title,
        "total_votes": poll.cached_total_votes,
        "unique_voters": poll.cached_unique_voters,
        "average_time_to_vote_seconds": avg_time,
        "top_option": max(distribution, key=lambda x: x["vote_count"])
        if distribution
        else None,
        "vote_distribution": distribution,
    }
