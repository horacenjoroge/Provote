"""
Google reCAPTCHA v3 verification utility.

Provides:
- CAPTCHA token verification
- Score-based verification (reject low scores)
- Trusted user bypass
"""

import logging
from typing import Dict, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Default minimum score threshold (0.0 to 1.0)
# Lower scores indicate more suspicious activity
DEFAULT_MIN_SCORE = 0.5

# reCAPTCHA v3 verification endpoint
RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


def verify_recaptcha_token(token: str, remote_ip: Optional[str] = None) -> Dict:
    """
    Verify a reCAPTCHA v3 token with Google's API.
    
    Args:
        token: The reCAPTCHA token from the client
        remote_ip: Optional client IP address for verification
        
    Returns:
        Dictionary with verification result:
        {
            "success": bool,
            "score": float (0.0 to 1.0),
            "action": str,
            "challenge_ts": str,
            "hostname": str,
            "error_codes": list (if any errors)
        }
    """
    secret_key = getattr(settings, "RECAPTCHA_SECRET_KEY", None)
    
    if not secret_key:
        logger.warning("RECAPTCHA_SECRET_KEY not configured, skipping verification")
        return {
            "success": False,
            "score": 0.0,
            "error_codes": ["missing-secret-key"],
        }
    
    if not token:
        logger.warning("CAPTCHA token is missing")
        return {
            "success": False,
            "score": 0.0,
            "error_codes": ["missing-input-response"],
        }
    
    try:
        # Prepare verification request
        data = {
            "secret": secret_key,
            "response": token,
        }
        
        if remote_ip:
            data["remoteip"] = remote_ip
        
        # Make request to Google's verification API
        response = requests.post(
            RECAPTCHA_VERIFY_URL,
            data=data,
            timeout=5,  # 5 second timeout
        )
        
        response.raise_for_status()
        result = response.json()
        
        logger.debug(
            f"reCAPTCHA verification result: success={result.get('success')}, "
            f"score={result.get('score')}, action={result.get('action')}"
        )
        
        return {
            "success": result.get("success", False),
            "score": result.get("score", 0.0),
            "action": result.get("action", ""),
            "challenge_ts": result.get("challenge_ts", ""),
            "hostname": result.get("hostname", ""),
            "error_codes": result.get("error-codes", []),
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error verifying reCAPTCHA token: {e}")
        return {
            "success": False,
            "score": 0.0,
            "error_codes": ["network-error"],
        }
    except Exception as e:
        logger.error(f"Unexpected error verifying reCAPTCHA token: {e}")
        return {
            "success": False,
            "score": 0.0,
            "error_codes": ["internal-error"],
        }


def verify_captcha_for_vote(
    token: Optional[str],
    poll_settings: Dict,
    user=None,
    remote_ip: Optional[str] = None,
    min_score: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Verify CAPTCHA for a vote request.
    
    Args:
        token: CAPTCHA token from client (optional)
        poll_settings: Poll settings dictionary (may contain enable_captcha flag)
        user: Optional user object (for trusted user bypass)
        remote_ip: Optional client IP address
        min_score: Optional minimum score threshold (defaults to DEFAULT_MIN_SCORE)
        
    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])
        - is_valid: True if CAPTCHA is valid or not required
        - error_message: Error message if validation failed, None otherwise
    """
    # Check if CAPTCHA is enabled for this poll
    enable_captcha = poll_settings.get("enable_captcha", False)
    
    if not enable_captcha:
        # CAPTCHA not required for this poll
        return True, None
    
    # Check if user is trusted (staff/superuser bypass)
    if user and (user.is_staff or user.is_superuser):
        logger.debug(f"CAPTCHA bypass for trusted user: {user.username}")
        return True, None
    
    # CAPTCHA is required - check if token is provided
    if not token:
        return False, "CAPTCHA token is required for this poll"
    
    # Verify the token
    verification_result = verify_recaptcha_token(token, remote_ip)
    
    if not verification_result["success"]:
        error_codes = verification_result.get("error_codes", [])
        error_msg = f"CAPTCHA verification failed: {', '.join(error_codes)}"
        logger.warning(f"CAPTCHA verification failed: {error_codes}")
        return False, error_msg
    
    # Check score threshold
    score = verification_result.get("score", 0.0)
    threshold = min_score if min_score is not None else getattr(settings, "RECAPTCHA_MIN_SCORE", DEFAULT_MIN_SCORE)
    
    if score < threshold:
        error_msg = (
            f"CAPTCHA score ({score:.2f}) is below minimum threshold ({threshold:.2f}). "
            "This may indicate suspicious activity."
        )
        logger.warning(f"CAPTCHA score too low: {score} < {threshold}")
        return False, error_msg
    
    # CAPTCHA verification passed
    logger.debug(f"CAPTCHA verification passed with score: {score:.2f}")
    return True, None

