#!/bin/bash
# Enhanced database backup script with point-in-time recovery support
# Usage: ./scripts/backup-database-enhanced.sh [--wal-archive] [--encrypt]

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups/database}"
WAL_ARCHIVE_DIR="${WAL_ARCHIVE_DIR:-$PROJECT_ROOT/backups/wal_archive}"
WAL_ARCHIVE="${WAL_ARCHIVE:-false}"
ENCRYPT="${ENCRYPT:-false}"
PRE_MIGRATION="${PRE_MIGRATION:-false}"
OUTPUT_DIR="${OUTPUT_DIR:-$BACKUP_DIR}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --wal-archive)
            WAL_ARCHIVE=true
            shift
            ;;
        --encrypt)
            ENCRYPT=true
            shift
            ;;
        --pre-migration)
            PRE_MIGRATION=true
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--wal-archive] [--encrypt] [--pre-migration] [--output-dir DIR]"
            exit 1
            ;;
    esac
done

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

# Set defaults
DB_NAME="${DB_NAME:-provote_production}"
DB_USER="${DB_USER:-provote_user}"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
COMPOSE_FILE="${COMPOSE_FILE:-docker/docker-compose.prod.yml}"

# Create backup directories
mkdir -p "$OUTPUT_DIR"
if [ "$WAL_ARCHIVE" = "true" ]; then
    mkdir -p "$WAL_ARCHIVE_DIR"
fi

# Generate backup filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PREFIX="backup"
if [ "$PRE_MIGRATION" = "true" ]; then
    BACKUP_PREFIX="pre_migration_backup"
fi
BACKUP_FILE="$OUTPUT_DIR/${BACKUP_PREFIX}_${TIMESTAMP}.sql.gz"

echo "=========================================="
echo "Enhanced Database Backup"
echo "=========================================="
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo "Host: $DB_HOST"
echo "Backup file: $BACKUP_FILE"
echo "WAL Archiving: $WAL_ARCHIVE"
echo "Encryption: $ENCRYPT"
echo ""

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

# Create base backup (SQL format for compatibility)
echo "Creating base backup..."
if docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
    pg_dump -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" "$DB_NAME" | \
    gzip > "$BACKUP_FILE"; then
    echo "✓ Base backup created successfully: $BACKUP_FILE"
else
    echo "✗ Base backup failed!"
    exit 1
fi

# Create custom format backup for point-in-time recovery (if WAL archiving enabled)
if [ "$WAL_ARCHIVE" = "true" ]; then
    CUSTOM_BACKUP_FILE="$OUTPUT_DIR/${BACKUP_PREFIX}_${TIMESTAMP}.dump"
    echo "Creating custom format backup (for PITR)..."
    if docker-compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T db \
        pg_dump -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" \
        -F c -f - "$DB_NAME" > "$CUSTOM_BACKUP_FILE"; then
        echo "✓ Custom format backup created: $CUSTOM_BACKUP_FILE"
        # Also compress it
        gzip "$CUSTOM_BACKUP_FILE"
        echo "✓ Custom format backup compressed: ${CUSTOM_BACKUP_FILE}.gz"
    else
        echo "⚠ Custom format backup failed (non-critical)"
    fi
fi

# Archive WAL files if requested
if [ "$WAL_ARCHIVE" = "true" ]; then
    echo ""
    echo "Archiving WAL files..."
    # This requires PostgreSQL to be configured with archive_mode=on
    # In production, WAL archiving is typically handled by PostgreSQL itself
    echo "⚠ WAL archiving requires PostgreSQL archive_mode configuration"
    echo "   See PostgreSQL documentation for continuous archiving setup"
fi

# Encrypt backup if requested
if [ "$ENCRYPT" = "true" ]; then
    echo ""
    echo "Encrypting backup..."
    if command -v gpg &> /dev/null; then
        gpg --symmetric --cipher-algo AES256 --output "${BACKUP_FILE}.gpg" "$BACKUP_FILE"
        rm "$BACKUP_FILE"
        BACKUP_FILE="${BACKUP_FILE}.gpg"
        echo "✓ Backup encrypted: $BACKUP_FILE"
    else
        echo "⚠ GPG not found, skipping encryption"
    fi
fi

# Verify backup file exists and is not empty
if [ ! -f "$BACKUP_FILE" ] || [ ! -s "$BACKUP_FILE" ]; then
    echo "✗ Backup file is missing or empty!"
    exit 1
fi

# Get backup file size
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo ""
echo "Backup size: $BACKUP_SIZE"

# Create backup metadata
METADATA_FILE="$OUTPUT_DIR/${BACKUP_PREFIX}_${TIMESTAMP}.metadata"
cat > "$METADATA_FILE" <<EOF
BACKUP_FILE=$BACKUP_FILE
TIMESTAMP=$TIMESTAMP
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_HOST=$DB_HOST
BACKUP_SIZE=$BACKUP_SIZE
WAL_ARCHIVE=$WAL_ARCHIVE
ENCRYPTED=$ENCRYPT
PRE_MIGRATION=$PRE_MIGRATION
EOF
echo "✓ Metadata saved: $METADATA_FILE"

# Create symlink to latest backup
LATEST_LINK="$OUTPUT_DIR/latest_backup.sql.gz"
if [ "$PRE_MIGRATION" = "true" ]; then
    LATEST_LINK="$OUTPUT_DIR/latest_pre_migration_backup.sql.gz"
fi

rm -f "$LATEST_LINK"
ln -s "$(basename "$BACKUP_FILE")" "$LATEST_LINK"
echo "✓ Latest backup link created: $LATEST_LINK"

# Cleanup old backups (keep last 30 days)
echo ""
echo "Cleaning up old backups (keeping last 30 days)..."
find "$OUTPUT_DIR" -name "${BACKUP_PREFIX}_*.sql.gz" -mtime +30 -delete
find "$OUTPUT_DIR" -name "${BACKUP_PREFIX}_*.sql.gz.gpg" -mtime +30 -delete
find "$OUTPUT_DIR" -name "${BACKUP_PREFIX}_*.metadata" -mtime +30 -delete
echo "✓ Cleanup complete"

# Optional: Upload to cloud storage
if [ -n "${BACKUP_UPLOAD_COMMAND:-}" ]; then
    echo ""
    echo "Uploading backup to cloud storage..."
    eval "$BACKUP_UPLOAD_COMMAND" "$BACKUP_FILE"
    echo "✓ Upload complete"
fi

echo ""
echo "=========================================="
echo "Backup completed successfully!"
echo "Backup file: $BACKUP_FILE"
echo "Metadata: $METADATA_FILE"
echo "=========================================="

