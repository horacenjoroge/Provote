# PostgreSQL WAL Archiving Configuration

**Last Updated:** 2025-11-22  
**Version:** 1.0.0

## Overview

This document describes how to configure PostgreSQL Write-Ahead Logging (WAL) archiving for point-in-time recovery (PITR) in the Provote production environment.

## What is WAL Archiving?

WAL archiving allows PostgreSQL to save transaction logs (WAL files) to a separate location. Combined with base backups, this enables point-in-time recovery - restoring the database to any specific moment in time.

## Benefits

- **Point-in-Time Recovery:** Restore to any moment, not just backup times
- **Reduced Data Loss:** RPO (Recovery Point Objective) of minutes instead of hours
- **Continuous Protection:** No need to take frequent full backups

## Prerequisites

- PostgreSQL 12 or later
- Sufficient disk space for WAL archives
- Backup storage location (local or remote)

## Configuration

### 1. Update docker-compose.prod.yml

Add WAL archiving configuration to the database service:

```yaml
db:
  image: postgres:15-alpine
  environment:
    POSTGRES_DB: ${DB_NAME}
    POSTGRES_USER: ${DB_USER}
    POSTGRES_PASSWORD: ${DB_PASSWORD}
    # WAL Archiving
    POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C"
  volumes:
    - postgres_data:/var/lib/postgresql/data/
    - ./backups/wal_archive:/var/lib/postgresql/wal_archive
  command: >
    postgres
    -c wal_level=replica
    -c archive_mode=on
    -c archive_command='test ! -f /var/lib/postgresql/wal_archive/%f && cp %p /var/lib/postgresql/wal_archive/%f'
    -c max_wal_senders=3
    -c wal_keep_size=1GB
```

### 2. Create WAL Archive Directory

```bash
mkdir -p backups/wal_archive
chmod 700 backups/wal_archive
```

### 3. Configure Archive Command

The archive command can be customized for:
- Remote storage (S3, GCS, Azure)
- Compression
- Encryption
- Retention policies

**Example: Archive to S3**
```bash
archive_command='aws s3 cp %p s3://your-bucket/wal-archive/%f'
```

**Example: Archive with compression**
```bash
archive_command='gzip < %p > /var/lib/postgresql/wal_archive/%f.gz'
```

### 4. Restart Database

```bash
docker-compose -f docker/docker-compose.prod.yml restart db
```

## Base Backups

Base backups are required for PITR. Create them regularly:

```bash
# Daily base backup
./scripts/backup-database-enhanced.sh --wal-archive
```

## Point-in-Time Recovery Procedure

### 1. Stop Application

```bash
docker-compose -f docker/docker-compose.prod.yml stop web celery celery-beat
```

### 2. Restore Base Backup

```bash
# Find base backup before target time
BASE_BACKUP=$(find backups/database/ -name "backup_*.dump.gz" \
  -newermt "2025-11-22 00:00:00" ! -newermt "2025-11-22 14:30:00" | head -1)

# Restore base backup
gunzip -c "$BASE_BACKUP" | \
  docker-compose -f docker/docker-compose.prod.yml exec -T db \
  pg_restore -U ${DB_USER} -d ${DB_NAME} --clean --if-exists
```

### 3. Configure Recovery

Create `recovery.conf` (PostgreSQL 12+) or update `postgresql.conf`:

```bash
# For PostgreSQL 12+
docker-compose -f docker/docker-compose.prod.yml exec db \
  sh -c "echo \"recovery_target_time = '2025-11-22 14:30:00 UTC'\" >> /var/lib/postgresql/data/postgresql.conf"
docker-compose -f docker/docker-compose.prod.yml exec db \
  sh -c "echo \"restore_command = 'cp /var/lib/postgresql/wal_archive/%f %p'\" >> /var/lib/postgresql/data/postgresql.conf"
```

### 4. Start Database in Recovery Mode

```bash
docker-compose -f docker/docker-compose.prod.yml restart db
```

### 5. Monitor Recovery

```bash
docker-compose -f docker/docker-compose.prod.yml logs -f db
```

### 6. Verify Recovery

```bash
docker-compose -f docker/docker-compose.prod.yml exec db \
  psql -U ${DB_USER} -d ${DB_NAME} -c "SELECT NOW();"
```

## Maintenance

### WAL Archive Cleanup

WAL archives accumulate over time. Clean up old archives:

```bash
# Remove WAL files older than base backup
find backups/wal_archive/ -name "*.wal" -mtime +7 -delete
```

### Monitoring

Monitor WAL archive:
- Disk space usage
- Archive command failures
- WAL file count

## Best Practices

1. **Regular Base Backups:** Daily or more frequent
2. **Monitor Archive Command:** Ensure it's working
3. **Test Recovery:** Monthly PITR tests
4. **Offsite Storage:** Store WAL archives offsite
5. **Retention Policy:** Keep WAL archives for at least 7 days

## Troubleshooting

### Archive Command Failing

**Symptoms:** WAL files not being archived

**Solutions:**
```bash
# Check PostgreSQL logs
docker-compose -f docker/docker-compose.prod.yml logs db | grep archive

# Test archive command manually
docker-compose -f docker/docker-compose.prod.yml exec db \
  sh -c "test ! -f /var/lib/postgresql/wal_archive/test.wal && echo 'Archive command works'"
```

### Disk Space Issues

**Symptoms:** WAL archive directory full

**Solutions:**
- Increase disk space
- Implement WAL archive rotation
- Use remote storage
- Compress WAL files

### Recovery Not Starting

**Symptoms:** Database doesn't enter recovery mode

**Solutions:**
- Check `recovery.conf` or `postgresql.conf`
- Verify WAL files are accessible
- Check PostgreSQL logs

## References

- [PostgreSQL Continuous Archiving](https://www.postgresql.org/docs/current/continuous-archiving.html)
- [PostgreSQL Point-in-Time Recovery](https://www.postgresql.org/docs/current/backup-pitr.html)

---

**Document Maintained By:** DevOps Team  
**Last Review Date:** 2025-11-22  
**Next Review Date:** 2026-02-22

