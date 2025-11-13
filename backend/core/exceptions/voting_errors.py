"""
Custom exceptions for voting functionality.
"""


class VotingError(Exception):
    """
    Base exception for voting-related errors.
    
    All custom voting exceptions inherit from this.
    """

    default_status_code = 400
    default_message = "A voting error occurred"

    def __init__(self, message=None, status_code=None):
        """
        Initialize exception.

        Args:
            message: Error message (defaults to default_message)
            status_code: HTTP status code (defaults to default_status_code)
        """
        self.message = message or self.default_message
        self.status_code = status_code or self.default_status_code
        super().__init__(self.message)


class DuplicateVoteError(VotingError):
    """Raised when a user tries to vote twice on the same poll."""

    default_status_code = 409
    default_message = "You have already voted on this poll"


class PollNotFoundError(VotingError):
    """Raised when a poll is not found."""

    default_status_code = 404
    default_message = "Poll not found"


class InvalidVoteError(VotingError):
    """Raised when a vote is invalid (e.g., invalid choice)."""

    default_status_code = 400
    default_message = "Invalid vote"


class PollClosedError(VotingError):
    """Raised when trying to vote on a closed poll."""

    default_status_code = 400
    default_message = "This poll is closed"


class RateLimitExceededError(VotingError):
    """Raised when rate limit is exceeded."""

    default_status_code = 429
    default_message = "Rate limit exceeded. Please try again later."


class InvalidPollError(VotingError):
    """Raised when poll data is invalid."""

    default_status_code = 400
    default_message = "Invalid poll data"


class FraudDetectedError(VotingError):
    """Raised when fraudulent activity is detected."""

    default_status_code = 403
    default_message = "Suspicious activity detected. Vote blocked."
