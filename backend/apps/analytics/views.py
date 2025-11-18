"""
Views for Analytics app.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from core.services.admin_dashboard import (
    get_active_polls_and_voters,
    get_dashboard_summary,
    get_fraud_alerts_summary,
    get_performance_metrics,
    get_recent_activity,
    get_system_statistics,
)
from core.services.poll_analytics import (
    get_comprehensive_analytics,
    get_analytics_summary,
    get_total_votes_over_time,
    get_votes_by_hour,
    get_votes_by_day,
    get_voter_demographics,
    get_participation_rate,
    get_average_time_to_vote,
    get_drop_off_rate,
    get_vote_distribution,
)

from .models import PollAnalytics
from .serializers import PollAnalyticsSerializer


class PollAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for PollAnalytics model."""

    queryset = PollAnalytics.objects.all()
    serializer_class = PollAnalyticsSerializer

    @action(detail=False, methods=["get"], url_path="poll/(?P<poll_id>[^/.]+)/comprehensive")
    def comprehensive(self, request, poll_id=None):
        """
        Get comprehensive analytics for a poll.
        
        GET /api/v1/analytics/poll/{poll_id}/comprehensive/
        
        Returns complete analytics including:
        - Time series data
        - Demographics
        - Participation metrics
        - Vote distribution
        - Drop-off rates
        """
        try:
            poll_id = int(poll_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid poll ID"}, status=status.HTTP_400_BAD_REQUEST
            )

        analytics = get_comprehensive_analytics(poll_id)
        
        if "error" in analytics:
            return Response(analytics, status=status.HTTP_404_NOT_FOUND)
        
        return Response(analytics, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="poll/(?P<poll_id>[^/.]+)/summary")
    def summary(self, request, poll_id=None):
        """
        Get analytics summary for a poll.
        
        GET /api/v1/analytics/poll/{poll_id}/summary/
        
        Returns lightweight summary of key metrics.
        """
        try:
            poll_id = int(poll_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid poll ID"}, status=status.HTTP_400_BAD_REQUEST
            )

        summary = get_analytics_summary(poll_id)
        
        if "error" in summary:
            return Response(summary, status=status.HTTP_404_NOT_FOUND)
        
        return Response(summary, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="poll/(?P<poll_id>[^/.]+)/time-series")
    def time_series(self, request, poll_id=None):
        """
        Get time series data for votes.
        
        GET /api/v1/analytics/poll/{poll_id}/time-series/?interval=hour|day
        
        Query params:
        - interval: 'hour' or 'day' (default: 'hour')
        """
        try:
            poll_id = int(poll_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid poll ID"}, status=status.HTTP_400_BAD_REQUEST
            )

        interval = request.query_params.get("interval", "hour")
        if interval not in ["hour", "day"]:
            interval = "hour"

        time_series = get_total_votes_over_time(poll_id, interval=interval)
        
        return Response({"poll_id": poll_id, "interval": interval, "data": time_series})

    @action(detail=False, methods=["get"], url_path="poll/(?P<poll_id>[^/.]+)/hourly")
    def hourly(self, request, poll_id=None):
        """
        Get votes by hour for a specific day.
        
        GET /api/v1/analytics/poll/{poll_id}/hourly/?date=YYYY-MM-DD
        """
        try:
            poll_id = int(poll_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid poll ID"}, status=status.HTTP_400_BAD_REQUEST
            )

        date_str = request.query_params.get("date")
        date = None
        if date_str:
            try:
                from datetime import datetime
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        hourly_data = get_votes_by_hour(poll_id, date)
        
        return Response({"poll_id": poll_id, "date": date_str or "today", "data": hourly_data})

    @action(detail=False, methods=["get"], url_path="poll/(?P<poll_id>[^/.]+)/daily")
    def daily(self, request, poll_id=None):
        """
        Get votes by day for the last N days.
        
        GET /api/v1/analytics/poll/{poll_id}/daily/?days=30
        """
        try:
            poll_id = int(poll_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid poll ID"}, status=status.HTTP_400_BAD_REQUEST
            )

        days = int(request.query_params.get("days", 30))
        if days < 1 or days > 365:
            days = 30

        daily_data = get_votes_by_day(poll_id, days=days)
        
        return Response({"poll_id": poll_id, "days": days, "data": daily_data})

    @action(detail=False, methods=["get"], url_path="poll/(?P<poll_id>[^/.]+)/demographics")
    def demographics(self, request, poll_id=None):
        """
        Get voter demographics.
        
        GET /api/v1/analytics/poll/{poll_id}/demographics/
        """
        try:
            poll_id = int(poll_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid poll ID"}, status=status.HTTP_400_BAD_REQUEST
            )

        demographics = get_voter_demographics(poll_id)
        
        return Response({"poll_id": poll_id, **demographics})

    @action(detail=False, methods=["get"], url_path="poll/(?P<poll_id>[^/.]+)/distribution")
    def distribution(self, request, poll_id=None):
        """
        Get vote distribution across options.
        
        GET /api/v1/analytics/poll/{poll_id}/distribution/
        """
        try:
            poll_id = int(poll_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid poll ID"}, status=status.HTTP_400_BAD_REQUEST
            )

        distribution = get_vote_distribution(poll_id)
        
        return Response({"poll_id": poll_id, "distribution": distribution})


class AdminDashboardViewSet(viewsets.ViewSet):
    """
    Admin dashboard API endpoints.
    
    All endpoints require admin authentication.
    """
    
    permission_classes = [IsAdminUser]
    
    @action(detail=False, methods=["get"], url_path="statistics")
    def statistics(self, request):
        """
        Get system-wide statistics.
        
        GET /api/v1/admin-dashboard/statistics/
        
        Returns:
            - total_polls: Total number of polls
            - active_polls: Number of active polls
            - total_votes: Total number of votes
            - total_users: Total number of users
            - total_fraud_alerts: Total number of fraud alerts
            - blocked_ips: Number of blocked IPs
        """
        stats = get_system_statistics()
        return Response(stats, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=["get"], url_path="activity")
    def activity(self, request):
        """
        Get recent activity feed.
        
        GET /api/v1/admin-dashboard/activity/?limit=50
        
        Query params:
            - limit: Maximum number of activities (default: 50, max: 100)
        
        Returns list of recent activities (votes, polls created, fraud alerts, etc.)
        """
        limit = int(request.query_params.get("limit", 50))
        if limit < 1 or limit > 100:
            limit = 50
        
        activities = get_recent_activity(limit=limit)
        return Response({
            "count": len(activities),
            "results": activities
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=["get"], url_path="fraud-alerts")
    def fraud_alerts(self, request):
        """
        Get fraud alerts summary.
        
        GET /api/v1/admin-dashboard/fraud-alerts/?limit=20
        
        Query params:
            - limit: Maximum number of recent alerts (default: 20)
        
        Returns:
            - total: Total number of fraud alerts
            - recent_24h: Alerts in last 24 hours
            - recent_7d: Alerts in last 7 days
            - recent: List of recent alerts
            - by_risk_score: Count by risk score ranges
            - top_polls: Top polls with fraud alerts
        """
        limit = int(request.query_params.get("limit", 20))
        if limit < 1 or limit > 100:
            limit = 20
        
        alerts = get_fraud_alerts_summary(limit=limit)
        return Response(alerts, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=["get"], url_path="performance")
    def performance(self, request):
        """
        Get performance metrics.
        
        GET /api/v1/admin-dashboard/performance/
        
        Returns:
            - api_latency: Average API response time
            - db_queries: Database query statistics
            - cache_hit_rate: Cache hit rate
            - error_rate: Error rate
        
        Note: This is a placeholder. In production, implement actual metric collection.
        """
        metrics = get_performance_metrics()
        return Response(metrics, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=["get"], url_path="active-polls")
    def active_polls(self, request):
        """
        Get active polls and recent voters.
        
        GET /api/v1/admin-dashboard/active-polls/?limit=20
        
        Query params:
            - limit: Maximum number of polls/voters (default: 20)
        
        Returns:
            - active_polls: List of currently active polls
            - recent_voters: List of recent voters (last 24h)
            - top_polls: Top polls by vote count
        """
        limit = int(request.query_params.get("limit", 20))
        if limit < 1 or limit > 100:
            limit = 20
        
        data = get_active_polls_and_voters(limit=limit)
        return Response(data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """
        Get complete admin dashboard summary.
        
        GET /api/v1/admin-dashboard/summary/
        
        Returns all dashboard data in one response:
            - statistics: System-wide statistics
            - recent_activity: Recent activity feed
            - fraud_alerts: Fraud alerts summary
            - performance_metrics: Performance metrics
            - active_polls_and_voters: Active polls and voters
        """
        summary = get_dashboard_summary()
        return Response(summary, status=status.HTTP_200_OK)
