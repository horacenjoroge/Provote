"""
Results calculation service for polls.
Efficient vote counting and results computation using denormalized counts and caching.
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import Poll, PollOption

logger = logging.getLogger(__name__)

# Cache TTL for results (1 hour)
RESULTS_CACHE_TTL = 3600


def can_view_results(poll: Poll, user) -> bool:
    """
    Check if user can view poll results based on visibility rules.
    
    Rules:
    - If poll is private (settings.is_private=True), only owner can view
    - If show_results_during_voting=False, results only shown after poll closes
    - If show_results_during_voting=True, results shown anytime
    - Public polls (default) can be viewed by anyone
    
    Args:
        poll: Poll instance
        user: User instance (can be None for anonymous)
        
    Returns:
        bool: True if user can view results
    """
    # Check if results are private
    is_private = poll.settings.get("is_private", False)
    if is_private:
        # Only owner can view private poll results
        if not user or not user.is_authenticated:
            return False
        if poll.created_by != user:
            return False
    
    # Check when results can be shown
    show_during_voting = poll.settings.get("show_results_during_voting", False)
    
    if not show_during_voting:
        # Results only shown after poll closes
        if poll.is_open:
            return False  # Poll is still open, don't show results
    
    # All checks passed
    return True


def get_results_cache_key(poll_id: int) -> str:
    """Generate cache key for poll results."""
    return f"poll_results:{poll_id}"


def calculate_poll_results(poll_id: int, use_cache: bool = True) -> Dict:
    """
    Calculate comprehensive poll results efficiently.

    Uses denormalized counts for speed and caches results.

    Args:
        poll_id: Poll ID
        use_cache: Whether to use cached results (default: True)

    Returns:
        dict: {
            "poll_id": int,
            "poll_title": str,
            "total_votes": int,
            "unique_voters": int,
            "participation_rate": float,
            "options": [
                {
                    "option_id": int,
                    "option_text": str,
                    "votes": int,
                    "percentage": float,
                    "is_winner": bool
                }
            ],
            "winners": [{"option_id": int, "option_text": str, "votes": int}],
            "is_tie": bool,
            "calculated_at": str
        }
    """
    cache_key = get_results_cache_key(poll_id)

    # Try to get from cache
    if use_cache:
        cached_results = cache.get(cache_key)
        if cached_results:
            logger.debug(f"Returning cached results for poll {poll_id}")
            return cached_results

    # Calculate results
    try:
        # Optimize query with select_related and prefetch_related
        poll = (
            Poll.objects.select_related("created_by")
            .prefetch_related("options")
            .get(id=poll_id)
        )
    except Poll.DoesNotExist:
        raise ValueError(f"Poll {poll_id} not found")

    # Get options with optimized query
    # Use cached_vote_count for speed (denormalized)
    options = (
        poll.options.all()
        .order_by("order", "id")
        .values("id", "text", "order", "cached_vote_count")
    )

    # Calculate total votes (use cached value for speed)
    total_votes = poll.cached_total_votes

    # Calculate unique voters (use cached value)
    unique_voters = poll.cached_unique_voters

    # Calculate participation rate
    # Participation rate = (unique_voters / total_eligible_voters) * 100
    # Since we don't have eligible_voters count, we'll use a simplified calculation:
    # participation_rate = unique_voters / total_votes * 100
    # This represents the ratio of unique voters to total votes cast
    # In a real system, you might have a separate field for eligible_voters
    participation_rate = 0.0
    if total_votes > 0:
        # For polls where one user can only vote once, unique_voters == total_votes
        # For polls allowing multiple votes, this ratio shows voter diversity
        participation_rate = (float(unique_voters) / total_votes) * 100

    # Calculate option results
    option_results = []
    max_votes = 0
    winners = []

    for option in options:
        votes = option["cached_vote_count"]
        percentage = (float(votes) / total_votes * 100) if total_votes > 0 else 0.0

        option_result = {
            "option_id": option["id"],
            "option_text": option["text"],
            "order": option["order"],
            "votes": votes,
            "percentage": round(percentage, 2),
            "is_winner": False,
        }

        option_results.append(option_result)

        # Track max votes for winner detection
        if votes > max_votes:
            max_votes = votes
            winners = [option_result]
        elif votes == max_votes and votes > 0:
            winners.append(option_result)

    # Mark winners
    for option_result in option_results:
        if option_result["votes"] == max_votes and max_votes > 0:
            option_result["is_winner"] = True

    # Determine if there's a tie
    is_tie = len(winners) > 1 and max_votes > 0

    # Calculate aggregate statistics
    stats = calculate_aggregate_statistics(poll_id, total_votes, unique_voters, option_results)
    
    # Build results
    results = {
        "poll_id": poll.id,
        "poll_title": poll.title,
        "total_votes": total_votes,
        "unique_voters": unique_voters,
        "participation_rate": round(participation_rate, 2),
        "options": option_results,
        "winners": [
            {"option_id": w["option_id"], "option_text": w["option_text"], "votes": w["votes"]}
            for w in winners
        ],
        "is_tie": is_tie,
        "calculated_at": timezone.now().isoformat(),
        "statistics": stats,
    }

    # Cache results
    try:
        cache.set(cache_key, results, RESULTS_CACHE_TTL)
        logger.debug(f"Cached results for poll {poll_id}")
    except Exception as e:
        logger.error(f"Error caching results for poll {poll_id}: {e}")

    return results


def calculate_option_vote_counts(poll_id: int) -> Dict[int, int]:
    """
    Calculate vote counts per option.

    Uses denormalized cached_vote_count for speed.

    Args:
        poll_id: Poll ID

    Returns:
        dict: {option_id: vote_count}
    """
    options = (
        PollOption.objects.filter(poll_id=poll_id)
        .values("id", "cached_vote_count")
    )

    return {option["id"]: option["cached_vote_count"] for option in options}


def calculate_percentages(vote_counts: Dict[int, int], total_votes: int) -> Dict[int, float]:
    """
    Calculate percentages for each option.

    Args:
        vote_counts: Dictionary of {option_id: vote_count}
        total_votes: Total number of votes

    Returns:
        dict: {option_id: percentage}
    """
    if total_votes == 0:
        return {option_id: 0.0 for option_id in vote_counts.keys()}

    percentages = {}
    for option_id, votes in vote_counts.items():
        percentage = (float(votes) / total_votes) * 100
        percentages[option_id] = round(percentage, 2)

    return percentages


def calculate_winners(poll_id: int) -> Tuple[List[Dict], bool]:
    """
    Calculate winner(s) for a poll.

    Args:
        poll_id: Poll ID

    Returns:
        tuple: (winners_list, is_tie)
            winners_list: List of winner option dictionaries
            is_tie: True if there's a tie
    """
    options = (
        PollOption.objects.filter(poll_id=poll_id)
        .values("id", "text", "cached_vote_count")
        .order_by("-cached_vote_count", "id")
    )

    if not options:
        return [], False

    # Get max votes
    max_votes = max(opt["cached_vote_count"] for opt in options)

    if max_votes == 0:
        return [], False

    # Find all options with max votes
    winners = [
        {"option_id": opt["id"], "option_text": opt["text"], "votes": opt["cached_vote_count"]}
        for opt in options
        if opt["cached_vote_count"] == max_votes
    ]

    is_tie = len(winners) > 1

    return winners, is_tie


def calculate_participation_rate(poll_id: int) -> float:
    """
    Calculate participation rate for a poll.

    Args:
        poll_id: Poll ID

    Returns:
        float: Participation rate as percentage
    """
    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        raise ValueError(f"Poll {poll_id} not found")

    total_votes = poll.cached_total_votes
    unique_voters = poll.cached_unique_voters

    if total_votes == 0:
        return 0.0

    # Participation rate = (unique_voters / total_votes) * 100
    # This represents the ratio of unique voters to total votes
    # For single-vote polls, this will be 100%
    # For multi-vote polls, this shows voter diversity
    participation_rate = (float(unique_voters) / total_votes) * 100

    return round(participation_rate, 2)


def invalidate_results_cache(poll_id: int):
    """
    Invalidate cached results for a poll.

    Args:
        poll_id: Poll ID
    """
    cache_key = get_results_cache_key(poll_id)
    try:
        cache.delete(cache_key)
        logger.debug(f"Invalidated results cache for poll {poll_id}")
    except Exception as e:
        logger.error(f"Error invalidating cache for poll {poll_id}: {e}")


def get_cached_results(poll_id: int) -> Optional[Dict]:
    """
    Get cached results for a poll.

    Args:
        poll_id: Poll ID

    Returns:
        dict: Cached results or None if not cached
    """
    cache_key = get_results_cache_key(poll_id)
    return cache.get(cache_key)


def calculate_aggregate_statistics(
    poll_id: int,
    total_votes: int,
    unique_voters: int,
    option_results: List[Dict],
) -> Dict:
    """
    Calculate aggregate statistics for poll results.
    
    Args:
        poll_id: Poll ID
        total_votes: Total number of votes
        unique_voters: Number of unique voters
        option_results: List of option result dictionaries
        
    Returns:
        dict: Aggregate statistics
    """
    if not option_results:
        return {
            "average_votes_per_option": 0.0,
            "median_votes_per_option": 0.0,
            "max_votes": 0,
            "min_votes": 0,
            "vote_distribution": {},
            "options_count": 0,
        }
    
    votes_list = [opt["votes"] for opt in option_results]
    votes_list_sorted = sorted(votes_list)
    
    # Calculate statistics
    average_votes = sum(votes_list) / len(votes_list) if votes_list else 0.0
    
    # Median
    n = len(votes_list_sorted)
    if n % 2 == 0:
        median_votes = (votes_list_sorted[n // 2 - 1] + votes_list_sorted[n // 2]) / 2
    else:
        median_votes = votes_list_sorted[n // 2]
    
    max_votes = max(votes_list) if votes_list else 0
    min_votes = min(votes_list) if votes_list else 0
    
    # Vote distribution (how many options have each vote count)
    vote_distribution = {}
    for votes in votes_list:
        vote_distribution[votes] = vote_distribution.get(votes, 0) + 1
    
    return {
        "average_votes_per_option": round(average_votes, 2),
        "median_votes_per_option": round(median_votes, 2),
        "max_votes": max_votes,
        "min_votes": min_votes,
        "vote_distribution": vote_distribution,
        "options_count": len(option_results),
    }


def export_results_to_csv(poll_id: int) -> str:
    """
    Export poll results to CSV format.
    
    Args:
        poll_id: Poll ID
        
    Returns:
        str: CSV content as string
    """
    import csv
    from io import StringIO
    
    try:
        poll = Poll.objects.get(id=poll_id)
    except Poll.DoesNotExist:
        raise ValueError(f"Poll {poll_id} not found")
    
    results = calculate_poll_results(poll_id, use_cache=True)
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(["Poll Results"])
    writer.writerow([f"Poll: {results['poll_title']}"])
    writer.writerow([f"Total Votes: {results['total_votes']}"])
    writer.writerow([f"Unique Voters: {results['unique_voters']}"])
    writer.writerow([f"Participation Rate: {results['participation_rate']}%"])
    writer.writerow([f"Calculated At: {results['calculated_at']}"])
    writer.writerow([])  # Empty row
    
    # Options header
    writer.writerow(["Option ID", "Option Text", "Votes", "Percentage", "Is Winner"])
    
    # Options data
    for option in results["options"]:
        writer.writerow([
            option["option_id"],
            option["option_text"],
            option["votes"],
            f"{option['percentage']}%",
            "Yes" if option["is_winner"] else "No",
        ])
    
    writer.writerow([])  # Empty row
    
    # Winners
    if results["winners"]:
        writer.writerow(["Winners"])
        for winner in results["winners"]:
            writer.writerow([winner["option_text"], f"{winner['votes']} votes"])
    
    return output.getvalue()


def export_results_to_json(poll_id: int) -> Dict:
    """
    Export poll results to JSON format.
    
    Args:
        poll_id: Poll ID
        
    Returns:
        dict: Results as dictionary (can be serialized to JSON)
    """
    return calculate_poll_results(poll_id, use_cache=True)


def broadcast_poll_results_update(poll_id: int):
    """
    Broadcast poll results update to all WebSocket subscribers.
    
    This function is called when a vote is cast to notify all connected
    clients about the updated results.
    
    Args:
        poll_id: Poll ID
    """
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("Channel layer not configured, skipping broadcast")
            return

        # Get updated results
        results = calculate_poll_results(poll_id, use_cache=False)

        # Get group name
        group_name = get_poll_group_name(poll_id)

        # Broadcast to all subscribers
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "poll_results_update",
                "poll_id": poll_id,
                "results": results,
            },
        )

        logger.debug(f"Broadcasted results update for poll {poll_id} to group {group_name}")
    except Exception as e:
        logger.error(f"Error broadcasting poll results update: {e}")


def get_poll_group_name(poll_id: int) -> str:
    """Generate channel group name for a poll."""
    return f"poll_{poll_id}_results"

