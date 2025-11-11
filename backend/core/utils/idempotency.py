"""
Idempotency utilities for ensuring vote operations are idempotent.
"""

import hashlib
import json
from django.core.cache import cache
from django.conf import settings


def generate_idempotency_key(user_id, poll_id, choice_id):
    """
    Generate an idempotency key for a vote operation.

    Args:
        user_id: The ID of the user making the vote
        poll_id: The ID of the poll being voted on
        choice_id: The ID of the choice being selected

    Returns:
        str: A unique idempotency key
    """
    data = f"{user_id}:{poll_id}:{choice_id}"
    return hashlib.sha256(data.encode()).hexdigest()


def check_idempotency(idempotency_key):
    """
    Check if an operation with the given idempotency key has already been processed.

    Args:
        idempotency_key: The idempotency key to check

    Returns:
        tuple: (is_duplicate: bool, cached_result: dict or None)
    """
    cache_key = f"idempotency:{idempotency_key}"
    cached_result = cache.get(cache_key)

    if cached_result:
        return True, cached_result

    return False, None


def store_idempotency_result(idempotency_key, result, ttl=3600):
    """
    Store the result of an idempotent operation.

    Args:
        idempotency_key: The idempotency key
        result: The result to cache
        ttl: Time to live in seconds (default: 1 hour)
    """
    cache_key = f"idempotency:{idempotency_key}"
    cache.set(cache_key, result, ttl)
