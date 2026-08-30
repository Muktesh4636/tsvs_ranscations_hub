#!/bin/bash
# Backup scheduler: run backup every day, retain 90 days, optionally sync to remote server.
# Deploy to server and run from cron daily (e.g. 2 AM): 0 2 * * * /root/backup_chip3_scheduled.sh

set -e

BACKUP_SCRIPT="${BACKUP_SCRIPT:-/root/backup_chip3.sh}"
BACKUP_BASE="${BACKUP_BASE:-/root/chip_3_backups}"
RETENTION_DAYS="${RETENTION_DAYS:-90}"

# Optional: source credentials for remote backup (create via setup_remote_backup.sh on server)
REMOTE_ENV="${BACKUP_BASE}/.remote_backup_env"
[ -f "$REMOTE_ENV" ] && source "$REMOTE_ENV"

mkdir -p "$BACKUP_BASE"

echo "Running daily backup..."
"$BACKUP_SCRIPT"

echo "Applying retention: keep last $RETENTION_DAYS days..."
find "$BACKUP_BASE" -maxdepth 1 -type d -name 'backup_*' -mtime +"$RETENTION_DAYS" -exec rm -rf {} + 2>/dev/null || true
find "$BACKUP_BASE" -maxdepth 1 -type f \( -name 'backup_*.tar.gz' -o -name 'backup_log_*.txt' \) -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true

# Optional: push latest backup to remote backup server
if [ -n "${REMOTE_BACKUP_HOST}" ]; then
    echo "Syncing latest backup to ${REMOTE_BACKUP_HOST}..."
    LATEST=$(ls -t "$BACKUP_BASE"/backup_*.tar.gz 2>/dev/null | head -n 1)
    if [ -n "$LATEST" ]; then
        REMOTE_USER="${REMOTE_BACKUP_USER:-root}"
        REMOTE_PATH="${REMOTE_BACKUP_PATH:-/root/chip3_backups}"
        # Ensure remote dir exists and copy (use sshpass if password is set)
        if [ -n "${REMOTE_BACKUP_PASS}" ]; then
            if command -v sshpass &>/dev/null; then
                sshpass -p "${REMOTE_BACKUP_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_BACKUP_HOST}" "mkdir -p $REMOTE_PATH"
                sshpass -p "${REMOTE_BACKUP_PASS}" scp -o StrictHostKeyChecking=no "$LATEST" "${REMOTE_USER}@${REMOTE_BACKUP_HOST}:${REMOTE_PATH}/" && echo "Remote sync done." || echo "Remote sync failed."
            else
                echo "sshpass not installed; skipping remote sync."
            fi
        else
            ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_BACKUP_HOST}" "mkdir -p $REMOTE_PATH"
            scp -o StrictHostKeyChecking=no "$LATEST" "${REMOTE_USER}@${REMOTE_BACKUP_HOST}:${REMOTE_PATH}/" && echo "Remote sync done." || echo "Remote sync failed."
        fi
    else
        echo "No backup .tar.gz found to sync."
    fi
fi

echo "Backup and retention done."
