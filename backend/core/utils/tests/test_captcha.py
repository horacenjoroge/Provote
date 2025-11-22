"""
Tests for CAPTCHA verification utility.
"""

from unittest.mock import MagicMock, Mock, patch

from core.exceptions import CaptchaVerificationError
from core.utils.captcha import (
    DEFAULT_MIN_SCORE,
    verify_captcha_for_vote,
    verify_recaptcha_token,
)
from django.contrib.auth.models import User


class TestVerifyRecaptchaToken:
    """Tests for verify_recaptcha_token function."""

    @patch("core.utils.captcha.requests.post")
    def test_verify_recaptcha_token_success(self, mock_post):
        """Test successful CAPTCHA verification."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "score": 0.9,
            "action": "vote",
            "challenge_ts": "2024-01-01T00:00:00Z",
            "hostname": "example.com",
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with patch("django.conf.settings.RECAPTCHA_SECRET_KEY", "test_secret"):
            result = verify_recaptcha_token("test_token", "192.168.1.1")

        assert result["success"] is True
        assert result["score"] == 0.9
        assert result["action"] == "vote"
        mock_post.assert_called_once()

    @patch("core.utils.captcha.requests.post")
    def test_verify_recaptcha_token_low_score(self, mock_post):
        """Test CAPTCHA verification with low score."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "score": 0.3,  # Low score
            "action": "vote",
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with patch("django.conf.settings.RECAPTCHA_SECRET_KEY", "test_secret"):
            result = verify_recaptcha_token("test_token")

        assert result["success"] is True
        assert result["score"] == 0.3

    @patch("core.utils.captcha.requests.post")
    def test_verify_recaptcha_token_failure(self, mock_post):
        """Test CAPTCHA verification failure."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": False,
            "error-codes": ["invalid-input-response"],
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with patch("django.conf.settings.RECAPTCHA_SECRET_KEY", "test_secret"):
            result = verify_recaptcha_token("invalid_token")

        assert result["success"] is False
        assert "invalid-input-response" in result["error_codes"]

    @patch("django.conf.settings.RECAPTCHA_SECRET_KEY", None)
    def test_verify_recaptcha_token_no_secret_key(self):
        """Test CAPTCHA verification without secret key."""
        result = verify_recaptcha_token("test_token")

        assert result["success"] is False
        assert "missing-secret-key" in result["error_codes"]

    def test_verify_recaptcha_token_no_token(self):
        """Test CAPTCHA verification without token."""
        with patch("django.conf.settings.RECAPTCHA_SECRET_KEY", "test_secret"):
            result = verify_recaptcha_token("")

        assert result["success"] is False
        assert "missing-input-response" in result["error_codes"]

    @patch("core.utils.captcha.requests.post")
    def test_verify_recaptcha_token_network_error(self, mock_post):
        """Test CAPTCHA verification with network error."""
        import requests

        mock_post.side_effect = requests.exceptions.RequestException("Network error")

        with patch("django.conf.settings.RECAPTCHA_SECRET_KEY", "test_secret"):
            result = verify_recaptcha_token("test_token")

        assert result["success"] is False
        assert "network-error" in result["error_codes"]


class TestVerifyCaptchaForVote:
    """Tests for verify_captcha_for_vote function."""

    def test_captcha_not_required(self):
        """Test that CAPTCHA is not required when flag is disabled."""
        poll_settings = {"enable_captcha": False}

        is_valid, error = verify_captcha_for_vote(
            token=None,
            poll_settings=poll_settings,
        )

        assert is_valid is True
        assert error is None

    def test_captcha_required_but_missing(self):
        """Test that CAPTCHA is required but token is missing."""
        poll_settings = {"enable_captcha": True}

        is_valid, error = verify_captcha_for_vote(
            token=None,
            poll_settings=poll_settings,
        )

        assert is_valid is False
        assert "required" in error.lower()

    @patch("core.utils.captcha.verify_recaptcha_token")
    def test_captcha_valid_token(self, mock_verify):
        """Test valid CAPTCHA token."""
        mock_verify.return_value = {
            "success": True,
            "score": 0.9,
            "action": "vote",
        }

        poll_settings = {"enable_captcha": True}

        is_valid, error = verify_captcha_for_vote(
            token="valid_token",
            poll_settings=poll_settings,
        )

        assert is_valid is True
        assert error is None

    @patch("core.utils.captcha.verify_recaptcha_token")
    def test_captcha_invalid_token(self, mock_verify):
        """Test invalid CAPTCHA token."""
        mock_verify.return_value = {
            "success": False,
            "error_codes": ["invalid-input-response"],
        }

        poll_settings = {"enable_captcha": True}

        is_valid, error = verify_captcha_for_vote(
            token="invalid_token",
            poll_settings=poll_settings,
        )

        assert is_valid is False
        assert "failed" in error.lower()

    @patch("core.utils.captcha.verify_recaptcha_token")
    def test_captcha_low_score(self, mock_verify):
        """Test CAPTCHA with low score."""
        mock_verify.return_value = {
            "success": True,
            "score": 0.2,  # Below default threshold of 0.5
        }

        poll_settings = {"enable_captcha": True}

        is_valid, error = verify_captcha_for_vote(
            token="low_score_token",
            poll_settings=poll_settings,
        )

        assert is_valid is False
        assert "score" in error.lower()

    @patch("core.utils.captcha.verify_recaptcha_token")
    def test_captcha_trusted_user_bypass(self, mock_verify):
        """Test that trusted users bypass CAPTCHA."""
        user = Mock()
        user.is_staff = True
        user.is_superuser = False

        poll_settings = {"enable_captcha": True}

        is_valid, error = verify_captcha_for_vote(
            token=None,
            poll_settings=poll_settings,
            user=user,
        )

        assert is_valid is True
        assert error is None
        # Should not call verify_recaptcha_token
        mock_verify.assert_not_called()

    @patch("core.utils.captcha.verify_recaptcha_token")
    def test_captcha_superuser_bypass(self, mock_verify):
        """Test that superusers bypass CAPTCHA."""
        user = Mock()
        user.is_staff = False
        user.is_superuser = True

        poll_settings = {"enable_captcha": True}

        is_valid, error = verify_captcha_for_vote(
            token=None,
            poll_settings=poll_settings,
            user=user,
        )

        assert is_valid is True
        assert error is None
        mock_verify.assert_not_called()

    @patch("core.utils.captcha.verify_recaptcha_token")
    def test_captcha_custom_min_score(self, mock_verify):
        """Test CAPTCHA with custom minimum score."""
        mock_verify.return_value = {
            "success": True,
            "score": 0.6,  # Above custom threshold of 0.7
        }

        poll_settings = {"enable_captcha": True}

        is_valid, error = verify_captcha_for_vote(
            token="token",
            poll_settings=poll_settings,
            min_score=0.7,
        )

        assert is_valid is False
        assert "score" in error.lower()
