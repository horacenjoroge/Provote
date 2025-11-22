# Disaster Recovery Runbook

**Last Updated:** 2025-11-22  
**Version:** 1.0.0

## Overview

This runbook provides step-by-step procedures for disaster recovery scenarios in the Provote production environment. It covers database failures, data corruption, complete system failures, and other critical incidents.

## Recovery Time Objectives (RTO) and Recovery Point Objectives (RPO)

- **RTO (Recovery Time Objective):** 4 hours
- **RPO (Recovery Point Objective):** 1 hour (with WAL archiving enabled)

## Pre-Disaster Preparation

### 1. Backup Verification

**Daily Tasks:**
- Verify automated backups are running
- Check backup storage availability
- Test restore procedures monthly

**Weekly Tasks:**
- Review backup logs
- Verify backup integrity
- Test point-in-time recovery

### 2. Documentation

- Keep this runbook updated
- Document all custom configurations
- Maintain contact list for escalation

### 3. Access and Credentials

- Ensure backup access credentials are secure and accessible
- Maintain offsite backup of credentials
- Document all service account permissions

## Disaster Scenarios

### Scenario 1: Database Corruption

**Symptoms:**
- Database errors in logs
- Application errors
- Data inconsistencies reported

**Recovery Steps:**

1. **Assess Damage**
   ```bash
   # Check database status
   docker-compose -f docker/docker-compose.prod.yml exec db pg_isready
   
   # Check for corruption
   docker-compose -f docker/docker-compose.prod.yml exec db \
     psql -U ${DB_USER} -d ${DB_NAME} -c "SELECT COUNT(*) FROM pg_database;"
   ```

2. **Stop Application Services**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml stop web celery celery-beat
   ```

3. **Create Emergency Backup**
   ```bash
   ./scripts/backup-database.sh --pre-migration
   ```

4. **Restore from Latest Backup**
   ```bash
   # List available backups
   ls -lh backups/database/
   
   # Restore
   ./scripts/restore-database.sh latest_backup.sql.gz --confirm
   ```

5. **Verify Data Integrity**
   ```bash
   # Check critical tables
   docker-compose -f docker/docker-compose.prod.yml exec db \
     psql -U ${DB_USER} -d ${DB_NAME} -c "SELECT COUNT(*) FROM polls_poll;"
   ```

6. **Restart Services**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml start web celery celery-beat
   ```

7. **Verify Application**
   ```bash
   curl http://localhost/health/
   ```

### Scenario 2: Complete Database Loss

**Symptoms:**
- Database container won't start
- Data directory corrupted or missing
- Connection refused errors

**Recovery Steps:**

1. **Stop All Services**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml down
   ```

2. **Remove Corrupted Database Volume**
   ```bash
   # WARNING: This deletes all data!
   docker volume rm provote_postgres_data
   ```

3. **Recreate Database Container**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml up -d db
   ```

4. **Wait for Database to Initialize**
   ```bash
   # Wait for database to be ready
   docker-compose -f docker/docker-compose.prod.yml exec db \
     pg_isready -U ${DB_USER} -d ${DB_NAME}
   ```

5. **Restore from Backup**
   ```bash
   # Find latest backup
   LATEST_BACKUP=$(ls -t backups/database/backup_*.sql.gz | head -1)
   
   # Restore
   ./scripts/restore-database.sh "$LATEST_BACKUP" --confirm
   ```

6. **Run Migrations (if needed)**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml exec web \
     python manage.py migrate --settings=config.settings.production
   ```

7. **Restart All Services**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml up -d
   ```

8. **Verify System**
   ```bash
   # Health check
   curl http://localhost/health/
   
   # Check logs
   docker-compose -f docker/docker-compose.prod.yml logs --tail=100 web
   ```

### Scenario 3: Point-in-Time Recovery

**Use Case:** Need to recover to a specific time before data loss or corruption

**Prerequisites:**
- WAL archiving enabled
- Continuous archiving configured

**Recovery Steps:**

1. **Stop Application**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml stop web celery celery-beat
   ```

2. **Identify Recovery Target**
   ```bash
   # Target time (example: 2025-11-22 14:30:00 UTC)
   RECOVERY_TARGET_TIME="2025-11-22 14:30:00 UTC"
   ```

3. **Restore Base Backup**
   ```bash
   # Find base backup before target time
   BASE_BACKUP=$(find backups/database/ -name "backup_*.sql.gz" \
     -newermt "2025-11-22 00:00:00" ! -newermt "$RECOVERY_TARGET_TIME" | head -1)
   
   ./scripts/restore-database.sh "$BASE_BACKUP" --confirm
   ```

4. **Configure Point-in-Time Recovery**
   ```bash
   # Create recovery.conf (PostgreSQL 12+ uses postgresql.conf)
   docker-compose -f docker/docker-compose.prod.yml exec db \
     sh -c "echo \"recovery_target_time = '$RECOVERY_TARGET_TIME'\" >> /var/lib/postgresql/data/postgresql.conf"
   ```

5. **Restore WAL Files**
   ```bash
   # Copy WAL files to pg_wal directory
   # (This would be automated in production)
   ```

6. **Start Database in Recovery Mode**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml restart db
   ```

7. **Monitor Recovery**
   ```bash
   # Check recovery progress
   docker-compose -f docker/docker-compose.prod.yml logs -f db
   ```

8. **Verify Recovery**
   ```bash
   # Check database is at target time
   docker-compose -f docker/docker-compose.prod.yml exec db \
     psql -U ${DB_USER} -d ${DB_NAME} -c "SELECT NOW();"
   ```

9. **Restart Application**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml start web celery celery-beat
   ```

### Scenario 4: Complete System Failure

**Symptoms:**
- All services down
- Server inaccessible
- Infrastructure failure

**Recovery Steps:**

1. **Provision New Infrastructure**
   - Set up new server/cloud instance
   - Install Docker and Docker Compose
   - Configure networking

2. **Restore Codebase**
   ```bash
   # Clone repository
   git clone <repository-url>
   cd AlxProjectNexus
   
   # Checkout production branch
   git checkout main
   ```

3. **Restore Configuration**
   ```bash
   # Restore .env file from secure backup
   # Restore SSL certificates
   # Restore Nginx configuration
   ```

4. **Restore Database**
   ```bash
   # Download latest backup from offsite storage
   # Restore database
   ./scripts/restore-database.sh backup_YYYYMMDD_HHMMSS.sql.gz --confirm
   ```

5. **Restore Media Files**
   ```bash
   # Download media backup
   # Extract to media volume
   ```

6. **Start Services**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml up -d
   ```

7. **Verify System**
   ```bash
   # Health checks
   curl http://localhost/health/
   
   # Smoke tests
   pytest backend/tests/test_smoke.py
   ```

8. **Update DNS/Load Balancer**
   - Point DNS to new server
   - Update load balancer configuration

### Scenario 5: Partial Data Loss

**Symptoms:**
- Specific tables corrupted
- Data missing from certain time period
- Application errors for specific features

**Recovery Steps:**

1. **Identify Affected Data**
   ```bash
   # Check specific tables
   docker-compose -f docker/docker-compose.prod.yml exec db \
     psql -U ${DB_USER} -d ${DB_NAME} -c "SELECT COUNT(*) FROM affected_table;"
   ```

2. **Create Backup of Current State**
   ```bash
   ./scripts/backup-database.sh --pre-migration
   ```

3. **Restore Specific Tables**
   ```bash
   # Extract specific tables from backup
   gunzip -c backup_YYYYMMDD_HHMMSS.sql.gz | \
     grep -A 10000 "COPY affected_table" | \
     docker-compose -f docker/docker-compose.prod.yml exec -T db \
     psql -U ${DB_USER} -d ${DB_NAME}
   ```

4. **Verify Data**
   ```bash
   # Check restored data
   docker-compose -f docker/docker-compose.prod.yml exec db \
     psql -U ${DB_USER} -d ${DB_NAME} -c "SELECT COUNT(*) FROM affected_table;"
   ```

## Backup Testing Procedures

### Weekly Backup Test

**Purpose:** Verify backups are restorable

**Procedure:**

1. **Select Test Backup**
   ```bash
   TEST_BACKUP=$(ls -t backups/database/backup_*.sql.gz | head -1)
   ```

2. **Create Test Database**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml exec db \
     createdb -U ${DB_USER} test_restore_db
   ```

3. **Restore to Test Database**
   ```bash
   gunzip -c "$TEST_BACKUP" | \
     docker-compose -f docker/docker-compose.prod.yml exec -T db \
     psql -U ${DB_USER} -d test_restore_db
   ```

4. **Verify Data**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml exec db \
     psql -U ${DB_USER} -d test_restore_db -c "SELECT COUNT(*) FROM polls_poll;"
   ```

5. **Cleanup**
   ```bash
   docker-compose -f docker/docker-compose.prod.yml exec db \
     dropdb -U ${DB_USER} test_restore_db
   ```

### Monthly Full Recovery Test

**Purpose:** Test complete disaster recovery procedure

**Procedure:**

1. **Document Current State**
   - Record all running services
   - Note current data volumes
   - Document configuration

2. **Simulate Disaster**
   ```bash
   # Stop services
   docker-compose -f docker/docker-compose.prod.yml down
   
   # Remove volumes (in test environment only!)
   docker volume rm provote_postgres_data
   ```

3. **Execute Recovery**
   - Follow Scenario 2: Complete Database Loss
   - Time the recovery process
   - Document any issues

4. **Verify Recovery**
   - Run full test suite
   - Verify data integrity
   - Check application functionality

5. **Document Results**
   - Record recovery time
   - Note any issues
   - Update runbook if needed

## Backup Storage

### Local Storage

- **Location:** `backups/database/`
- **Retention:** 30 days
- **Format:** Compressed SQL dumps

### Offsite Storage

**Options:**
1. **Cloud Storage (S3, GCS, Azure)**
   - Automated upload after backup
   - Versioning enabled
   - Cross-region replication

2. **Remote Server**
   - SSH/SCP transfer
   - Encrypted transfer
   - Separate geographic location

3. **Tape Backup**
   - Weekly full backups
   - Monthly offsite rotation

### Backup Encryption

**All backups should be encrypted:**
```bash
# Encrypt backup
gpg --symmetric --cipher-algo AES256 backup.sql.gz

# Decrypt backup
gpg --decrypt backup.sql.gz.gpg | gunzip | psql ...
```

## Monitoring and Alerts

### Backup Monitoring

- **Daily:** Verify backup completed successfully
- **Weekly:** Test backup restore
- **Monthly:** Full disaster recovery test

### Alert Conditions

- Backup failed
- Backup size significantly different
- Backup older than 24 hours
- Restore test failed

## Communication Plan

### Incident Response Team

1. **Primary On-Call:** DevOps Engineer
2. **Secondary On-Call:** Senior Developer
3. **Escalation:** CTO/Technical Lead

### Communication Channels

- **Slack:** #incidents channel
- **PagerDuty:** Critical alerts
- **Email:** devops@example.com

### Status Updates

- **Initial:** Within 15 minutes
- **Progress:** Every 30 minutes
- **Resolution:** Immediate notification

## Post-Recovery Procedures

### 1. Root Cause Analysis

- Document what happened
- Identify root cause
- Determine prevention measures

### 2. System Verification

- Run full test suite
- Verify all services
- Check data integrity
- Monitor for 24 hours

### 3. Documentation Update

- Update runbook with lessons learned
- Document any new procedures
- Update contact information if needed

### 4. Prevention Measures

- Implement fixes for root cause
- Update monitoring
- Enhance backup procedures
- Schedule additional training

## Recovery Checklists

### Pre-Recovery Checklist

- [ ] Incident identified and documented
- [ ] Team notified
- [ ] Backup location confirmed
- [ ] Recovery procedure selected
- [ ] Access credentials verified
- [ ] Communication channels established

### During Recovery Checklist

- [ ] Services stopped safely
- [ ] Backup restored
- [ ] Data integrity verified
- [ ] Services restarted
- [ ] Application tested
- [ ] Monitoring verified

### Post-Recovery Checklist

- [ ] All services running
- [ ] Health checks passing
- [ ] Data integrity confirmed
- [ ] Application functional
- [ ] Monitoring active
- [ ] Team notified of resolution
- [ ] Root cause analysis scheduled

## Testing Schedule

- **Daily:** Automated backup verification
- **Weekly:** Manual backup restore test
- **Monthly:** Full disaster recovery drill
- **Quarterly:** Review and update runbook

## References

- [PostgreSQL Backup Documentation](https://www.postgresql.org/docs/current/backup.html)
- [PostgreSQL Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html)
- [Docker Volume Management](https://docs.docker.com/storage/volumes/)

---

**Document Maintained By:** DevOps Team  
**Last Review Date:** 2025-11-22  
**Next Review Date:** 2026-02-22

