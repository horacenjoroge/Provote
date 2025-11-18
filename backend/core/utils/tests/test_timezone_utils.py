"""
Tests for timezone utilities.
"""

import pytest
from datetime import datetime
import pytz
from django.utils import timezone as django_timezone

from core.utils.timezone_utils import (
    convert_to_utc,
    convert_from_utc,
    get_timezone_aware_datetime,
    is_valid_timezone,
    get_common_timezones,
)


class TestTimezoneUtils:
    """Test timezone utility functions."""

    def test_convert_to_utc_from_naive_datetime(self):
        """Test converting naive datetime to UTC."""
        naive_dt = datetime(2024, 1, 1, 12, 0, 0)
        utc_dt = convert_to_utc(naive_dt, timezone_str='America/New_York')
        
        assert utc_dt.tzinfo == pytz.UTC
        # EST is UTC-5, so 12:00 EST = 17:00 UTC
        assert utc_dt.hour == 17

    def test_convert_to_utc_from_aware_datetime(self):
        """Test converting timezone-aware datetime to UTC."""
        ny_tz = pytz.timezone('America/New_York')
        ny_dt = ny_tz.localize(datetime(2024, 1, 1, 12, 0, 0))
        utc_dt = convert_to_utc(ny_dt)
        
        assert utc_dt.tzinfo == pytz.UTC
        assert utc_dt.hour == 17

    def test_convert_to_utc_from_iso_string(self):
        """Test converting ISO format string to UTC."""
        iso_string = "2024-01-01T12:00:00-05:00"
        utc_dt = convert_to_utc(iso_string)
        
        assert utc_dt.tzinfo == pytz.UTC
        assert utc_dt.hour == 17

    def test_convert_from_utc(self):
        """Test converting UTC datetime to specific timezone."""
        utc_dt = pytz.UTC.localize(datetime(2024, 1, 1, 17, 0, 0))
        ny_dt = convert_from_utc(utc_dt, 'America/New_York')
        
        # Check that timezone is correct (compare by name, not object)
        assert str(ny_dt.tzinfo) == str(pytz.timezone('America/New_York'))
        assert ny_dt.hour == 12

    def test_get_timezone_aware_datetime_from_naive(self):
        """Test getting timezone-aware datetime from naive datetime."""
        naive_dt = datetime(2024, 1, 1, 12, 0, 0)
        aware_dt = get_timezone_aware_datetime(naive_dt, timezone_str='America/New_York')
        
        assert aware_dt.tzinfo == pytz.UTC
        assert aware_dt.hour == 17

    def test_get_timezone_aware_datetime_from_iso_string(self):
        """Test getting timezone-aware datetime from ISO string."""
        iso_string = "2024-01-01T12:00:00Z"
        aware_dt = get_timezone_aware_datetime(iso_string)
        
        assert aware_dt.tzinfo == pytz.UTC

    def test_is_valid_timezone(self):
        """Test timezone validation."""
        assert is_valid_timezone('UTC') is True
        assert is_valid_timezone('America/New_York') is True
        assert is_valid_timezone('Europe/London') is True
        assert is_valid_timezone('Invalid/Timezone') is False
        assert is_valid_timezone('') is False

    def test_get_common_timezones(self):
        """Test getting common timezones list."""
        timezones = get_common_timezones()
        
        assert isinstance(timezones, list)
        assert len(timezones) > 0
        assert 'UTC' in timezones
        assert 'America/New_York' in timezones
        assert 'Europe/London' in timezones

    def test_timezone_conversion_round_trip(self):
        """Test that timezone conversion works both ways."""
        original_dt = pytz.timezone('America/New_York').localize(
            datetime(2024, 1, 1, 12, 0, 0)
        )
        
        # Convert to UTC
        utc_dt = convert_to_utc(original_dt)
        
        # Convert back to NY time
        ny_dt = convert_from_utc(utc_dt, 'America/New_York')
        
        assert ny_dt.hour == original_dt.hour
        assert ny_dt.minute == original_dt.minute
        assert ny_dt.day == original_dt.day

    def test_different_timezones_handled_correctly(self):
        """Test that different timezones are handled correctly."""
        # Create datetime in Tokyo timezone
        tokyo_tz = pytz.timezone('Asia/Tokyo')
        tokyo_dt = tokyo_tz.localize(datetime(2024, 1, 1, 12, 0, 0))
        
        # Convert to UTC
        utc_dt = convert_to_utc(tokyo_dt)
        
        # Convert to New York time
        ny_dt = convert_from_utc(utc_dt, 'America/New_York')
        
        # Tokyo is UTC+9, NY is UTC-5 (in January), so 14 hour difference
        # 12:00 Tokyo = 03:00 UTC = 22:00 NY (previous day)
        assert ny_dt.hour == 22
        assert ny_dt.day == 31  # Previous day

