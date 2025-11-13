"""
Custom exception handlers for Django REST Framework.
Provides consistent error formatting and proper HTTP status codes.
"""

import logging
import traceback

from django.http import JsonResponse
from rest_framework.views import exception_handler

from core.exceptions import VotingError

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF that provides consistent error formatting.

    Args:
        exc: The exception that was raised
        context: Dictionary containing context information about the exception

    Returns:
        Response object with formatted error, or None to use default handler
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    # Handle custom VotingError exceptions
    if isinstance(exc, VotingError):
        return JsonResponse(
            {
                "error": exc.message,
                "error_code": exc.__class__.__name__,
                "status_code": exc.status_code,
            },
            status=exc.status_code,
        )

    # If response is None, it's an unhandled exception (500 error)
    if response is None:
        # Log the full traceback for debugging
        logger.error(
            f"Unhandled exception: {exc.__class__.__name__}: {str(exc)}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )

        # Return a generic error response (don't expose internal details)
        return JsonResponse(
            {
                "error": "An internal server error occurred",
                "error_code": "InternalServerError",
                "status_code": 500,
            },
            status=500,
        )

    # Customize the response data format for DRF exceptions
    custom_response_data = {
        "error": str(exc),
        "error_code": exc.__class__.__name__,
        "status_code": response.status_code,
    }

    # Add detail if it's a DRF ValidationError
    if hasattr(exc, "detail"):
        if isinstance(exc.detail, dict):
            custom_response_data["errors"] = exc.detail
        elif isinstance(exc.detail, list):
            custom_response_data["errors"] = {"detail": exc.detail}
        else:
            custom_response_data["error"] = str(exc.detail)

    # Add field errors if present
    if hasattr(exc, "detail") and isinstance(exc.detail, dict):
        field_errors = {k: v for k, v in exc.detail.items() if k != "detail"}
        if field_errors:
            custom_response_data["field_errors"] = field_errors

    response.data = custom_response_data

    return response

