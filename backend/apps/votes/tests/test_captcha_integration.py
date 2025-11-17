"""
Integration tests for CAPTCHA verification in vote casting.
"""

import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient

from apps.polls.models import Poll, PollOption
from core.exceptions import CaptchaVerificationError


@pytest.mark.django_db
class TestCaptchaIntegration:
    """Integration tests for CAPTCHA in vote casting."""

    def test_valid_captcha_accepted(self, user, poll, choices):
        """Test that valid CAPTCHA token is accepted."""
        # Enable CAPTCHA for poll
        poll.settings = {"enable_captcha": True}
        poll.save()
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        with patch("core.utils.captcha.verify_recaptcha_token") as mock_verify:
            mock_verify.return_value = {
                "success": True,
                "score": 0.9,
                "action": "vote",
            }
            
            response = client.post(
                "/api/v1/votes/cast/",
                {
                    "poll_id": poll.id,
                    "choice_id": choices[0].id,
                    "captcha_token": "valid_token",
                },
                format="json"
            )
            
            # Should succeed (may be 201, 200, or 409 depending on vote status)
            assert response.status_code in [201, 200, 409]
            mock_verify.assert_called_once()

    def test_invalid_captcha_rejected(self, user, poll, choices):
        """Test that invalid CAPTCHA token is rejected."""
        # Enable CAPTCHA for poll
        poll.settings = {"enable_captcha": True}
        poll.save()
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        with patch("core.utils.captcha.verify_recaptcha_token") as mock_verify:
            mock_verify.return_value = {
                "success": False,
                "error_codes": ["invalid-input-response"],
            }
            
            response = client.post(
                "/api/v1/votes/cast/",
                {
                    "poll_id": poll.id,
                    "choice_id": choices[0].id,
                    "captcha_token": "invalid_token",
                },
                format="json"
            )
            
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert response.data["error_code"] == "CaptchaVerificationError"
            assert "CAPTCHA" in response.data["error"]

    def test_missing_captcha_rejected_when_required(self, user, poll, choices):
        """Test that missing CAPTCHA token is rejected when required."""
        # Enable CAPTCHA for poll
        poll.settings = {"enable_captcha": True}
        poll.save()
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.post(
            "/api/v1/votes/cast/",
            {
                "poll_id": poll.id,
                "choice_id": choices[0].id,
                # No captcha_token
            },
            format="json"
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error_code"] == "CaptchaVerificationError"
        assert "required" in response.data["error"].lower()

    def test_captcha_bypass_for_trusted_users(self, poll, choices):
        """Test that trusted users bypass CAPTCHA."""
        # Create staff user
        staff_user = User.objects.create_user(
            username="staff",
            password="staffpass",
            is_staff=True,
        )
        
        # Enable CAPTCHA for poll
        poll.settings = {"enable_captcha": True}
        poll.save()
        
        client = APIClient()
        client.force_authenticate(user=staff_user)
        
        with patch("core.utils.captcha.verify_recaptcha_token") as mock_verify:
            response = client.post(
                "/api/v1/votes/cast/",
                {
                    "poll_id": poll.id,
                    "choice_id": choices[0].id,
                    # No captcha_token - should be bypassed
                },
                format="json"
            )
            
            # Should succeed without CAPTCHA
            assert response.status_code in [201, 200, 409]
            # Should not call verify_recaptcha_token
            mock_verify.assert_not_called()

    def test_captcha_not_required_when_flag_disabled(self, user, poll, choices):
        """Test that CAPTCHA is not required when flag is disabled."""
        # Disable CAPTCHA for poll
        poll.settings = {"enable_captcha": False}
        poll.save()
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        with patch("core.utils.captcha.verify_recaptcha_token") as mock_verify:
            response = client.post(
                "/api/v1/votes/cast/",
                {
                    "poll_id": poll.id,
                    "choice_id": choices[0].id,
                    # No captcha_token
                },
                format="json"
            )
            
            # Should succeed without CAPTCHA
            assert response.status_code in [201, 200, 409]
            # Should not call verify_recaptcha_token
            mock_verify.assert_not_called()

    def test_captcha_low_score_rejected(self, user, poll, choices):
        """Test that low CAPTCHA score is rejected."""
        # Enable CAPTCHA for poll
        poll.settings = {"enable_captcha": True}
        poll.save()
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        with patch("core.utils.captcha.verify_recaptcha_token") as mock_verify:
            mock_verify.return_value = {
                "success": True,
                "score": 0.2,  # Below default threshold of 0.5
            }
            
            response = client.post(
                "/api/v1/votes/cast/",
                {
                    "poll_id": poll.id,
                    "choice_id": choices[0].id,
                    "captcha_token": "low_score_token",
                },
                format="json"
            )
            
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert response.data["error_code"] == "CaptchaVerificationError"
            assert "score" in response.data["error"].lower()

    def test_captcha_default_settings(self, user, poll, choices):
        """Test CAPTCHA with default poll settings (not explicitly set)."""
        # Poll settings don't have enable_captcha (defaults to False)
        poll.settings = {}
        poll.save()
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        with patch("core.utils.captcha.verify_recaptcha_token") as mock_verify:
            response = client.post(
                "/api/v1/votes/cast/",
                {
                    "poll_id": poll.id,
                    "choice_id": choices[0].id,
                },
                format="json"
            )
            
            # Should succeed without CAPTCHA
            assert response.status_code in [201, 200, 409]
            mock_verify.assert_not_called()

