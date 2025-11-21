"""
Tests for geographic restrictions in voting.
"""

import pytest
from unittest.mock import patch, MagicMock
from django.test import RequestFactory
from django.contrib.auth.models import User

from apps.polls.models import Poll, PollOption
from apps.votes.services import cast_vote
from apps.votes.models import Vote, VoteAttempt
from core.exceptions import InvalidVoteError


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(username="testuser", password="testpass123")


@pytest.fixture
def poll_with_geographic_restrictions(db, user):
    """Create a poll with geographic restrictions."""
    poll = Poll.objects.create(
        title="Geographic Restricted Poll",
        description="Test poll with geographic restrictions",
        created_by=user,
        is_active=True,
        security_rules={
            "allowed_countries": ["US", "CA", "GB"],
            "blocked_countries": ["CN", "RU"],
        },
    )
    option1 = PollOption.objects.create(poll=poll, text="Option 1", order=0)
    option2 = PollOption.objects.create(poll=poll, text="Option 2", order=1)
    return poll, [option1, option2]


@pytest.fixture
def poll_with_region_restrictions(db, user):
    """Create a poll with region restrictions."""
    poll = Poll.objects.create(
        title="Region Restricted Poll",
        description="Test poll with region restrictions",
        created_by=user,
        is_active=True,
        security_rules={
            "allowed_regions": ["CA", "NY"],
            "blocked_regions": ["TX"],
        },
    )
    option1 = PollOption.objects.create(poll=poll, text="Option 1", order=0)
    return poll, [option1]


@pytest.fixture
def request_factory():
    """Create a request factory."""
    return RequestFactory()


class TestGeographicRestrictions:
    """Test geographic restrictions in voting."""
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_vote_allowed_from_allowed_country(self, mock_get_country, poll_with_geographic_restrictions, user, request_factory):
        """Test that voting is allowed from an allowed country."""
        poll, options = poll_with_geographic_restrictions
        mock_get_country.return_value = "US"
        
        request = request_factory.post("/api/v1/votes/cast/")
        request.META["REMOTE_ADDR"] = "8.8.8.8"
        request.fingerprint = "a" * 64  # Valid 64-character SHA256 hex fingerprint
        
        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=options[0].id,
            request=request,
        )
        
        assert is_new is True
        assert vote.poll == poll
        assert vote.option == options[0]
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_vote_blocked_from_blocked_country(self, mock_get_country, poll_with_geographic_restrictions, user, request_factory):
        """Test that voting is blocked from a blocked country."""
        poll, options = poll_with_geographic_restrictions
        mock_get_country.return_value = "CN"
        
        request = request_factory.post("/api/v1/votes/cast/")
        request.META["REMOTE_ADDR"] = "8.8.8.8"
        request.fingerprint = "a" * 64  # Valid 64-character SHA256 hex fingerprint
        
        with pytest.raises(InvalidVoteError) as exc_info:
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=options[0].id,
                request=request,
            )
        
        assert "not allowed from" in str(exc_info.value).lower() or "CN" in str(exc_info.value)
        
        # Check that VoteAttempt was created
        attempt = VoteAttempt.objects.filter(poll=poll, success=False).first()
        assert attempt is not None
        assert "geographic" in attempt.error_message.lower() or "not allowed" in attempt.error_message.lower()
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_vote_blocked_from_not_allowed_country(self, mock_get_country, poll_with_geographic_restrictions, user, request_factory):
        """Test that voting is blocked from a country not in allowed list."""
        poll, options = poll_with_geographic_restrictions
        mock_get_country.return_value = "FR"
        
        request = request_factory.post("/api/v1/votes/cast/")
        request.META["REMOTE_ADDR"] = "8.8.8.8"
        request.fingerprint = "a" * 64  # Valid 64-character SHA256 hex fingerprint
        
        with pytest.raises(InvalidVoteError) as exc_info:
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=options[0].id,
                request=request,
            )
        
        assert "only allowed from" in str(exc_info.value).lower() or "not allowed" in str(exc_info.value).lower()
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_vote_allowed_when_no_restrictions(self, mock_get_country, db, user, request_factory):
        """Test that voting is allowed when no geographic restrictions are set."""
        poll = Poll.objects.create(
            title="No Restrictions Poll",
            description="Test poll without restrictions",
            created_by=user,
            is_active=True,
            security_rules={},  # No restrictions
        )
        option = PollOption.objects.create(poll=poll, text="Option 1", order=0)
        
        request = request_factory.post("/api/v1/votes/cast/")
        request.META["REMOTE_ADDR"] = "8.8.8.8"
        request.fingerprint = "a" * 64  # Valid 64-character SHA256 hex fingerprint
        
        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=option.id,
            request=request,
        )
        
        assert is_new is True
        # Should not have called geolocation
        mock_get_country.assert_not_called()
    
    @patch('core.utils.geolocation.get_country_from_ip')
    def test_vote_allowed_from_private_ip(self, mock_get_country, poll_with_geographic_restrictions, user, request_factory):
        """Test that voting from private IP is allowed (geolocation returns None)."""
        poll, options = poll_with_geographic_restrictions
        mock_get_country.return_value = None  # Private IPs return None
        
        request = request_factory.post("/api/v1/votes/cast/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"  # Private IP
        request.fingerprint = "a" * 64  # Valid 64-character SHA256 hex fingerprint
        
        # Should fail because we can't determine country and restrictions are set
        with pytest.raises(InvalidVoteError) as exc_info:
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=options[0].id,
                request=request,
            )
        
        assert "could not determine" in str(exc_info.value).lower() or "not allowed" in str(exc_info.value).lower()
    
    @patch('core.utils.geolocation.get_country_from_ip')
    @patch('core.utils.geolocation.get_region_from_ip')
    def test_vote_allowed_from_allowed_region(self, mock_get_region, mock_get_country, poll_with_region_restrictions, user, request_factory):
        """Test that voting is allowed from an allowed region."""
        poll, options = poll_with_region_restrictions
        mock_get_country.return_value = "US"
        mock_get_region.return_value = "CA"
        
        request = request_factory.post("/api/v1/votes/cast/")
        request.META["REMOTE_ADDR"] = "8.8.8.8"
        request.fingerprint = "a" * 64  # Valid 64-character SHA256 hex fingerprint
        
        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=options[0].id,
            request=request,
        )
        
        assert is_new is True
        assert vote.poll == poll
    
    @patch('core.utils.geolocation.get_country_from_ip')
    @patch('core.utils.geolocation.get_region_from_ip')
    def test_vote_blocked_from_blocked_region(self, mock_get_region, mock_get_country, poll_with_region_restrictions, user, request_factory):
        """Test that voting is blocked from a blocked region."""
        poll, options = poll_with_region_restrictions
        mock_get_country.return_value = "US"
        mock_get_region.return_value = "TX"
        
        request = request_factory.post("/api/v1/votes/cast/")
        request.META["REMOTE_ADDR"] = "8.8.8.8"
        request.fingerprint = "a" * 64  # Valid 64-character SHA256 hex fingerprint
        
        with pytest.raises(InvalidVoteError) as exc_info:
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=options[0].id,
                request=request,
            )
        
        assert "not allowed from region" in str(exc_info.value).lower() or "not allowed" in str(exc_info.value).lower()
    
    @patch('core.utils.geolocation.get_country_from_ip')
    @patch('core.utils.geolocation.get_region_from_ip')
    def test_vote_blocked_from_not_allowed_region(self, mock_get_region, mock_get_country, poll_with_region_restrictions, user, request_factory):
        """Test that voting is blocked from a region not in allowed list."""
        poll, options = poll_with_region_restrictions
        mock_get_country.return_value = "US"
        mock_get_region.return_value = "FL"
        
        request = request_factory.post("/api/v1/votes/cast/")
        request.META["REMOTE_ADDR"] = "8.8.8.8"
        request.fingerprint = "a" * 64  # Valid 64-character SHA256 hex fingerprint
        
        with pytest.raises(InvalidVoteError) as exc_info:
            cast_vote(
                user=user,
                poll_id=poll.id,
                choice_id=options[0].id,
                request=request,
            )
        
        assert "only allowed from regions" in str(exc_info.value).lower() or "not allowed" in str(exc_info.value).lower()
    
    @patch('core.utils.geolocation.validate_geographic_restriction')
    def test_geographic_restriction_error_handling(self, mock_validate, poll_with_geographic_restrictions, user, request_factory):
        """Test that geolocation errors don't block votes (fail open)."""
        poll, options = poll_with_geographic_restrictions
        mock_validate.side_effect = Exception("Geolocation service error")
        
        request = request_factory.post("/api/v1/votes/cast/")
        request.META["REMOTE_ADDR"] = "8.8.8.8"
        request.fingerprint = "a" * 64  # Valid 64-character SHA256 hex fingerprint
        
        # Should allow vote despite geolocation error (fail open)
        vote, is_new = cast_vote(
            user=user,
            poll_id=poll.id,
            choice_id=options[0].id,
            request=request,
        )
        
        assert is_new is True

