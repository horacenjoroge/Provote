"""
Audit logging middleware for Provote.
"""

import logging

logger = logging.getLogger("provote.audit")


class AuditLogMiddleware:
    """
    Middleware to log all API requests for audit purposes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip logging for admin and static files
        if not request.path.startswith(("/admin/", "/static/", "/media/")):
            # Log request details
            logger.info(
                f"Request: {request.method} {request.path} "
                f"from {self.get_client_ip(request)} "
                f"User: {request.user if hasattr(request, 'user') else 'Anonymous'}"
            )

        response = self.get_response(request)
        return response

    @staticmethod
    def get_client_ip(request):
        """
        Get the client IP address from the request.
        """
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR", "unknown")
        return ip
