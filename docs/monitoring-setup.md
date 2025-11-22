# Production Monitoring and Alerting Setup

**Last Updated:** 2025-11-22  
**Version:** 1.0.0

## Overview

This document describes the production monitoring and alerting setup for Provote, including Prometheus metrics, Grafana dashboards, Sentry error tracking, and PagerDuty alerting.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Django    │────▶│  Prometheus  │────▶│   Grafana   │
│  (Metrics)  │     │  (Scraping)  │     │ (Dashboards)│
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Alertmanager│
                    │  (PagerDuty)  │
                    └──────────────┘

┌─────────────┐
│   Django    │────▶│    Sentry    │
│  (Errors)   │     │ (Error Track)│
└─────────────┘     └──────────────┘
```

## Components

### 1. Prometheus

**Purpose:** Metrics collection and storage

**Metrics Collected:**
- API response times
- Error rates
- Vote throughput
- Database query times
- Cache hit rates
- WebSocket connections
- Request counts
- Active users

**Configuration:** `docker/monitoring/prometheus.yml`

### 2. Grafana

**Purpose:** Metrics visualization and dashboards

**Dashboards:**
- API Performance
- Error Rates
- Vote Throughput
- Database Performance
- Cache Performance
- WebSocket Connections
- System Health

**Configuration:** `docker/monitoring/grafana/dashboards/`

### 3. Sentry

**Purpose:** Error tracking and performance monitoring

**Features:**
- Real-time error tracking
- Performance monitoring
- Release tracking
- User context
- Breadcrumbs

**Configuration:** `backend/config/settings/production.py`

### 4. Alertmanager

**Purpose:** Alert routing and notification

**Integrations:**
- PagerDuty
- Email
- Slack (optional)

**Configuration:** `docker/monitoring/alertmanager.yml`

## Setup Instructions

### 1. Install Dependencies

Add to `requirements/production.txt`:
```
prometheus-client==0.19.0
sentry-sdk==1.40.0
```

### 2. Configure Sentry

Add to `.env`:
```bash
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=1.0.0
```

### 3. Start Monitoring Stack

```bash
docker-compose -f docker/docker-compose.monitoring.yml up -d
```

### 4. Access Dashboards

- **Grafana:** http://localhost:3000 (admin/admin)
- **Prometheus:** http://localhost:9090
- **Alertmanager:** http://localhost:9093

## Metrics

### Application Metrics

**Endpoint:** `/metrics/`

**Available Metrics:**
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request duration
- `http_errors_total` - Total HTTP errors
- `votes_total` - Total votes cast
- `votes_per_second` - Vote throughput
- `db_query_duration_seconds` - Database query duration
- `cache_hits_total` - Cache hits
- `cache_misses_total` - Cache misses
- `websocket_connections` - Active WebSocket connections

### Custom Metrics

**Vote Metrics:**
```python
from prometheus_client import Counter, Histogram

votes_total = Counter('votes_total', 'Total votes cast', ['poll_id', 'option_id'])
vote_duration = Histogram('vote_duration_seconds', 'Time to process vote')
```

**Database Metrics:**
```python
db_query_duration = Histogram('db_query_duration_seconds', 'Database query duration', ['operation'])
```

**Cache Metrics:**
```python
cache_operations = Counter('cache_operations_total', 'Cache operations', ['operation', 'status'])
```

## Alerts

### Alert Rules

**File:** `docker/monitoring/prometheus/alerts.yml`

**Critical Alerts:**
- High error rate (> 5% for 5 minutes)
- High response time (> 2s p95 for 5 minutes)
- Database connection failures
- Cache unavailability
- High vote failure rate (> 10% for 5 minutes)

**Warning Alerts:**
- Elevated error rate (> 2% for 10 minutes)
- Elevated response time (> 1s p95 for 10 minutes)
- Low cache hit rate (< 70% for 15 minutes)
- High database query time (> 500ms p95 for 10 minutes)

### PagerDuty Integration

1. Create PagerDuty service
2. Get integration key
3. Configure in `alertmanager.yml`
4. Test alert routing

## Dashboards

### API Performance Dashboard

**Metrics:**
- Request rate (requests/second)
- Response time (p50, p95, p99)
- Error rate (%)
- Top endpoints by latency
- Request distribution by status code

### Vote Throughput Dashboard

**Metrics:**
- Votes per second
- Vote success rate
- Vote failures by reason
- Top polls by vote count
- Vote distribution over time

### Database Performance Dashboard

**Metrics:**
- Query rate
- Query duration (p50, p95, p99)
- Slow queries
- Connection pool usage
- Transaction rate

### Cache Performance Dashboard

**Metrics:**
- Cache hit rate
- Cache operations per second
- Cache size
- Eviction rate
- Memory usage

### System Health Dashboard

**Metrics:**
- Service uptime
- Health check status
- Resource usage (CPU, memory)
- Container status
- Network traffic

## Sentry Configuration

### Error Tracking

Sentry automatically captures:
- Unhandled exceptions
- 500 errors
- Performance issues
- Database query performance

### Release Tracking

```python
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
    release=os.environ.get("SENTRY_RELEASE", "1.0.0"),
    traces_sample_rate=0.1,  # 10% of transactions
)
```

### Custom Context

```python
import sentry_sdk

sentry_sdk.set_user({"id": user.id, "username": user.username})
sentry_sdk.set_context("poll", {"poll_id": poll.id, "title": poll.title})
```

## Monitoring Best Practices

### 1. Metrics Naming

- Use consistent naming conventions
- Include units in metric names
- Use labels for dimensions

### 2. Alert Fatigue

- Set appropriate thresholds
- Use alert grouping
- Implement alert suppression
- Review and tune alerts regularly

### 3. Dashboard Design

- Keep dashboards focused
- Use appropriate visualizations
- Include time ranges
- Add annotations for deployments

### 4. Performance Impact

- Use sampling for high-volume metrics
- Aggregate metrics appropriately
- Monitor monitoring system itself
- Set resource limits

## Troubleshooting

### Metrics Not Appearing

1. Check Prometheus targets: http://localhost:9090/targets
2. Verify `/metrics/` endpoint is accessible
3. Check Prometheus logs: `docker-compose logs prometheus`

### Alerts Not Firing

1. Check alert rules: http://localhost:9090/alerts
2. Verify Alertmanager configuration
3. Test PagerDuty integration
4. Check Alertmanager logs: `docker-compose logs alertmanager`

### Grafana Dashboards Empty

1. Verify Prometheus data source
2. Check query syntax
3. Verify time range
4. Check Grafana logs: `docker-compose logs grafana`

### Sentry Not Receiving Errors

1. Verify SENTRY_DSN is set correctly
2. Check Sentry project settings
3. Test error reporting manually
4. Check Django logs for Sentry errors

## Maintenance

### Regular Tasks

1. **Weekly:**
   - Review alert effectiveness
   - Check dashboard performance
   - Review error trends

2. **Monthly:**
   - Update alert thresholds
   - Optimize dashboards
   - Review metric retention

3. **Quarterly:**
   - Audit monitoring setup
   - Review costs
   - Update documentation

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Sentry Documentation](https://docs.sentry.io/)
- [PagerDuty Documentation](https://developer.pagerduty.com/)

---

**Document Maintained By:** DevOps Team  
**Last Review Date:** 2025-11-22  
**Next Review Date:** 2026-02-22

