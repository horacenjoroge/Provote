"""
Vote pattern analysis for detecting suspicious voting patterns.
Analyzes votes in batches to detect coordinated attacks and fraud patterns.
"""

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Dict, List, Optional

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

logger = logging.getLogger(__name__)


def detect_single_ip_single_option_pattern(
    poll_id: int, time_window_hours: int = 24
) -> List[Dict]:
    """
    Detect pattern where all votes from one IP go to the same option.

    This is a strong indicator of bot activity or vote manipulation.

    Args:
        poll_id: Poll ID to analyze
        time_window_hours: Time window to analyze (default: 24 hours)

    Returns:
        List of dicts with pattern details:
        {
            "ip_address": str,
            "option_id": int,
            "vote_count": int,
            "risk_score": int,
            "pattern_type": str
        }
    """
    from apps.votes.models import Vote

    cutoff = timezone.now() - timedelta(hours=time_window_hours)

    # Get all votes in time window
    votes = (
        Vote.objects.filter(
            poll_id=poll_id,
            created_at__gte=cutoff,
            ip_address__isnull=False,
        )
        .values("ip_address", "option_id")
        .annotate(vote_count=Count("id"))
        .order_by("-vote_count")
    )

    suspicious_patterns = []

    # Group by IP and check if all votes go to one option
    ip_votes = defaultdict(dict)
    for vote in votes:
        ip = vote["ip_address"]
        option_id = vote["option_id"]
        count = vote["vote_count"]

        if ip not in ip_votes:
            ip_votes[ip] = {}

        ip_votes[ip][option_id] = count

    # Check each IP
    for ip, options in ip_votes.items():
        if len(options) == 1:  # All votes to one option
            option_id = list(options.keys())[0]
            vote_count = list(options.values())[0]

            # Only flag if significant number of votes
            if vote_count >= getattr(settings, "PATTERN_ANALYSIS_MIN_VOTES", 5):
                risk_score = min(50 + (vote_count * 5), 100)

                suspicious_patterns.append(
                    {
                        "ip_address": ip,
                        "option_id": option_id,
                        "vote_count": vote_count,
                        "risk_score": risk_score,
                        "pattern_type": "single_ip_single_option",
                    }
                )

    return suspicious_patterns


def detect_time_clustered_votes(
    poll_id: int, cluster_window_seconds: int = 60, min_votes_in_cluster: int = 10
) -> List[Dict]:
    """
    Detect votes clustered in time (bot attack pattern).

    Bot attacks often show votes arriving in rapid succession.

    Args:
        poll_id: Poll ID to analyze
        cluster_window_seconds: Time window for clustering (default: 60 seconds)
        min_votes_in_cluster: Minimum votes to consider suspicious (default: 10)

    Returns:
        List of dicts with cluster details:
        {
            "start_time": datetime,
            "end_time": datetime,
            "vote_count": int,
            "unique_ips": int,
            "risk_score": int,
            "pattern_type": str
        }
    """
    from apps.votes.models import Vote

    # Analyze last 24 hours
    cutoff = timezone.now() - timedelta(hours=24)

    votes = (
        Vote.objects.filter(
            poll_id=poll_id,
            created_at__gte=cutoff,
        )
        .order_by("created_at")
        .values("id", "created_at", "ip_address")
    )

    if not votes:
        return []

    suspicious_clusters = []
    current_cluster = []
    cluster_start = None

    for vote in votes:
        vote_time = vote["created_at"]

        if not current_cluster:
            # Start new cluster
            current_cluster = [vote]
            cluster_start = vote_time
        else:
            # Check if vote is within cluster window
            time_diff = (vote_time - cluster_start).total_seconds()

            if time_diff <= cluster_window_seconds:
                current_cluster.append(vote)
            else:
                # Cluster ended, check if suspicious
                if len(current_cluster) >= min_votes_in_cluster:
                    unique_ips = len(
                        set(v["ip_address"] for v in current_cluster if v["ip_address"])
                    )
                    cluster_end = current_cluster[-1]["created_at"]

                    # Calculate risk score
                    risk_score = min(40 + (len(current_cluster) * 2), 100)
                    if unique_ips == 1:
                        risk_score += 20  # Same IP makes it more suspicious

                    suspicious_clusters.append(
                        {
                            "start_time": cluster_start,
                            "end_time": cluster_end,
                            "vote_count": len(current_cluster),
                            "unique_ips": unique_ips,
                            "risk_score": min(risk_score, 100),
                            "pattern_type": "time_clustered",
                        }
                    )

                # Start new cluster
                current_cluster = [vote]
                cluster_start = vote_time

    # Check last cluster
    if len(current_cluster) >= min_votes_in_cluster:
        unique_ips = len(
            set(v["ip_address"] for v in current_cluster if v["ip_address"])
        )
        cluster_end = current_cluster[-1]["created_at"]

        risk_score = min(40 + (len(current_cluster) * 2), 100)
        if unique_ips == 1:
            risk_score += 20

        suspicious_clusters.append(
            {
                "start_time": cluster_start,
                "end_time": cluster_end,
                "vote_count": len(current_cluster),
                "unique_ips": unique_ips,
                "risk_score": min(risk_score, 100),
                "pattern_type": "time_clustered",
            }
        )

    return suspicious_clusters


def detect_geographic_anomalies(
    poll_id: int, time_window_hours: int = 24
) -> List[Dict]:
    """
    Detect geographic anomalies (votes from impossible locations).

    This requires IP geolocation data. For now, we'll detect:
    - Votes from IPs that change location too quickly (impossible travel)
    - Votes from known VPN/proxy IP ranges (if configured)

    Args:
        poll_id: Poll ID to analyze
        time_window_hours: Time window to analyze (default: 24 hours)

    Returns:
        List of dicts with anomaly details:
        {
            "ip_address": str,
            "anomaly_type": str,
            "details": str,
            "risk_score": int,
            "pattern_type": str
        }
    """
    from apps.votes.models import Vote

    cutoff = timezone.now() - timedelta(hours=time_window_hours)

    # Get votes with IP addresses
    votes = (
        Vote.objects.filter(
            poll_id=poll_id,
            created_at__gte=cutoff,
            ip_address__isnull=False,
        )
        .order_by("ip_address", "created_at")
        .values("id", "ip_address", "created_at", "user_id")
    )

    if not votes:
        return []

    anomalies = []

    # Group votes by user to detect impossible travel
    user_votes = defaultdict(list)
    for vote in votes:
        if vote["user_id"]:
            user_votes[vote["user_id"]].append(vote)

    # Check for impossible travel (same user, different IPs in short time)
    for user_id, user_vote_list in user_votes.items():
        if len(user_vote_list) < 2:
            continue

        # Sort by time
        user_vote_list.sort(key=lambda x: x["created_at"])

        # Check for rapid IP changes
        for i in range(1, len(user_vote_list)):
            prev_vote = user_vote_list[i - 1]
            curr_vote = user_vote_list[i]

            time_diff = (
                curr_vote["created_at"] - prev_vote["created_at"]
            ).total_seconds()

            # If IP changed and time difference is very short (< 1 minute)
            if prev_vote["ip_address"] != curr_vote["ip_address"] and time_diff < 60:
                anomalies.append(
                    {
                        "ip_address": curr_vote["ip_address"],
                        "anomaly_type": "impossible_travel",
                        "details": f"User {user_id} changed IP from {prev_vote['ip_address']} to {curr_vote['ip_address']} in {time_diff:.1f} seconds",
                        "risk_score": 70,
                        "pattern_type": "geographic_anomaly",
                    }
                )

    # Check for VPN/proxy patterns (if configured)
    vpn_proxy_ips = getattr(settings, "VPN_PROXY_IP_RANGES", [])
    if vpn_proxy_ips:
        # Simple check - in production, use proper IP range matching
        for vote in votes:
            ip = vote["ip_address"]
            # This is a simplified check - in production, use proper IP range library
            if any(
                ip.startswith(prefix)
                for prefix in vpn_proxy_ips
                if isinstance(prefix, str)
            ):
                anomalies.append(
                    {
                        "ip_address": ip,
                        "anomaly_type": "vpn_proxy",
                        "details": f"IP {ip} matches known VPN/proxy pattern",
                        "risk_score": 30,
                        "pattern_type": "geographic_anomaly",
                    }
                )

    return anomalies


def detect_user_agent_anomalies(
    poll_id: int, time_window_hours: int = 24, min_voters_threshold: int = 10
) -> List[Dict]:
    """
    Detect user agent anomalies (same UA across many voters).

    Legitimate users typically have diverse user agents.
    Bot attacks often use the same or very similar user agents.

    Args:
        poll_id: Poll ID to analyze
        time_window_hours: Time window to analyze (default: 24 hours)
        min_voters_threshold: Minimum unique voters to flag (default: 10)

    Returns:
        List of dicts with anomaly details:
        {
            "user_agent": str,
            "unique_voters": int,
            "vote_count": int,
            "risk_score": int,
            "pattern_type": str
        }
    """
    from apps.votes.models import Vote

    cutoff = timezone.now() - timedelta(hours=time_window_hours)

    # Get votes with user agents
    votes = (
        Vote.objects.filter(
            poll_id=poll_id,
            created_at__gte=cutoff,
            user_agent__isnull=False,
        )
        .exclude(user_agent="")
        .values("user_agent", "user_id", "ip_address")
    )

    if not votes:
        return []

    # Group by user agent
    ua_stats = defaultdict(lambda: {"voters": set(), "votes": 0, "ips": set()})

    for vote in votes:
        ua = vote["user_agent"]
        ua_stats[ua]["votes"] += 1
        if vote["user_id"]:
            ua_stats[ua]["voters"].add(vote["user_id"])
        if vote["ip_address"]:
            ua_stats[ua]["ips"].add(vote["ip_address"])

    anomalies = []

    for ua, stats in ua_stats.items():
        unique_voters = len(stats["voters"])
        unique_ips = len(stats["ips"])
        vote_count = stats["votes"]

        # Flag if same UA used by many voters/IPs
        if unique_voters >= min_voters_threshold or unique_ips >= min_voters_threshold:
            # Calculate risk score
            risk_score = min(30 + (unique_voters * 2) + (unique_ips * 2), 100)

            # Higher risk if same UA from same IP (bot pattern)
            if unique_ips == 1 and vote_count >= 10:
                risk_score += 30

            anomalies.append(
                {
                    "user_agent": ua[:100],  # Truncate for storage
                    "unique_voters": unique_voters,
                    "unique_ips": unique_ips,
                    "vote_count": vote_count,
                    "risk_score": min(risk_score, 100),
                    "pattern_type": "user_agent_anomaly",
                }
            )

    return anomalies


def analyze_vote_patterns(
    poll_id: Optional[int] = None, time_window_hours: int = 24
) -> Dict:
    """
    Comprehensive pattern analysis for votes.

    Analyzes all suspicious patterns and returns aggregated results.

    Args:
        poll_id: Poll ID to analyze (None for all polls)
        time_window_hours: Time window to analyze (default: 24 hours)

    Returns:
        dict: {
            "poll_id": int or None,
            "analysis_timestamp": datetime,
            "patterns_detected": {
                "single_ip_single_option": List[Dict],
                "time_clustered": List[Dict],
                "geographic_anomalies": List[Dict],
                "user_agent_anomalies": List[Dict],
            },
            "total_suspicious_patterns": int,
            "highest_risk_score": int,
            "alerts_generated": int,
        }
    """
    from apps.polls.models import Poll

    analysis_start = timezone.now()

    # Get polls to analyze
    if poll_id:
        polls = Poll.objects.filter(id=poll_id, is_active=True)
    else:
        polls = Poll.objects.filter(is_active=True)

    all_patterns = {
        "single_ip_single_option": [],
        "time_clustered": [],
        "geographic_anomalies": [],
        "user_agent_anomalies": [],
    }

    total_alerts = 0

    for poll in polls:
        # Detect each pattern type
        single_ip_patterns = detect_single_ip_single_option_pattern(
            poll.id, time_window_hours
        )
        all_patterns["single_ip_single_option"].extend(single_ip_patterns)

        time_clusters = detect_time_clustered_votes(poll.id)
        all_patterns["time_clustered"].extend(time_clusters)

        geo_anomalies = detect_geographic_anomalies(poll.id, time_window_hours)
        all_patterns["geographic_anomalies"].extend(geo_anomalies)

        ua_anomalies = detect_user_agent_anomalies(poll.id, time_window_hours)
        all_patterns["user_agent_anomalies"].extend(ua_anomalies)

        # Generate alerts for high-risk patterns
        alerts = generate_pattern_alerts(poll.id, all_patterns)
        total_alerts += len(alerts)

    # Calculate summary statistics
    all_pattern_list = (
        all_patterns["single_ip_single_option"]
        + all_patterns["time_clustered"]
        + all_patterns["geographic_anomalies"]
        + all_patterns["user_agent_anomalies"]
    )

    total_patterns = len(all_pattern_list)
    highest_risk = max((p.get("risk_score", 0) for p in all_pattern_list), default=0)

    return {
        "poll_id": poll_id,
        "analysis_timestamp": analysis_start,
        "patterns_detected": all_patterns,
        "total_suspicious_patterns": total_patterns,
        "highest_risk_score": highest_risk,
        "alerts_generated": total_alerts,
    }


def generate_pattern_alerts(poll_id: int, patterns: Dict) -> List[Dict]:
    """
    Generate fraud alerts for detected patterns.

    Args:
        poll_id: Poll ID
        patterns: Dictionary of detected patterns

    Returns:
        List of alert dictionaries
    """
    from apps.analytics.models import FraudAlert
    from apps.votes.models import Vote

    alerts = []

    # Process single IP single option patterns
    for pattern in patterns.get("single_ip_single_option", []):
        if pattern["risk_score"] >= 60:  # Only high-risk patterns
            # Find votes matching this pattern
            cutoff = timezone.now() - timedelta(hours=24)
            votes = Vote.objects.filter(
                poll_id=poll_id,
                ip_address=pattern["ip_address"],
                option_id=pattern["option_id"],
                created_at__gte=cutoff,
            )[
                :10
            ]  # Limit to first 10 votes

            for vote in votes:
                try:
                    FraudAlert.objects.get_or_create(
                        vote=vote,
                        defaults={
                            "poll_id": poll_id,
                            "user": vote.user,
                            "ip_address": pattern["ip_address"],
                            "reasons": (
                                f"Single IP single option pattern: "
                                f"{pattern['vote_count']} votes from {pattern['ip_address']} "
                                f"all go to option {pattern['option_id']}"
                            ),
                            "risk_score": pattern["risk_score"],
                        },
                    )
                    alerts.append(
                        {
                            "vote_id": vote.id,
                            "pattern_type": pattern["pattern_type"],
                            "risk_score": pattern["risk_score"],
                        }
                    )
                except Exception as e:
                    logger.error(f"Error creating fraud alert: {e}")

    # Process time clustered patterns
    for pattern in patterns.get("time_clustered", []):
        if pattern["risk_score"] >= 60:
            # Find votes in this time cluster
            votes = Vote.objects.filter(
                poll_id=poll_id,
                created_at__gte=pattern["start_time"],
                created_at__lte=pattern["end_time"],
            )[:10]

            for vote in votes:
                try:
                    FraudAlert.objects.get_or_create(
                        vote=vote,
                        defaults={
                            "poll_id": poll_id,
                            "user": vote.user,
                            "ip_address": vote.ip_address,
                            "reasons": (
                                f"Time clustered votes: {pattern['vote_count']} votes "
                                f"in {pattern['end_time'] - pattern['start_time']} seconds"
                            ),
                            "risk_score": pattern["risk_score"],
                        },
                    )
                    alerts.append(
                        {
                            "vote_id": vote.id,
                            "pattern_type": pattern["pattern_type"],
                            "risk_score": pattern["risk_score"],
                        }
                    )
                except Exception as e:
                    logger.error(f"Error creating fraud alert: {e}")

    # Process geographic anomalies
    for pattern in patterns.get("geographic_anomalies", []):
        if pattern["risk_score"] >= 50:
            cutoff = timezone.now() - timedelta(hours=24)
            votes = Vote.objects.filter(
                poll_id=poll_id,
                ip_address=pattern["ip_address"],
                created_at__gte=cutoff,
            )[:5]

            for vote in votes:
                try:
                    FraudAlert.objects.get_or_create(
                        vote=vote,
                        defaults={
                            "poll_id": poll_id,
                            "user": vote.user,
                            "ip_address": pattern["ip_address"],
                            "reasons": f"Geographic anomaly: {pattern['details']}",
                            "risk_score": pattern["risk_score"],
                        },
                    )
                    alerts.append(
                        {
                            "vote_id": vote.id,
                            "pattern_type": pattern["pattern_type"],
                            "risk_score": pattern["risk_score"],
                        }
                    )
                except Exception as e:
                    logger.error(f"Error creating fraud alert: {e}")

    # Process user agent anomalies
    for pattern in patterns.get("user_agent_anomalies", []):
        if pattern["risk_score"] >= 50:
            cutoff = timezone.now() - timedelta(hours=24)
            votes = Vote.objects.filter(
                poll_id=poll_id,
                user_agent__startswith=pattern["user_agent"][:50],
                created_at__gte=cutoff,
            )[:10]

            for vote in votes:
                try:
                    FraudAlert.objects.get_or_create(
                        vote=vote,
                        defaults={
                            "poll_id": poll_id,
                            "user": vote.user,
                            "ip_address": vote.ip_address,
                            "reasons": (
                                f"User agent anomaly: Same UA '{pattern['user_agent'][:50]}' "
                                f"used by {pattern['unique_voters']} voters"
                            ),
                            "risk_score": pattern["risk_score"],
                        },
                    )
                    alerts.append(
                        {
                            "vote_id": vote.id,
                            "pattern_type": pattern["pattern_type"],
                            "risk_score": pattern["risk_score"],
                        }
                    )
                except Exception as e:
                    logger.error(f"Error creating fraud alert: {e}")

    return alerts


def flag_suspicious_votes(poll_id: int, patterns: Dict) -> int:
    """
    Flag votes as invalid based on detected patterns.

    Args:
        poll_id: Poll ID
        patterns: Dictionary of detected patterns

    Returns:
        Number of votes flagged
    """
    from apps.votes.models import Vote

    flagged_count = 0

    # Flag votes from high-risk single IP patterns
    for pattern in patterns.get("single_ip_single_option", []):
        if pattern["risk_score"] >= 80:
            cutoff = timezone.now() - timedelta(hours=24)
            votes = Vote.objects.filter(
                poll_id=poll_id,
                ip_address=pattern["ip_address"],
                option_id=pattern["option_id"],
                created_at__gte=cutoff,
            )

            updated = votes.update(
                is_valid=False,
                fraud_reasons=(
                    f"Flagged by pattern analysis: {pattern['pattern_type']} "
                    f"(risk score: {pattern['risk_score']})"
                ),
                risk_score=pattern["risk_score"],
            )
            flagged_count += updated

    # Flag votes from high-risk time clusters
    for pattern in patterns.get("time_clustered", []):
        if pattern["risk_score"] >= 80:
            votes = Vote.objects.filter(
                poll_id=poll_id,
                created_at__gte=pattern["start_time"],
                created_at__lte=pattern["end_time"],
            )

            updated = votes.update(
                is_valid=False,
                fraud_reasons=(
                    f"Flagged by pattern analysis: {pattern['pattern_type']} "
                    f"(risk score: {pattern['risk_score']})"
                ),
                risk_score=pattern["risk_score"],
            )
            flagged_count += updated

    return flagged_count
