"""
Timezone utilities for handling poll scheduling across different timezones.
"""

import pytz
from django.utils import timezone
from typing import Optional, Union
from datetime import datetime


def convert_to_utc(dt: Union[datetime, str], timezone_str: Optional[str] = None) -> datetime:
    """
    Convert a datetime to UTC.
    
    Args:
        dt: Datetime object or ISO format string
        timezone_str: Timezone string (e.g., 'America/New_York'). If None, uses Django's TIME_ZONE
        
    Returns:
        datetime: UTC datetime (timezone-aware)
    """
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
    
    # If datetime is naive, assume it's in the specified timezone
    if timezone.is_naive(dt):
        tz = pytz.timezone(timezone_str) if timezone_str else pytz.timezone(timezone.get_current_timezone_name())
        dt = tz.localize(dt)
    
    # Convert to UTC
    return dt.astimezone(pytz.UTC)


def convert_from_utc(dt: datetime, timezone_str: str) -> datetime:
    """
    Convert a UTC datetime to a specific timezone.
    
    Args:
        dt: UTC datetime (timezone-aware)
        timezone_str: Target timezone string (e.g., 'America/New_York')
        
    Returns:
        datetime: Datetime in the specified timezone
    """
    if timezone.is_naive(dt):
        # Assume UTC if naive
        dt = pytz.UTC.localize(dt)
    
    target_tz = pytz.timezone(timezone_str)
    return dt.astimezone(target_tz)


def get_timezone_aware_datetime(dt: Union[datetime, str], timezone_str: Optional[str] = None) -> datetime:
    """
    Get a timezone-aware datetime, converting to UTC if needed.
    
    Args:
        dt: Datetime object or ISO format string
        timezone_str: Timezone string. If None, uses Django's TIME_ZONE
        
    Returns:
        datetime: Timezone-aware datetime in UTC
    """
    if isinstance(dt, str):
        # Try parsing ISO format
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError(f"Invalid datetime format: {dt}")
    
    if timezone.is_naive(dt):
        # If naive, assume it's in the specified timezone (or Django's default)
        tz_str = timezone_str or timezone.get_current_timezone_name()
        tz = pytz.timezone(tz_str)
        dt = tz.localize(dt)
    
    # Ensure we're in UTC
    if dt.tzinfo != pytz.UTC:
        dt = dt.astimezone(pytz.UTC)
    
    return dt


def is_valid_timezone(timezone_str: str) -> bool:
    """
    Check if a timezone string is valid.
    
    Args:
        timezone_str: Timezone string to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    try:
        pytz.timezone(timezone_str)
        return True
    except (pytz.UnknownTimeZoneError, AttributeError):
        return False


def get_common_timezones() -> list:
    """
    Get a list of common timezones.
    
    Returns:
        list: List of timezone strings
    """
    return [
        'UTC',
        'America/New_York',
        'America/Chicago',
        'America/Denver',
        'America/Los_Angeles',
        'Europe/London',
        'Europe/Paris',
        'Europe/Berlin',
        'Asia/Tokyo',
        'Asia/Shanghai',
        'Asia/Dubai',
        'Australia/Sydney',
    ]

