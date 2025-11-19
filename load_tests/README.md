# Load and Performance Tests

This directory contains Locust-based load and performance tests for the Provote application.

## Test Files

### 1. `voting_load_test.py`
- **VotingUser**: Simulates normal voting behavior (1000 concurrent users)
- **HighVolumeVotingUser**: High-throughput voting (10k votes per second target)
- Tests: Vote casting, poll browsing, results viewing

### 2. `api_performance_test.py`
- **APIPerformanceUser**: Tests API endpoint performance
- **DatabaseQueryPerformanceUser**: Tests database query performance
- Monitors: Response times, query performance, endpoint-specific metrics

### 3. `data_integrity_test.py`
- **DataIntegrityUser**: Verifies data integrity under load
- Tests: Vote count accuracy, database consistency, no data corruption

### 4. `graceful_degradation_test.py`
- **DegradationTestUser**: Tests graceful degradation under stress
- **ExtremeLoadUser**: Extreme load stress testing
- Tests: Rate limiting, error handling, timeout handling, bottleneck identification

### 5. `websocket_load_test.py`
- **WebSocketLoadUser**: Tests WebSocket connections under load (1000 connections)
- Note: Requires additional setup for full WebSocket testing

## Running Tests

### Prerequisites

```bash
pip install locust
```

### Basic Usage

```bash
# Run with web UI (default)
locust -f load_tests/locustfile.py --host=http://localhost:8001

# Run headless (no UI)
locust -f load_tests/locustfile.py --host=http://localhost:8001 --headless -u 1000 -r 100 --run-time 5m

# Run specific user classes
locust -f load_tests/voting_load_test.py --host=http://localhost:8001 VotingUser HighVolumeVotingUser

# Run with custom spawn rate (users per second)
locust -f load_tests/voting_load_test.py --host=http://localhost:8001 -u 1000 -r 100
```

### Test Scenarios

#### 1. 1000 Concurrent Users Voting
```bash
locust -f load_tests/voting_load_test.py --host=http://localhost:8001 VotingUser -u 1000 -r 50
```

#### 2. 10k Votes Per Second
```bash
locust -f load_tests/voting_load_test.py --host=http://localhost:8001 HighVolumeVotingUser -u 500 -r 200
```

#### 3. API Performance Testing
```bash
locust -f load_tests/api_performance_test.py --host=http://localhost:8001 APIPerformanceUser -u 200 -r 20
```

#### 4. Data Integrity Testing
```bash
locust -f load_tests/data_integrity_test.py --host=http://localhost:8001 DataIntegrityUser -u 100 -r 10
```

#### 5. Graceful Degradation Testing
```bash
locust -f load_tests/graceful_degradation_test.py --host=http://localhost:8001 DegradationTestUser -u 500 -r 100
```

## Test Targets

### Performance Targets
- **1000 concurrent users**: System should handle 1000 concurrent users voting
- **10k votes per second**: System should process 10,000 votes per second
- **API response times**: 
  - Poll list: < 500ms (p95)
  - Poll detail: < 200ms (p95)
  - Vote casting: < 1000ms (p95)
  - Results: < 500ms (p95)
- **WebSocket connections**: 1000 concurrent WebSocket connections

### Data Integrity Targets
- **No data corruption**: Vote counts remain accurate under load
- **Database consistency**: Cached counts match actual counts (within tolerance)
- **No duplicate votes**: Idempotency maintained under load

### Degradation Targets
- **Error rate**: < 1% under normal load, < 5% under extreme load
- **Graceful degradation**: System degrades gracefully, not catastrophically
- **Rate limiting**: Rate limits enforced correctly

## Monitoring

### Metrics Collected
- Request count and rate (RPS)
- Response times (min, max, avg, p50, p95, p99)
- Failure rate
- Error types and frequencies
- Slow requests (>5 seconds)
- Timeouts

### Reports

Locust generates HTML reports automatically. After running tests:

```bash
# Generate HTML report
locust -f load_tests/locustfile.py --host=http://localhost:8001 --headless -u 1000 -r 100 --run-time 5m --html=load_test_report.html
```

## Bottleneck Identification

The tests automatically identify bottlenecks:
- Endpoints with high p95/p99 response times
- Slow database queries
- High error rates
- Timeout patterns

Check the console output and HTML reports for bottleneck analysis.

## Docker Integration

To run load tests against Docker containers:

```bash
# Test against local Docker setup
locust -f load_tests/locustfile.py --host=http://localhost:8001

# Test against production (if accessible)
locust -f load_tests/locustfile.py --host=https://your-production-url.com
```

## Notes

- **SQLite Limitations**: For true concurrent load testing, use PostgreSQL
- **WebSocket Testing**: Full WebSocket load testing may require additional tools or custom Locust extensions
- **Rate Limiting**: Tests may hit rate limits; this is expected and tests graceful degradation
- **Database State**: Tests create test data; ensure test database is separate from production

## Continuous Integration

Add to CI/CD pipeline:

```yaml
# Example GitHub Actions
- name: Run Load Tests
  run: |
    locust -f load_tests/locustfile.py \
      --host=http://localhost:8001 \
      --headless \
      -u 100 \
      -r 10 \
      --run-time 2m \
      --html=load_test_report.html \
      --csv=load_test_results
```

