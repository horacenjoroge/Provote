"""
Helper utilities for Provote.
"""

from datetime import datetime, timezone


def get_current_timestamp():
    """
    Get the current UTC timestamp.

    Returns:
        datetime: Current UTC datetime
    """
    return datetime.now(timezone.utc)


def format_datetime(dt):
    """
    Format a datetime object as a string.

    Args:
        dt: datetime object

    Returns:
        str: Formatted datetime string
    """
    if dt is None:
        return None
    return dt.isoformat()
