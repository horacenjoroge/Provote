#!/bin/bash
# Script to run load tests with different scenarios

set -e

HOST="${HOST:-http://localhost:8001}"
OUTPUT_DIR="${OUTPUT_DIR:-load_test_results}"

mkdir -p "$OUTPUT_DIR"

echo "=========================================="
echo "Provote Load Test Suite"
echo "=========================================="
echo "Host: $HOST"
echo "Output Directory: $OUTPUT_DIR"
echo ""

# Test 1: 1000 Concurrent Users Voting
echo "Test 1: 1000 Concurrent Users Voting"
echo "--------------------------------------"
locust -f load_tests/voting_load_test.py \
    --host="$HOST" \
    --headless \
    -u 1000 \
    -r 50 \
    --run-time 5m \
    --html="$OUTPUT_DIR/voting_1000_users.html" \
    --csv="$OUTPUT_DIR/voting_1000_users" \
    VotingUser

echo ""

# Test 2: 10k Votes Per Second
echo "Test 2: 10k Votes Per Second (High Volume)"
echo "--------------------------------------"
locust -f load_tests/voting_load_test.py \
    --host="$HOST" \
    --headless \
    -u 500 \
    -r 200 \
    --run-time 2m \
    --html="$OUTPUT_DIR/high_volume_voting.html" \
    --csv="$OUTPUT_DIR/high_volume_voting" \
    HighVolumeVotingUser

echo ""

# Test 3: API Performance
echo "Test 3: API Performance Testing"
echo "--------------------------------------"
locust -f load_tests/api_performance_test.py \
    --host="$HOST" \
    --headless \
    -u 200 \
    -r 20 \
    --run-time 3m \
    --html="$OUTPUT_DIR/api_performance.html" \
    --csv="$OUTPUT_DIR/api_performance" \
    APIPerformanceUser

echo ""

# Test 4: Data Integrity
echo "Test 4: Data Integrity Testing"
echo "--------------------------------------"
locust -f load_tests/data_integrity_test.py \
    --host="$HOST" \
    --headless \
    -u 100 \
    -r 10 \
    --run-time 5m \
    --html="$OUTPUT_DIR/data_integrity.html" \
    --csv="$OUTPUT_DIR/data_integrity" \
    DataIntegrityUser

echo ""

# Test 5: Graceful Degradation
echo "Test 5: Graceful Degradation Testing"
echo "--------------------------------------"
locust -f load_tests/graceful_degradation_test.py \
    --host="$HOST" \
    --headless \
    -u 500 \
    -r 100 \
    --run-time 3m \
    --html="$OUTPUT_DIR/graceful_degradation.html" \
    --csv="$OUTPUT_DIR/graceful_degradation" \
    DegradationTestUser

echo ""

# Test 6: Database Query Performance
echo "Test 6: Database Query Performance"
echo "--------------------------------------"
locust -f load_tests/api_performance_test.py \
    --host="$HOST" \
    --headless \
    -u 100 \
    -r 10 \
    --run-time 2m \
    --html="$OUTPUT_DIR/db_performance.html" \
    --csv="$OUTPUT_DIR/db_performance" \
    DatabaseQueryPerformanceUser

echo ""
echo "=========================================="
echo "All Load Tests Completed"
echo "=========================================="
echo "Results saved to: $OUTPUT_DIR"
echo ""
echo "Summary Reports:"
ls -lh "$OUTPUT_DIR"/*.html

