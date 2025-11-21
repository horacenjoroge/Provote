"""
IP Geolocation utilities for geographic restrictions.

Supports multiple geolocation providers:
- MaxMind GeoIP2 (requires GeoLite2 database)
- Free IP API services (ipapi.co, ip-api.com)
- Mock provider for testing
"""

import logging
from typing import Dict, Optional, Tuple

from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


def get_country_from_ip(ip_address: str) -> Optional[str]:
    """
    Get country code (ISO 3166-1 alpha-2) from IP address.
    
    Uses multiple providers in order of preference:
    1. MaxMind GeoIP2 (if configured)
    2. Free IP API services
    3. Mock provider (for testing)
    
    Args:
        ip_address: IP address to geolocate
        
    Returns:
        str: ISO 3166-1 alpha-2 country code (e.g., 'US', 'GB', 'FR') or None if not found
    """
    if not ip_address:
        return None
    
    # Skip private/local IPs
    if ip_address.startswith(('127.', '192.168.', '10.', '172.')):
        logger.debug(f"Skipping geolocation for private IP: {ip_address}")
        return None
    
    # Check cache first (1 hour TTL)
    cache_key = f"geoip:{ip_address}"
    cached_country = cache.get(cache_key)
    if cached_country:
        return cached_country
    
    country = None
    
    # Try MaxMind GeoIP2 first (if configured)
    try:
        country = _get_country_from_maxmind(ip_address)
        if country:
            cache.set(cache_key, country, 3600)  # Cache for 1 hour
            return country
    except Exception as e:
        logger.debug(f"MaxMind GeoIP2 lookup failed: {e}")
    
    # Try free IP API services
    try:
        country = _get_country_from_ipapi(ip_address)
        if country:
            cache.set(cache_key, country, 3600)
            return country
    except Exception as e:
        logger.debug(f"IP API lookup failed: {e}")
    
    # For testing, use mock provider
    if getattr(settings, 'USE_MOCK_GEOLOCATION', False):
        country = _get_country_from_mock(ip_address)
        if country:
            cache.set(cache_key, country, 3600)
            return country
    
    if not country:
        logger.warning(f"Could not determine country for IP: {ip_address}")
    
    return country


def _get_country_from_maxmind(ip_address: str) -> Optional[str]:
    """Get country from MaxMind GeoIP2 database."""
    try:
        import geoip2.database
        import geoip2.errors
        
        # Check if database path is configured
        db_path = getattr(settings, 'GEOIP2_DATABASE_PATH', None)
        if not db_path:
            return None
        
        with geoip2.database.Reader(db_path) as reader:
            try:
                response = reader.country(ip_address)
                return response.country.iso_code
            except geoip2.errors.AddressNotFoundError:
                return None
    except ImportError:
        logger.debug("geoip2 not installed, skipping MaxMind lookup")
        return None
    except Exception as e:
        logger.error(f"Error in MaxMind GeoIP2 lookup: {e}")
        return None


def _get_country_from_ipapi(ip_address: str) -> Optional[str]:
    """Get country from free IP API service (ipapi.co)."""
    try:
        import requests
        
        # Use free tier (no API key required, rate limited)
        url = f"https://ipapi.co/{ip_address}/country_code/"
        response = requests.get(url, timeout=2)
        
        if response.status_code == 200:
            country = response.text.strip()
            # Validate it's a 2-letter country code
            if country and len(country) == 2 and country.isalpha():
                return country.upper()
        
        return None
    except ImportError:
        logger.debug("requests not installed, skipping IP API lookup")
        return None
    except Exception as e:
        logger.debug(f"Error in IP API lookup: {e}")
        return None


def _get_country_from_mock(ip_address: str) -> Optional[str]:
    """
    Mock geolocation provider for testing.
    
    Maps IP addresses to countries for testing purposes.
    """
    # Simple mock mapping for testing
    # In real tests, this can be overridden
    mock_mapping = getattr(settings, 'MOCK_GEOIP_MAPPING', {})
    
    if ip_address in mock_mapping:
        return mock_mapping[ip_address]
    
    # Default mock mapping based on IP patterns
    if ip_address.startswith('203.0.113.'):  # TEST-NET-1 (RFC 5737)
        return 'US'
    elif ip_address.startswith('198.51.100.'):  # TEST-NET-2
        return 'GB'
    elif ip_address.startswith('192.0.2.'):  # TEST-NET-3
        return 'FR'
    elif ip_address.startswith('2001:db8:'):  # IPv6 documentation prefix
        return 'DE'
    
    return None


def get_region_from_ip(ip_address: str) -> Optional[str]:
    """
    Get region/state code from IP address.
    
    Args:
        ip_address: IP address to geolocate
        
    Returns:
        str: Region/state code or None if not found
    """
    if not ip_address:
        return None
    
    # Skip private/local IPs
    if ip_address.startswith(('127.', '192.168.', '10.', '172.')):
        return None
    
    # Check cache
    cache_key = f"geoip:region:{ip_address}"
    cached_region = cache.get(cache_key)
    if cached_region:
        return cached_region
    
    region = None
    
    # Try MaxMind GeoIP2
    try:
        region = _get_region_from_maxmind(ip_address)
        if region:
            cache.set(cache_key, region, 3600)
            return region
    except Exception as e:
        logger.debug(f"MaxMind region lookup failed: {e}")
    
    # Try free IP API
    try:
        region = _get_region_from_ipapi(ip_address)
        if region:
            cache.set(cache_key, region, 3600)
            return region
    except Exception as e:
        logger.debug(f"IP API region lookup failed: {e}")
    
    return None


def _get_region_from_maxmind(ip_address: str) -> Optional[str]:
    """Get region from MaxMind GeoIP2 database."""
    try:
        import geoip2.database
        
        db_path = getattr(settings, 'GEOIP2_DATABASE_PATH', None)
        if not db_path:
            return None
        
        with geoip2.database.Reader(db_path) as reader:
            try:
                response = reader.city(ip_address)
                # Return subdivision ISO code (e.g., 'CA' for California)
                if response.subdivisions.most_specific.iso_code:
                    return response.subdivisions.most_specific.iso_code
                return None
            except Exception:
                return None
    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"Error in MaxMind region lookup: {e}")
        return None


def _get_region_from_ipapi(ip_address: str) -> Optional[str]:
    """Get region from free IP API service."""
    try:
        import requests
        
        url = f"https://ipapi.co/{ip_address}/region_code/"
        response = requests.get(url, timeout=2)
        
        if response.status_code == 200:
            region = response.text.strip()
            if region:
                return region
        
        return None
    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"Error in IP API region lookup: {e}")
        return None


def validate_geographic_restriction(
    ip_address: Optional[str],
    allowed_countries: Optional[list] = None,
    blocked_countries: Optional[list] = None,
    allowed_regions: Optional[list] = None,
    blocked_regions: Optional[list] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate if an IP address is allowed based on geographic restrictions.
    
    Args:
        ip_address: IP address to validate
        allowed_countries: List of allowed country codes (ISO 3166-1 alpha-2)
        blocked_countries: List of blocked country codes
        allowed_regions: List of allowed region codes
        blocked_regions: List of blocked region codes
        
    Returns:
        tuple: (is_allowed: bool, error_message: str or None)
    """
    if not ip_address:
        # If no IP, allow (for testing or local development)
        # In production, you might want to block this
        return True, None
    
    # Get country and region
    country = get_country_from_ip(ip_address)
    region = get_region_from_ip(ip_address)
    
    # If we can't determine location and restrictions are set, be conservative
    if not country and (allowed_countries or blocked_countries):
        # Option: allow if we can't determine (fail open)
        # Or: block if we can't determine (fail closed)
        # Using fail closed for security
        return False, "Could not determine geographic location"
    
    # Check country restrictions
    if country:
        # Check blocked countries first (more restrictive)
        if blocked_countries and country.upper() in [c.upper() for c in blocked_countries]:
            return False, f"Voting is not allowed from {country}"
        
        # Check allowed countries (whitelist)
        if allowed_countries:
            if country.upper() not in [c.upper() for c in allowed_countries]:
                return False, f"Voting is only allowed from: {', '.join(allowed_countries)}"
    
    # Check region restrictions
    if region:
        # Check blocked regions
        if blocked_regions and region.upper() in [r.upper() for r in blocked_regions]:
            return False, f"Voting is not allowed from region {region}"
        
        # Check allowed regions
        if allowed_regions:
            if region.upper() not in [r.upper() for r in allowed_regions]:
                return False, f"Voting is only allowed from regions: {', '.join(allowed_regions)}"
    
    return True, None

