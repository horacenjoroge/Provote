#!/bin/bash
# Script to run load tests with detailed reporting

set -e

HOST="${1:-http://localhost:8001}"
USERS="${2:-1000}"
SPAWN_RATE="${3:-100}"
DURATION="${4:-5m}"
OUTPUT_DIR="${5:-load_test_results}"

echo "=========================================="
echo "Running Load Test with Detailed Reports"
echo "=========================================="
echo "Host: $HOST"
echo "Users: $USERS"
echo "Spawn Rate: $SPAWN_RATE users/second"
echo "Duration: $DURATION"
echo "Output Directory: $OUTPUT_DIR"
echo "=========================================="

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Run Locust with detailed reporting
locust -f load_tests/voting_load_test.py \
    --host="$HOST" \
    --headless \
    -u "$USERS" \
    -r "$SPAWN_RATE" \
    --run-time "$DURATION" \
    --html "$OUTPUT_DIR/report.html" \
    --csv "$OUTPUT_DIR/results" \
    --loglevel INFO \
    --logfile "$OUTPUT_DIR/locust.log"

echo ""
echo "=========================================="
echo "Test Complete!"
echo "=========================================="
echo "Results saved to: $OUTPUT_DIR/"
echo "  - HTML Report: $OUTPUT_DIR/report.html"
echo "  - CSV Files: $OUTPUT_DIR/results_*.csv"
echo "  - Log File: $OUTPUT_DIR/locust.log"
echo ""
echo "To view the HTML report:"
echo "  open $OUTPUT_DIR/report.html"
echo "=========================================="

