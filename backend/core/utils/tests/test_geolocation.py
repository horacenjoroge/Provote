"""
Tests for IP geolocation utilities.
"""

import pytest
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from django.conf import settings

from core.utils.geolocation import (
    get_country_from_ip,
    get_region_from_ip,
    validate_geographic_restriction,
)


class TestIPGeolocation:
    """Test IP geolocation functionality."""
    
    def test_get_country_from_ip_private_ip(self):
        """Test that private IPs return None."""
        assert get_country_from_ip("127.0.0.1") is None
        assert get_country_from_ip("192.168.1.1") is None
        assert get_country_from_ip("10.0.0.1") is None
        assert get_country_from_ip("172.16.0.1") is None
    
    def test_get_country_from_ip_none(self):
        """Test that None IP returns None."""
        assert get_country_from_ip(None) is None
        assert get_country_from_ip("") is None
    
    @patch('core.utils.geolocation._get_country_from_ipapi')
    def test_get_country_from_ip_api_success(self, mock_ipapi):
        """Test successful IP API lookup."""
        mock_ipapi.return_value = "US"
        
        country = get_country_from_ip("8.8.8.8")
        assert country == "US"
        mock_ipapi.assert_called_once_with("8.8.8.8")
    
    @patch('core.utils.geolocation._get_country_from_maxmind')
    @patch('core.utils.geolocation._get_country_from_ipapi')
    def test_get_country_from_ip_caching(self, mock_ipapi, mock_maxmind):
        """Test that country lookups are cached."""
        mock_maxmind.return_value = None  # MaxMind not available
        mock_ipapi.return_value = "GB"
        
        # Clear cache
        cache.delete("geoip:8.8.8.8")
        
        # First call should hit API
        country1 = get_country_from_ip("8.8.8.8")
        assert country1 == "GB"
        assert mock_ipapi.call_count == 1
        
        # Second call should use cache
        country2 = get_country_from_ip("8.8.8.8")
        assert country2 == "GB"
        assert mock_ipapi.call_count == 1  # Still 1, not 2
    
    @patch('core.utils.geolocation.settings')
    @patch('core.utils.geolocation._get_country_from_mock')
    def test_get_country_from_ip_mock_provider(self, mock_mock, mock_settings):
        """Test mock geolocation provider for testing."""
        mock_settings.USE_MOCK_GEOLOCATION = True
        mock_mock.return_value = "FR"
        
        country = get_country_from_ip("203.0.113.1")
        assert country == "FR"
    
    def test_get_country_from_ip_mock_default_mapping(self):
        """Test default mock mapping."""
        with patch('core.utils.geolocation.settings') as mock_settings:
            mock_settings.USE_MOCK_GEOLOCATION = True
            mock_settings.MOCK_GEOIP_MAPPING = {}
            
            # Test-NET-1 should map to US
            assert get_country_from_ip("203.0.113.1") == "US"
            # Test-NET-2 should map to GB
            assert get_country_from_ip("198.51.100.1") == "GB"
            # Test-NET-3 should map to FR
            assert get_country_from_ip("192.0.2.1") == "FR"
    
    @patch('core.utils.geolocation._get_country_from_maxmind')
    def test_get_country_from_ip_maxmind_priority(self, mock_maxmind):
        """Test that MaxMind is tried first."""
        mock_maxmind.return_value = "DE"
        
        country = get_country_from_ip("8.8.8.8")
        assert country == "DE"
        mock_maxmind.assert_called_once_with("8.8.8.8")
    
    def test_get_region_from_ip_private_ip(self):
        """Test that private IPs return None for region."""
        assert get_region_from_ip("127.0.0.1") is None
        assert get_region_from_ip("192.168.1.1") is None
    
    def test_get_region_from_ip_none(self):
        """Test that None IP returns None for region."""
        assert get_region_from_ip(None) is None
        assert get_region_from_ip("") is None


class TestGeographicRestrictionValidation:
    """Test geographic restriction validation."""
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_validate_geographic_restriction_no_restrictions(self, mock_get_country):
        """Test validation when no restrictions are set."""
        mock_get_country.return_value = "US"
        
        is_allowed, error = validate_geographic_restriction(
            ip_address="8.8.8.8",
            allowed_countries=None,
            blocked_countries=None,
        )
        
        assert is_allowed is True
        assert error is None
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_validate_geographic_restriction_allowed_country(self, mock_get_country):
        """Test validation with allowed country whitelist."""
        mock_get_country.return_value = "US"
        
        is_allowed, error = validate_geographic_restriction(
            ip_address="8.8.8.8",
            allowed_countries=["US", "CA", "GB"],
            blocked_countries=None,
        )
        
        assert is_allowed is True
        assert error is None
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_validate_geographic_restriction_not_allowed_country(self, mock_get_country):
        """Test validation when country is not in allowed list."""
        mock_get_country.return_value = "FR"
        
        is_allowed, error = validate_geographic_restriction(
            ip_address="8.8.8.8",
            allowed_countries=["US", "CA", "GB"],
            blocked_countries=None,
        )
        
        assert is_allowed is False
        assert "only allowed from" in error.lower()
        assert "US" in error or "CA" in error or "GB" in error
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_validate_geographic_restriction_blocked_country(self, mock_get_country):
        """Test validation with blocked country."""
        mock_get_country.return_value = "CN"
        
        is_allowed, error = validate_geographic_restriction(
            ip_address="8.8.8.8",
            allowed_countries=None,
            blocked_countries=["CN", "RU"],
        )
        
        assert is_allowed is False
        assert "not allowed from" in error.lower()
        assert "CN" in error
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_validate_geographic_restriction_blocked_takes_priority(self, mock_get_country):
        """Test that blocked countries take priority over allowed."""
        mock_get_country.return_value = "CN"
        
        is_allowed, error = validate_geographic_restriction(
            ip_address="8.8.8.8",
            allowed_countries=["US", "CN", "GB"],  # CN is in allowed
            blocked_countries=["CN", "RU"],  # But also in blocked
        )
        
        assert is_allowed is False
        assert "not allowed from" in error.lower()
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_validate_geographic_restriction_case_insensitive(self, mock_get_country):
        """Test that country codes are case-insensitive."""
        mock_get_country.return_value = "us"  # Lowercase
        
        is_allowed, error = validate_geographic_restriction(
            ip_address="8.8.8.8",
            allowed_countries=["US", "CA"],  # Uppercase
            blocked_countries=None,
        )
        
        assert is_allowed is True
        assert error is None
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_validate_geographic_restriction_no_ip(self, mock_get_country):
        """Test validation when IP is None (should allow)."""
        is_allowed, error = validate_geographic_restriction(
            ip_address=None,
            allowed_countries=["US", "CA"],
            blocked_countries=None,
        )
        
        assert is_allowed is True
        assert error is None
        mock_get_country.assert_not_called()
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_validate_geographic_restriction_cannot_determine_country(self, mock_get_country):
        """Test validation when country cannot be determined."""
        mock_get_country.return_value = None
        
        is_allowed, error = validate_geographic_restriction(
            ip_address="8.8.8.8",
            allowed_countries=["US", "CA"],
            blocked_countries=None,
        )
        
        assert is_allowed is False
        assert "could not determine" in error.lower()
    
    @patch('core.utils.geolocation.get_country_from_ip')
    @patch('core.utils.geolocation.get_region_from_ip')
    def test_validate_geographic_restriction_allowed_region(self, mock_get_region, mock_get_country):
        """Test validation with allowed region."""
        mock_get_country.return_value = "US"
        mock_get_region.return_value = "CA"
        
        is_allowed, error = validate_geographic_restriction(
            ip_address="8.8.8.8",
            allowed_countries=None,
            blocked_countries=None,
            allowed_regions=["CA", "NY"],
            blocked_regions=None,
        )
        
        assert is_allowed is True
        assert error is None
    
    @patch('core.utils.geolocation.get_country_from_ip')
    @patch('core.utils.geolocation.get_region_from_ip')
    def test_validate_geographic_restriction_blocked_region(self, mock_get_region, mock_get_country):
        """Test validation with blocked region."""
        mock_get_country.return_value = "US"
        mock_get_region.return_value = "TX"
        
        is_allowed, error = validate_geographic_restriction(
            ip_address="8.8.8.8",
            allowed_countries=None,
            blocked_countries=None,
            allowed_regions=None,
            blocked_regions=["TX", "FL"],
        )
        
        assert is_allowed is False
        assert "not allowed from region" in error.lower()
    
    @patch('core.utils.geolocation.get_country_from_ip')
    @patch('core.utils.geolocation.get_region_from_ip')
    def test_validate_geographic_restriction_region_not_allowed(self, mock_get_region, mock_get_country):
        """Test validation when region is not in allowed list."""
        mock_get_country.return_value = "US"
        mock_get_region.return_value = "TX"
        
        is_allowed, error = validate_geographic_restriction(
            ip_address="8.8.8.8",
            allowed_countries=None,
            blocked_countries=None,
            allowed_regions=["CA", "NY"],
            blocked_regions=None,
        )
        
        assert is_allowed is False
        assert "only allowed from regions" in error.lower()

