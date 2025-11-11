"""
Custom exceptions for voting functionality.
"""


class VotingError(Exception):
    """Base exception for voting-related errors."""

    pass


class DuplicateVoteError(VotingError):
    """Raised when a user tries to vote twice on the same poll."""

    pass


class PollNotFoundError(VotingError):
    """Raised when a poll is not found."""

    pass


class InvalidVoteError(VotingError):
    """Raised when a vote is invalid (e.g., invalid choice)."""

    pass


class PollClosedError(VotingError):
    """Raised when trying to vote on a closed poll."""

    pass
