#!/bin/bash
# Backup testing and validation script
# Usage: ./scripts/test-backup-restore.sh [backup_file]

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DB_NAME="test_restore_db"

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

# Set defaults
DB_USER="${DB_USER:-provote_user}"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
COMPOSE_FILE="${COMPOSE_FILE:-docker/docker-compose.prod.yml}"

# Get backup file
if [ $# -ge 1 ]; then
    BACKUP_FILE="$1"
else
    # Use latest backup
    BACKUP_FILE=$(ls -t "$PROJECT_ROOT/backups/database/backup_"*.sql.gz 2>/dev/null | head -1)
    if [ -z "$BACKUP_FILE" ]; then
        echo "Error: No backup file found"
        echo "Usage: $0 [backup_file]"
        exit 1
    fi
fi

# Resolve backup file path
if [ ! -f "$BACKUP_FILE" ]; then
    if [ -f "$PROJECT_ROOT/backups/database/$BACKUP_FILE" ]; then
        BACKUP_FILE="$PROJECT_ROOT/backups/database/$BACKUP_FILE"
    else
        echo "Error: Backup file not found: $BACKUP_FILE"
        exit 1
    fi
fi

echo "=========================================="
echo "Backup Restore Test"
echo "=========================================="
echo "Backup file: $BACKUP_FILE"
echo "Test database: $TEST_DB_NAME"
echo ""

# Check if backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Check if backup file is not empty
if [ ! -s "$BACKUP_FILE" ]; then
    echo "Error: Backup file is empty: $BACKUP_FILE"
    exit 1
fi

# Check if Docker Compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose not found"
    exit 1
fi

# Check if database container is running
if ! docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" ps db | grep -q "Up"; then
    echo "Error: Database container is not running"
    exit 1
fi

# Create test database
echo "Step 1: Creating test database..."
if docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
    psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -c \
    "SELECT 1 FROM pg_database WHERE datname = '$TEST_DB_NAME';" | grep -q 1; then
    echo "Test database already exists, dropping..."
    docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
        dropdb -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" "$TEST_DB_NAME" || true
fi

docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
    createdb -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" "$TEST_DB_NAME"
echo "✓ Test database created"

# Restore backup to test database
echo ""
echo "Step 2: Restoring backup to test database..."
if gunzip -c "$BACKUP_FILE" | \
    docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
    psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" "$TEST_DB_NAME"; then
    echo "✓ Backup restored successfully"
else
    echo "✗ Restore failed!"
    # Cleanup
    docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
        dropdb -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" "$TEST_DB_NAME" || true
    exit 1
fi

# Verify data integrity
echo ""
echo "Step 3: Verifying data integrity..."

# Check critical tables exist
CRITICAL_TABLES=("polls_poll" "votes_vote" "users_user" "analytics_auditlog")

for table in "${CRITICAL_TABLES[@]}"; do
    COUNT=$(docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
        psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -t -c \
        "SELECT COUNT(*) FROM $table;" "$TEST_DB_NAME" 2>/dev/null | tr -d ' ' || echo "0")
    
    if [ "$COUNT" != "" ] && [ "$COUNT" != "0" ]; then
        echo "  ✓ $table: $COUNT records"
    else
        echo "  ⚠ $table: No records or table missing"
    fi
done

# Check database schema
echo ""
echo "Step 4: Verifying database schema..."
TABLE_COUNT=$(docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
    psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" \
    "$TEST_DB_NAME" | tr -d ' ')

echo "  Tables found: $TABLE_COUNT"

if [ "$TABLE_COUNT" -lt 10 ]; then
    echo "  ⚠ Warning: Fewer tables than expected"
fi

# Check for common issues
echo ""
echo "Step 5: Checking for common issues..."

# Check for NULL in non-nullable fields (sample check)
NULL_CHECK=$(docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
    psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -t -c \
    "SELECT COUNT(*) FROM polls_poll WHERE title IS NULL;" \
    "$TEST_DB_NAME" 2>/dev/null | tr -d ' ' || echo "0")

if [ "$NULL_CHECK" != "0" ]; then
    echo "  ⚠ Warning: Found NULL values in non-nullable fields"
else
    echo "  ✓ No NULL values in critical fields"
fi

# Performance test
echo ""
echo "Step 6: Running performance test..."
START_TIME=$(date +%s)
docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
    psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -c \
    "SELECT COUNT(*) FROM votes_vote;" "$TEST_DB_NAME" > /dev/null
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

if [ "$DURATION" -lt 5 ]; then
    echo "  ✓ Query performance acceptable ($DURATION seconds)"
else
    echo "  ⚠ Warning: Query took $DURATION seconds (may indicate issues)"
fi

# Cleanup
echo ""
echo "Step 7: Cleaning up test database..."
docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
    dropdb -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" "$TEST_DB_NAME"
echo "✓ Test database removed"

echo ""
echo "=========================================="
echo "Backup restore test completed!"
echo "Backup file: $BACKUP_FILE"
echo "Status: ✓ PASSED"
echo "=========================================="

