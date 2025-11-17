"""
IP reputation system for tracking and blocking malicious IPs.

Provides:
- IP reputation scoring
- Automatic blocking after threshold violations
- Manual IP blocking/unblocking
- IP whitelisting
- Automatic unblocking after time period
"""

import logging
from datetime import timedelta
from typing import Optional, Tuple

from django.conf import settings
from django.utils import timezone

from apps.analytics.models import IPBlock, IPReputation, IPWhitelist

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_VIOLATION_THRESHOLD = 5  # Block after 5 violations
DEFAULT_AUTO_UNBLOCK_HOURS = 24  # Auto-unblock after 24 hours
DEFAULT_REPUTATION_THRESHOLD = 30  # Block if reputation score below this


def get_or_create_ip_reputation(ip_address: str) -> IPReputation:
    """
    Get or create IP reputation record.
    
    Args:
        ip_address: IP address to track
        
    Returns:
        IPReputation instance
    """
    reputation, created = IPReputation.objects.get_or_create(
        ip_address=ip_address,
        defaults={
            "reputation_score": 100,
            "violation_count": 0,
        }
    )
    return reputation


def is_ip_whitelisted(ip_address: str) -> bool:
    """
    Check if IP is whitelisted.
    
    Args:
        ip_address: IP address to check
        
    Returns:
        True if IP is whitelisted, False otherwise
    """
    return IPWhitelist.objects.filter(
        ip_address=ip_address,
        is_active=True
    ).exists()


def is_ip_blocked(ip_address: str) -> Tuple[bool, Optional[str]]:
    """
    Check if IP is currently blocked.
    
    Args:
        ip_address: IP address to check
        
    Returns:
        Tuple of (is_blocked: bool, reason: Optional[str])
    """
    # Check whitelist first (whitelisted IPs are never blocked)
    if is_ip_whitelisted(ip_address):
        return False, None
    
    # Check for active block
    block = IPBlock.objects.filter(
        ip_address=ip_address,
        is_active=True
    ).first()
    
    if not block:
        return False, None
    
    # Check if auto-unblock time has passed
    if block.auto_unblock_at and block.auto_unblock_at <= timezone.now():
        # Auto-unblock
        block.unblock()
        logger.info(f"Auto-unblocked IP {ip_address} (unblock time reached)")
        return False, None
    
    reason = f"IP blocked: {block.reason}"
    if block.auto_unblock_at:
        reason += f" (auto-unblock at {block.auto_unblock_at})"
    
    return True, reason


def record_ip_success(ip_address: str):
    """
    Record a successful attempt from an IP.
    
    Args:
        ip_address: IP address
    """
    if not ip_address:
        return
    
    try:
        reputation = get_or_create_ip_reputation(ip_address)
        reputation.record_success()
    except Exception as e:
        logger.error(f"Error recording IP success for {ip_address}: {e}")


def record_ip_violation(
    ip_address: str,
    reason: str,
    severity: int = 1,
    auto_block: bool = True,
) -> Optional[IPBlock]:
    """
    Record a violation from an IP and optionally block it.
    
    Args:
        ip_address: IP address
        reason: Reason for violation
        severity: Severity of violation (1-5, higher is worse)
        auto_block: Whether to automatically block if threshold reached
        
    Returns:
        IPBlock instance if IP was blocked, None otherwise
    """
    if not ip_address:
        return None
    
    # Don't record violations for whitelisted IPs
    if is_ip_whitelisted(ip_address):
        logger.debug(f"Skipping violation record for whitelisted IP {ip_address}")
        return None
    
    try:
        reputation = get_or_create_ip_reputation(ip_address)
        reputation.record_violation(severity=severity)
        
        # Check if should auto-block
        if auto_block:
            threshold = getattr(settings, "IP_VIOLATION_THRESHOLD", DEFAULT_VIOLATION_THRESHOLD)
            reputation_threshold = getattr(settings, "IP_REPUTATION_THRESHOLD", DEFAULT_REPUTATION_THRESHOLD)
            
            should_block = (
                reputation.violation_count >= threshold or
                reputation.reputation_score < reputation_threshold
            )
            
            if should_block:
                # Check if already blocked
                if not is_ip_blocked(ip_address)[0]:
                    return block_ip(
                        ip_address=ip_address,
                        reason=f"Auto-blocked: {reason} (violations: {reputation.violation_count}, score: {reputation.reputation_score})",
                        is_manual=False,
                        auto_unblock_hours=getattr(settings, "IP_AUTO_UNBLOCK_HOURS", DEFAULT_AUTO_UNBLOCK_HOURS),
                    )
        
        return None
        
    except Exception as e:
        logger.error(f"Error recording IP violation for {ip_address}: {e}")
        return None


def block_ip(
    ip_address: str,
    reason: str,
    is_manual: bool = False,
    blocked_by: Optional[object] = None,
    auto_unblock_hours: Optional[int] = None,
) -> IPBlock:
    """
    Block an IP address.
    
    Args:
        ip_address: IP address to block
        reason: Reason for blocking
        is_manual: Whether this is a manual block (admin)
        blocked_by: User who blocked the IP (for manual blocks)
        auto_unblock_hours: Hours until auto-unblock (None for permanent)
        
    Returns:
        IPBlock instance
    """
    # Don't block whitelisted IPs
    if is_ip_whitelisted(ip_address):
        raise ValueError(f"Cannot block whitelisted IP {ip_address}")
    
    # Unblock any existing inactive blocks
    IPBlock.objects.filter(ip_address=ip_address, is_active=False).update(is_active=False)
    
    # Create or update block
    block, created = IPBlock.objects.get_or_create(
        ip_address=ip_address,
        defaults={
            "reason": reason,
            "is_manual": is_manual,
            "blocked_by": blocked_by,
            "is_active": True,
        }
    )
    
    if not created:
        # Update existing block
        block.reason = reason
        block.is_manual = is_manual
        block.blocked_by = blocked_by
        block.is_active = True
        block.unblocked_at = None
        block.unblocked_by = None
    
    # Set auto-unblock time if specified
    if auto_unblock_hours and not is_manual:
        block.auto_unblock_at = timezone.now() + timedelta(hours=auto_unblock_hours)
    else:
        block.auto_unblock_at = None
    
    block.save()
    
    logger.info(f"Blocked IP {ip_address}: {reason} (manual={is_manual})")
    return block


def unblock_ip(ip_address: str, unblocked_by: Optional[object] = None) -> bool:
    """
    Unblock an IP address.
    
    Args:
        ip_address: IP address to unblock
        unblocked_by: User who unblocked the IP
        
    Returns:
        True if IP was unblocked, False if not found or already unblocked
    """
    try:
        block = IPBlock.objects.get(ip_address=ip_address, is_active=True)
        block.unblock(user=unblocked_by)
        logger.info(f"Unblocked IP {ip_address} by {unblocked_by}")
        return True
    except IPBlock.DoesNotExist:
        return False


def whitelist_ip(
    ip_address: str,
    reason: str = "",
    created_by: Optional[object] = None,
) -> IPWhitelist:
    """
    Whitelist an IP address.
    
    Args:
        ip_address: IP address to whitelist
        reason: Reason for whitelisting
        created_by: User who whitelisted the IP
        
    Returns:
        IPWhitelist instance
    """
    whitelist, created = IPWhitelist.objects.get_or_create(
        ip_address=ip_address,
        defaults={
            "reason": reason,
            "created_by": created_by,
            "is_active": True,
        }
    )
    
    if not created:
        whitelist.reason = reason
        whitelist.is_active = True
        whitelist.save()
    
    # Unblock if currently blocked
    if is_ip_blocked(ip_address)[0]:
        unblock_ip(ip_address, unblocked_by=created_by)
    
    logger.info(f"Whitelisted IP {ip_address}: {reason}")
    return whitelist


def remove_whitelist(ip_address: str) -> bool:
    """
    Remove IP from whitelist.
    
    Args:
        ip_address: IP address to remove from whitelist
        
    Returns:
        True if removed, False if not found
    """
    try:
        whitelist = IPWhitelist.objects.get(ip_address=ip_address, is_active=True)
        whitelist.is_active = False
        whitelist.save()
        logger.info(f"Removed IP {ip_address} from whitelist")
        return True
    except IPWhitelist.DoesNotExist:
        return False


def check_ip_reputation(ip_address: str) -> Tuple[bool, Optional[str]]:
    """
    Check IP reputation and block status.
    
    Args:
        ip_address: IP address to check
        
    Returns:
        Tuple of (is_allowed: bool, error_message: Optional[str])
    """
    if not ip_address:
        return True, None
    
    # Check if blocked
    is_blocked, reason = is_ip_blocked(ip_address)
    if is_blocked:
        return False, reason
    
    return True, None


def auto_unblock_expired_ips():
    """
    Automatically unblock IPs whose auto-unblock time has passed.
    This should be called periodically (e.g., via Celery task or cron).
    
    Returns:
        Number of IPs unblocked
    """
    now = timezone.now()
    expired_blocks = IPBlock.objects.filter(
        is_active=True,
        auto_unblock_at__lte=now,
        auto_unblock_at__isnull=False,
    )
    
    count = expired_blocks.count()
    for block in expired_blocks:
        block.unblock()
        logger.info(f"Auto-unblocked expired IP {block.ip_address}")
    
    if count > 0:
        logger.info(f"Auto-unblocked {count} expired IP(s)")
    
    return count

