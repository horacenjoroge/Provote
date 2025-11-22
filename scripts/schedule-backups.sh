#!/bin/bash
# Backup scheduling script
# Sets up cron jobs for automated backups
# Usage: ./scripts/schedule-backups.sh [--install] [--remove]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ACTION="${1:-}"

# Backup script path
BACKUP_SCRIPT="$PROJECT_ROOT/scripts/backup-database-enhanced.sh"

# Cron job definitions
DAILY_BACKUP="0 2 * * * $BACKUP_SCRIPT --pre-migration >> $PROJECT_ROOT/logs/backup.log 2>&1"
WEEKLY_TEST="0 3 * * 0 $PROJECT_ROOT/scripts/test-backup-restore.sh >> $PROJECT_ROOT/logs/backup-test.log 2>&1"

case "$ACTION" in
    --install)
        echo "Installing backup cron jobs..."
        
        # Create logs directory
        mkdir -p "$PROJECT_ROOT/logs"
        
        # Add daily backup
        (crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT" || true; echo "$DAILY_BACKUP") | crontab -
        echo "✓ Daily backup scheduled (2 AM)"
        
        # Add weekly test
        (crontab -l 2>/dev/null | grep -v "test-backup-restore.sh" || true; echo "$WEEKLY_TEST") | crontab -
        echo "✓ Weekly backup test scheduled (Sunday 3 AM)"
        
        echo ""
        echo "Current crontab:"
        crontab -l | grep -E "backup|test-backup" || echo "No backup jobs found"
        ;;
    
    --remove)
        echo "Removing backup cron jobs..."
        crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT" | grep -v "test-backup-restore.sh" | crontab - || true
        echo "✓ Backup cron jobs removed"
        ;;
    
    --list)
        echo "Current backup cron jobs:"
        crontab -l 2>/dev/null | grep -E "backup|test-backup" || echo "No backup jobs found"
        ;;
    
    *)
        echo "Usage: $0 [--install|--remove|--list]"
        echo ""
        echo "Options:"
        echo "  --install  Install backup cron jobs"
        echo "  --remove   Remove backup cron jobs"
        echo "  --list     List current backup cron jobs"
        exit 1
        ;;
esac

