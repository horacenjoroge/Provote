"""
Vote services with idempotency and fingerprint validation logic.
Enhanced with atomic operations, select-for-update locks, and comprehensive validation.
"""

import logging
from typing import Optional, Tuple

from apps.polls.models import Choice, Poll, PollOption
from apps.votes.models import Vote, VoteAttempt
from core.exceptions import (
    CaptchaVerificationError,
    DuplicateVoteError,
    FingerprintValidationError,
    FraudDetectedError,
    IPBlockedError,
    InvalidPollError,
    InvalidVoteError,
    PollClosedError,
    PollNotFoundError,
)
from core.utils.fingerprint_validation import (
    check_fingerprint_ip_combination,
    check_fingerprint_suspicious,
    detect_suspicious_fingerprint_changes,
    require_fingerprint_for_anonymous,
    update_fingerprint_cache,
    validate_fingerprint_format,
)
from core.utils.fraud_detection import detect_fraud, log_fraud_alert
from core.utils.idempotency import (
    check_duplicate_vote_by_idempotency,
    check_idempotency,
    extract_ip_address,
    generate_idempotency_key,
    generate_voter_token,
    store_idempotency_result,
)
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


def cast_vote(
    user: User,
    poll_id: int,
    choice_id: int,
    idempotency_key: Optional[str] = None,
    request=None,
) -> Tuple[Vote, bool]:
    """
    Main voting function with atomic operations and idempotency guarantees.

    This is the core voting service that handles:
    - Idempotency checks (returns existing vote if duplicate)
    - Poll validation (is open, not expired, active)
    - Voter validation (not already voted, IP limits, auth requirements)
    - Select-for-update locks to prevent race conditions
    - Atomic update of denormalized vote counts
    - Cache invalidation
    - Audit logging

    Args:
        user: The authenticated user making the vote
        poll_id: The ID of the poll
        choice_id: The ID of the choice/option
        idempotency_key: Optional idempotency key. If not provided, one will be generated.
        request: Django request object (optional, for fingerprint/IP extraction)

    Returns:
        tuple: (Vote object, is_new: bool)
            - is_new=True if vote was just created
            - is_new=False if existing vote was returned (idempotent retry)

    Raises:
        PollNotFoundError: If the poll doesn't exist
        InvalidPollError: If poll is invalid (not active, expired, not started)
        InvalidVoteError: If the choice doesn't belong to the poll
        PollClosedError: If the poll is closed
        DuplicateVoteError: If the user has already voted on this poll
        FraudDetectedError: If fingerprint validation blocks the vote
    """
    # Step 2: Extract request data (before idempotency key generation)
    fingerprint = getattr(request, "fingerprint", "") if request else ""
    ip_address = None
    user_agent = ""

    if request:
        ip_address = extract_ip_address(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
    
    # Step 2.1: Require fingerprint for anonymous votes
    try:
        is_valid, error_message = require_fingerprint_for_anonymous(user, fingerprint)
        if not is_valid:
            raise FingerprintValidationError(error_message or "Fingerprint validation failed")
    except FingerprintValidationError:
        raise
    except Exception as e:
        logger.error(f"Error checking fingerprint requirement: {e}")
        # Fail open for system errors
    
    # Step 2.2: Validate fingerprint format if provided
    if fingerprint:
        is_valid, error_message = validate_fingerprint_format(fingerprint)
        if not is_valid:
            raise FingerprintValidationError(error_message or "Invalid fingerprint format")
    
    # Generate idempotency key if not provided (now includes fingerprint+IP for anonymous)
    if not idempotency_key:
        user_id = user.id if user and user.is_authenticated else None
        idempotency_key = generate_idempotency_key(
            user_id=user_id,
            poll_id=poll_id,
            choice_id=choice_id,
            fingerprint=fingerprint,
            ip_address=ip_address,
        )

    # Step 1: Idempotency check (fast path - return existing vote if duplicate)
    is_duplicate, cached_result = check_idempotency(idempotency_key)
    if is_duplicate and cached_result:
        try:
            existing_vote = Vote.objects.get(id=cached_result["vote_id"])
            logger.info(f"Idempotent retry: returning existing vote {existing_vote.id}")
            return existing_vote, False  # Not a new vote
        except Vote.DoesNotExist:
            # Cache points to non-existent vote, continue with normal flow
            pass

    # Also check database for duplicate idempotency key
    is_db_duplicate, existing_vote_id = check_duplicate_vote_by_idempotency(idempotency_key)
    if is_db_duplicate:
        try:
            existing_vote = Vote.objects.get(id=existing_vote_id)
            # Store in cache for future fast lookups
            store_idempotency_result(
                idempotency_key,
                {"vote_id": existing_vote.id, "status": "existing"},
            )
            logger.info(f"Idempotent retry: returning existing vote {existing_vote.id} from database")
            return existing_vote, False  # Not a new vote
        except Vote.DoesNotExist:
            pass

    # Step 2.5: Check IP reputation and block status
    if ip_address:
        try:
            from core.utils.ip_reputation import check_ip_reputation
            
            is_allowed, error_message = check_ip_reputation(ip_address)
            if not is_allowed:
                raise IPBlockedError(error_message or "Your IP address has been blocked")
        except IPBlockedError:
            raise
        except Exception as e:
            logger.error(f"Error checking IP reputation: {e}")
            # Fail open - don't block legitimate users if reputation check fails

    # Generate voter token
    voter_token = generate_voter_token(
        user_id=user.id if user and user.is_authenticated else None,
        ip_address=ip_address,
        user_agent=user_agent,
        fingerprint=fingerprint,
    )

    # Step 3: Poll validation with select-for-update lock
    with transaction.atomic():
        try:
            # Use select_for_update to prevent race conditions
            poll = Poll.objects.select_for_update().get(id=poll_id)
        except Poll.DoesNotExist:
            raise PollNotFoundError(f"Poll with id {poll_id} not found")

        # Validate poll is active
        if not poll.is_active:
            raise InvalidPollError(f"Poll {poll_id} is not active")

        # Validate poll has started
        now = timezone.now()
        if poll.starts_at > now:
            raise InvalidPollError(f"Poll {poll_id} has not started yet (starts at {poll.starts_at})")

        # Validate poll has not expired
        if poll.ends_at and poll.ends_at < now:
            raise PollClosedError(f"Poll {poll_id} has expired (ended at {poll.ends_at})")

        # Validate poll is open (combines all checks)
        if not poll.is_open:
            raise PollClosedError(f"Poll {poll_id} is closed")

        # Step 3.5: CAPTCHA verification (if enabled)
        captcha_token = getattr(request, "captcha_token", None) if request else None
        if captcha_token is None and request and hasattr(request, "data"):
            # Try to get from request data
            captcha_token = request.data.get("captcha_token")
        
        try:
            from core.utils.captcha import verify_captcha_for_vote
            
            is_valid, error_message = verify_captcha_for_vote(
                token=captcha_token,
                poll_settings=poll.settings,
                user=user,
                remote_ip=ip_address,
            )
            
            if not is_valid:
                raise CaptchaVerificationError(error_message or "CAPTCHA verification failed")
        except CaptchaVerificationError:
            raise
        except Exception as e:
            logger.error(f"Error during CAPTCHA verification: {e}")
            # If CAPTCHA verification fails due to system error, allow vote
            # (fail open to avoid blocking legitimate users)
            # In production, you might want to be more strict

        # Step 4: Voter validation
        # Check if user has already voted on this poll (with lock)
        # For anonymous users, check by voter_token instead
        if user and user.is_authenticated:
            existing_vote = Vote.objects.select_for_update().filter(user=user, poll=poll).first()
        else:
            # Anonymous user - check by voter_token (will be set after generation)
            existing_vote = None
        
        # Re-check after voter_token is generated for anonymous users
        if not existing_vote and not (user and user.is_authenticated):
            # For anonymous users, check by idempotency_key which includes fingerprint+IP
            existing_vote = Vote.objects.select_for_update().filter(
                idempotency_key=idempotency_key, poll=poll
            ).first()
        
        if existing_vote:
            # Record IP violation for duplicate vote attempt
            if ip_address:
                try:
                    from core.utils.ip_reputation import record_ip_violation
                    record_ip_violation(
                        ip_address=ip_address,
                        reason="Duplicate vote attempt",
                        severity=1,
                    )
                except Exception as e:
                    logger.error(f"Error recording IP violation: {e}")
            
            # Store result for idempotency
            store_idempotency_result(
                idempotency_key,
                {"vote_id": existing_vote.id, "status": "duplicate"},
            )
            raise DuplicateVoteError(
                f"User {user.username} has already voted on poll {poll_id}"
            )

        # Check IP limits if configured in security_rules
        if ip_address and poll.security_rules.get("max_votes_per_ip"):
            max_votes = poll.security_rules.get("max_votes_per_ip")
            ip_vote_count = Vote.objects.filter(poll=poll, ip_address=ip_address).count()
            if ip_vote_count >= max_votes:
                raise InvalidVoteError(
                    f"IP address {ip_address} has reached the maximum vote limit ({max_votes}) for this poll"
                )

        # Check authentication requirement
        if poll.security_rules.get("require_authentication", False):
            if not user or not user.is_authenticated:
                raise InvalidVoteError("This poll requires authentication")

        # Step 5: Get and validate choice with lock
        try:
            option = PollOption.objects.select_for_update().get(id=choice_id, poll=poll)
        except PollOption.DoesNotExist:
            raise InvalidVoteError(f"Choice {choice_id} does not belong to poll {poll_id}")

        # Step 6: Fingerprint validation and suspicious change detection
        fingerprint_missing = False
        fraud_reasons_list = []
        
        if fingerprint:
            try:
                # Check for suspicious fingerprint patterns
                validation_result = check_fingerprint_suspicious(
                    fingerprint=fingerprint,
                    poll_id=poll_id,
                    user_id=user.id if user and user.is_authenticated else None,
                    ip_address=ip_address,
                    request=request,
                )

                # Block vote if critical suspicious pattern detected
                if validation_result.get("block_vote", False):
                    # Log to VoteAttempt
                    VoteAttempt.objects.create(
                        user=user,
                        poll=poll,
                        option=option,
                        voter_token=voter_token,
                        idempotency_key=idempotency_key,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        fingerprint=fingerprint,
                        success=False,
                        error_message=f"Fingerprint validation failed: {', '.join(validation_result.get('reasons', []))}",
                    )

                    raise FraudDetectedError(
                        f"Vote blocked due to suspicious activity: {', '.join(validation_result.get('reasons', []))}"
                    )

                # Check for suspicious fingerprint changes
                user_id = user.id if user and user.is_authenticated else None
                change_result = detect_suspicious_fingerprint_changes(
                    fingerprint=fingerprint,
                    user_id=user_id,
                    ip_address=ip_address,
                    poll_id=poll_id,
                )
                
                if change_result.get("block_vote", False):
                    raise FraudDetectedError(
                        f"Vote blocked due to suspicious fingerprint changes: {', '.join(change_result.get('reasons', []))}"
                    )
                
                if change_result.get("suspicious", False):
                    fraud_reasons_list.extend(change_result.get("reasons", []))

                # Check fingerprint+IP combination
                ip_combo_result = check_fingerprint_ip_combination(
                    fingerprint=fingerprint,
                    ip_address=ip_address,
                    poll_id=poll_id,
                )
                
                if ip_combo_result.get("block_vote", False):
                    raise FraudDetectedError(
                        f"Vote blocked: {', '.join(ip_combo_result.get('reasons', []))}"
                    )
                
                if ip_combo_result.get("suspicious", False):
                    fraud_reasons_list.extend(ip_combo_result.get("reasons", []))

                # Log warning if suspicious but not blocking
                if validation_result.get("suspicious", False):
                    logger.warning(
                        f"Suspicious fingerprint detected for user {user.id if user and user.is_authenticated else 'anonymous'}, poll {poll_id}: "
                        f"{', '.join(validation_result.get('reasons', []))}"
                    )

                    # Trigger async analysis (Tier 3)
                    try:
                        from apps.votes.tasks import analyze_fingerprint_patterns

                        analyze_fingerprint_patterns.delay(fingerprint, poll_id)
                    except Exception as e:
                        logger.error(f"Failed to trigger async fingerprint analysis: {e}")

            except (InvalidVoteError, FraudDetectedError, FingerprintValidationError):
                raise
            except Exception as e:
                logger.error(f"Error in fingerprint validation: {e}")
                # Don't block vote if validation fails, but log error
        else:
            # Flag vote with missing fingerprint
            fingerprint_missing = True
            fraud_reasons_list.append("Missing browser fingerprint")
            logger.warning(
                f"Vote from user {user.id if user and user.is_authenticated else 'anonymous'} (IP: {ip_address}) missing fingerprint"
            )

        # Step 7: Fraud detection
        fraud_result = detect_fraud(
            poll_id=poll_id,
            option_id=option.id,
            user_id=user.id if user else None,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=fingerprint,
            request=request,
        )
        
        # Combine fraud reasons from fingerprint validation and fraud detection
        all_fraud_reasons = fraud_reasons_list + fraud_result.get("reasons", [])
        
        # Mark vote as invalid if fingerprint is missing (for anonymous votes) or fraud detected
        should_mark_invalid = (
            fraud_result.get("should_mark_invalid", False) or
            (fingerprint_missing and (not user or not user.is_authenticated))
        )

        # Step 8: Create vote atomically
        # For anonymous users, user is None (Vote.user now allows null)
        vote_user = user if user and user.is_authenticated else None
        vote = Vote.objects.create(
            user=vote_user,
            option=option,
            poll=poll,
            idempotency_key=idempotency_key,
            voter_token=voter_token,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=fingerprint or "",  # Store empty string if missing
            is_valid=not should_mark_invalid,
            fraud_reasons=", ".join(all_fraud_reasons) if all_fraud_reasons else "",
            risk_score=fraud_result["risk_score"],
        )

        # Log fraud alert if fraud detected
        if fraud_result["is_fraud"] or fraud_result["should_mark_invalid"]:
            try:
                log_fraud_alert(
                    vote_id=vote.id,
                    reasons=fraud_result["reasons"],
                    risk_score=fraud_result["risk_score"],
                    poll_id=poll_id,
                    user_id=user.id if user and user.is_authenticated else None,
                    ip_address=ip_address,
                )
                
                # Notify user that their vote was flagged
                if user and vote.is_valid is False:
                    try:
                        from apps.notifications.services import notify_vote_flagged
                        notify_vote_flagged(vote, fraud_result["reasons"])
                    except Exception as e:
                        logger.error(f"Error sending vote flagged notification: {e}")
            except Exception as e:
                logger.error(f"Error logging fraud alert: {e}")

        # Step 9: Update denormalized vote counts atomically (only for valid votes)
        if vote.is_valid:
            # Update option cached vote count
            PollOption.objects.filter(id=option.id).update(
                cached_vote_count=F("cached_vote_count") + 1
            )

            # Update poll cached totals
            Poll.objects.filter(id=poll.id).update(
                cached_total_votes=F("cached_total_votes") + 1
            )

            # Update unique voters count (only if this is first vote from this user)
            # We already checked for existing vote, so this is a new voter
            Poll.objects.filter(id=poll.id).update(
                cached_unique_voters=F("cached_unique_voters") + 1
            )

        # Step 10: Update fingerprint cache
        if fingerprint:
            try:
                update_fingerprint_cache(
                    fingerprint=fingerprint,
                    poll_id=poll_id,
                    user_id=user.id if user and user.is_authenticated else None,
                    ip_address=ip_address,
                )
            except Exception as e:
                logger.error(f"Error updating fingerprint cache: {e}")

        # Step 11: Store idempotency result
        store_idempotency_result(
            idempotency_key,
            {"vote_id": vote.id, "status": "created"},
        )

        # Step 12: Invalidate cache (if any poll/option caches exist)
        cache_keys_to_invalidate = [
            f"poll:{poll.id}",
            f"poll:{poll.id}:results",
            f"option:{option.id}:votes",
        ]
        for key in cache_keys_to_invalidate:
            try:
                cache.delete(key)
            except Exception:
                pass

        # Invalidate results cache
        try:
            from apps.polls.services import invalidate_results_cache

            invalidate_results_cache(poll.id)
        except Exception as e:
            logger.error(f"Error invalidating results cache: {e}")

        # Publish vote event to Redis Pub/Sub for multi-server scaling
        try:
            from core.utils.redis_pubsub import publish_vote_event

            publish_vote_event(poll.id, vote.id)
        except Exception as e:
            logger.error(f"Error publishing vote event to Redis: {e}")

        # Step 13: Audit logging
        VoteAttempt.objects.create(
            user=user if user and user.is_authenticated else None,
            poll=poll,
            option=option,
            voter_token=voter_token,
            idempotency_key=idempotency_key,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=fingerprint,
            success=True,
        )

        logger.info(f"Vote created successfully: vote_id={vote.id}, poll_id={poll_id}, user_id={user.id if user and user.is_authenticated else None}")
        
        # Record successful IP activity
        if ip_address:
            try:
                from core.utils.ip_reputation import record_ip_success
                record_ip_success(ip_address)
            except Exception as e:
                logger.error(f"Error recording IP success: {e}")

    return vote, True  # New vote created


# Backward compatibility alias
def create_vote(
    user: User,
    poll_id: int,
    choice_id: int,
    idempotency_key: Optional[str] = None,
    request=None,
) -> Vote:
    """
    Backward compatibility wrapper for cast_vote().
    Returns only the Vote object (not the tuple).

    Args:
        user: The user making the vote
        poll_id: The ID of the poll
        choice_id: The ID of the choice
        idempotency_key: Optional idempotency key
        request: Django request object (optional)

    Returns:
        Vote: The created or existing vote
    """
    vote, _ = cast_vote(user, poll_id, choice_id, idempotency_key, request)
    return vote
