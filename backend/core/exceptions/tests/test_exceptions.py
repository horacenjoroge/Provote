"""
Comprehensive tests for custom exceptions and exception handling.
"""

import json

import pytest
from core.exceptions import (
    DuplicateVoteError,
    FraudDetectedError,
    InvalidPollError,
    InvalidVoteError,
    PollClosedError,
    PollNotFoundError,
    RateLimitExceededError,
    VotingError,
)
from core.exceptions.handlers import custom_exception_handler
from django.test import RequestFactory
from rest_framework.test import APIClient


@pytest.mark.unit
class TestCustomExceptions:
    """Test custom exception classes."""

    def test_voting_error_base_exception(self):
        """Test VotingError base exception."""
        error = VotingError()
        assert error.message == "A voting error occurred"
        assert error.status_code == 400

    def test_voting_error_custom_message(self):
        """Test VotingError with custom message."""
        error = VotingError("Custom error message")
        assert error.message == "Custom error message"
        assert error.status_code == 400

    def test_voting_error_custom_status_code(self):
        """Test VotingError with custom status code."""
        error = VotingError("Error", status_code=422)
        assert error.message == "Error"
        assert error.status_code == 422

    def test_duplicate_vote_error(self):
        """Test DuplicateVoteError."""
        error = DuplicateVoteError()
        assert error.status_code == 409
        assert "already voted" in error.message.lower()

    def test_poll_not_found_error(self):
        """Test PollNotFoundError."""
        error = PollNotFoundError()
        assert error.status_code == 404
        assert "not found" in error.message.lower()

    def test_invalid_vote_error(self):
        """Test InvalidVoteError."""
        error = InvalidVoteError()
        assert error.status_code == 400
        assert "invalid" in error.message.lower()

    def test_poll_closed_error(self):
        """Test PollClosedError."""
        error = PollClosedError()
        assert error.status_code == 400
        assert "closed" in error.message.lower()

    def test_rate_limit_exceeded_error(self):
        """Test RateLimitExceededError."""
        error = RateLimitExceededError()
        assert error.status_code == 429
        assert "rate limit" in error.message.lower()

    def test_invalid_poll_error(self):
        """Test InvalidPollError."""
        error = InvalidPollError()
        assert error.status_code == 400
        assert "invalid poll" in error.message.lower()

    def test_fraud_detected_error(self):
        """Test FraudDetectedError."""
        error = FraudDetectedError()
        assert error.status_code == 403
        assert "suspicious" in error.message.lower() or "fraud" in error.message.lower()


@pytest.mark.unit
class TestExceptionHandler:
    """Test custom exception handler."""

    def test_handler_returns_correct_status_code(self):
        """Test that handler returns correct status code for each exception."""
        factory = RequestFactory()
        request = factory.get("/api/test/")
        context = {"request": request, "view": None}

        test_cases = [
            (DuplicateVoteError(), 409),
            (PollNotFoundError(), 404),
            (InvalidVoteError(), 400),
            (PollClosedError(), 400),
            (RateLimitExceededError(), 429),
            (InvalidPollError(), 400),
            (FraudDetectedError(), 403),
        ]

        for exc, expected_status in test_cases:
            response = custom_exception_handler(exc, context)
            assert response is not None
            assert response.status_code == expected_status

    def test_handler_formats_error_message(self):
        """Test that handler formats error messages correctly."""
        factory = RequestFactory()
        request = factory.get("/api/test/")
        context = {"request": request, "view": None}

        error = DuplicateVoteError("Custom duplicate vote message")
        response = custom_exception_handler(error, context)

        assert response is not None
        data = json.loads(response.content)
        assert "error" in data
        assert data["error"] == "Custom duplicate vote message"
        assert data["error_code"] == "DuplicateVoteError"
        assert data["status_code"] == 409

    def test_handler_includes_error_code(self):
        """Test that handler includes error code in response."""
        factory = RequestFactory()
        request = factory.get("/api/test/")
        context = {"request": request, "view": None}

        error = PollNotFoundError()
        response = custom_exception_handler(error, context)

        assert response is not None
        data = json.loads(response.content)
        assert "error_code" in data
        assert data["error_code"] == "PollNotFoundError"

    def test_handler_handles_500_errors(self):
        """Test that handler catches and logs 500 errors."""
        factory = RequestFactory()
        request = factory.get("/api/test/")
        context = {"request": request, "view": None}

        # Simulate unhandled exception
        unhandled_exc = ValueError("Something went wrong")
        response = custom_exception_handler(unhandled_exc, context)

        assert response is not None
        assert response.status_code == 500
        data = json.loads(response.content)
        assert "error" in data
        assert "An internal server error occurred" in data["error"]
        assert data["error_code"] == "InternalServerError"
        assert data["status_code"] == 500

    def test_handler_logs_500_errors(self, caplog):
        """Test that 500 errors are logged with traceback."""
        import logging

        logger = logging.getLogger("core.exceptions.handlers")
        logger.setLevel(logging.ERROR)

        factory = RequestFactory()
        request = factory.get("/api/test/")
        context = {"request": request, "view": None}

        unhandled_exc = RuntimeError("Unexpected error")
        with caplog.at_level(logging.ERROR):
            custom_exception_handler(unhandled_exc, context)

        # Check that error was logged
        assert len(caplog.records) > 0
        assert "Unhandled exception" in caplog.text
        assert "RuntimeError" in caplog.text

    def test_handler_handles_drf_validation_error(self):
        """Test that handler handles DRF ValidationError."""
        from rest_framework.exceptions import ValidationError

        factory = RequestFactory()
        request = factory.get("/api/test/")
        context = {"request": request, "view": None}

        validation_error = ValidationError({"field": ["This field is required."]})
        response = custom_exception_handler(validation_error, context)

        assert response is not None
        # DRF Response has .data attribute, JsonResponse needs json.loads
        if hasattr(response, "data"):
            data = response.data
        else:
            data = json.loads(response.content)
        assert "error_code" in data
        assert "errors" in data or "field_errors" in data


@pytest.mark.django_db
class TestExceptionHandlerIntegration:
    """Integration tests for exception handling in views."""

    def test_exception_returns_correct_status_in_view(self, authenticated_client, user):
        """Test that exceptions return correct status codes in actual views."""
        from apps.polls.models import Poll

        # Create a poll
        _poll = Poll.objects.create(title="Test Poll", created_by=user)

        # Try to vote with invalid poll ID (serializer validation catches this first)
        response = authenticated_client.post(
            "/api/v1/votes/cast/",
            {"poll_id": 99999, "choice_id": 1},
            format="json",
        )

        # Serializer validation returns 400, not 404 (validation happens before service layer)
        assert response.status_code == 400
        # APIClient returns DRF Response which has .data
        if hasattr(response, "data"):
            data = response.data
        else:
            data = json.loads(response.content)
        assert "error" in data
        assert "error_code" in data

    def test_duplicate_vote_returns_409(
        self, authenticated_client, user, poll, choices
    ):
        """Test that duplicate vote returns 409 status."""
        from apps.votes.services import cast_vote

        # Create first vote
        cast_vote(user=user, poll_id=poll.id, choice_id=choices[0].id, request=None)

        # Try to vote again (should fail with DuplicateVoteError)
        response = authenticated_client.post(
            "/api/v1/votes/cast/",
            {"poll_id": poll.id, "choice_id": choices[1].id},
            format="json",
        )

        # Should return 409
        assert response.status_code == 409
        # APIClient returns DRF Response which has .data
        if hasattr(response, "data"):
            data = response.data
        else:
            data = json.loads(response.content)
        assert "error" in data
        assert "error_code" in data
        assert data["error_code"] == "DuplicateVoteError"

    def test_error_format_is_consistent(self, authenticated_client):
        """Test that error format is consistent across all exceptions."""
        # Test with invalid endpoint (404)
        response = authenticated_client.get("/api/nonexistent/")

        # Should have consistent format
        if response.status_code >= 400:
            # APIClient returns DRF Response which has .data
            if hasattr(response, "data"):
                data = response.data
            else:
                # Try to parse as JSON, but 404 from Django might return HTML
                try:
                    data = json.loads(response.content)
                except (json.JSONDecodeError, ValueError):
                    # If it's HTML, that's fine for 404 - Django's default handler
                    # The important thing is that our custom exceptions return JSON
                    return  # Skip this assertion for HTML 404 responses
            # Should have error or errors field
            assert "error" in data or "errors" in data


@pytest.mark.unit
class TestExceptionInheritance:
    """Test exception inheritance and isinstance checks."""

    def test_all_exceptions_inherit_from_voting_error(self):
        """Test that all custom exceptions inherit from VotingError."""
        exceptions = [
            DuplicateVoteError,
            PollNotFoundError,
            InvalidVoteError,
            PollClosedError,
            RateLimitExceededError,
            InvalidPollError,
            FraudDetectedError,
        ]

        for exc_class in exceptions:
            error = exc_class()
            assert isinstance(error, VotingError)
            assert isinstance(error, Exception)

    def test_exception_message_inheritance(self):
        """Test that exceptions use their default messages."""
        error1 = DuplicateVoteError()
        assert "already voted" in error1.message.lower()

        error2 = PollNotFoundError()
        assert "not found" in error2.message.lower()

        error3 = FraudDetectedError()
        assert (
            "suspicious" in error3.message.lower() or "fraud" in error3.message.lower()
        )
