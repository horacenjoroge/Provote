"""
Prometheus metrics middleware for Django.

Collects HTTP request metrics including:
- Request count
- Request duration
- Error count
"""

import time
from typing import Callable

from django.http import HttpRequest, HttpResponse

# Optional Prometheus client
try:
    from prometheus_client import Counter, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Dummy classes if Prometheus is not available
    class Counter:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

    class Histogram:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self

        def observe(self, *args, **kwargs):
            pass

# Metrics (only create if Prometheus is available)
if PROMETHEUS_AVAILABLE:
    http_requests_total = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )

    http_request_duration_seconds = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint"],
        buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
    )

    http_errors_total = Counter(
        "http_errors_total",
        "Total HTTP errors",
        ["method", "endpoint", "status"],
    )
else:
    # Dummy metrics if Prometheus is not available
    http_requests_total = Counter("http_requests_total", "Total HTTP requests", [])
    http_request_duration_seconds = Histogram("http_request_duration_seconds", "HTTP request duration", [])
    http_errors_total = Counter("http_errors_total", "Total HTTP errors", [])


class MetricsMiddleware:
    """
    Middleware to collect Prometheus metrics for HTTP requests.
    """

    def __init__(self, get_response: Callable):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Start timer
        start_time = time.time()

        # Get response
        response = self.get_response(request)

        # Calculate duration
        duration = time.time() - start_time

        # Get endpoint (simplified - use path without query params)
        endpoint = self._get_endpoint(request.path)

        # Record metrics (only if Prometheus is available)
        if PROMETHEUS_AVAILABLE:
            http_requests_total.labels(
                method=request.method,
                endpoint=endpoint,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=endpoint,
            ).observe(duration)

            # Record errors (4xx and 5xx)
            if response.status_code >= 400:
                http_errors_total.labels(
                    method=request.method,
                    endpoint=endpoint,
                    status=response.status_code,
                ).inc()

        return response

    def _get_endpoint(self, path: str) -> str:
        """
        Normalize endpoint path for metrics.

        Replaces IDs and dynamic segments with placeholders.
        """
        # Remove leading/trailing slashes
        path = path.strip("/")

        # Replace common ID patterns
        import re

        # Replace UUIDs
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{id}",
            path,
            flags=re.IGNORECASE,
        )

        # Replace numeric IDs
        path = re.sub(r"/\d+/", "/{id}/", path)

        # Limit path length
        if len(path) > 100:
            path = path[:100]

        return path or "root"

