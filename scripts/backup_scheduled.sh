#!/bin/bash
# Backup scheduler: run backup every day, retain 100 days, optionally sync to remote server.
# Deploy to server and run from cron daily (6 PM): 0 18 * * * /root/backup_chip3_scheduled.sh

set -e

BACKUP_SCRIPT="${BACKUP_SCRIPT:-/root/backup_chip3.sh}"
BACKUP_BASE="${BACKUP_BASE:-/root/chip_3_backups}"
RETENTION_DAYS="${RETENTION_DAYS:-100}"
STATUS_FILE="${BACKUP_STATUS_PATH:-${BACKUP_BASE}/backup_status.json}"
STARTED_AT="$(date -Is)"

write_status() {
    local success="$1"
    local exit_code="$2"
    local finished_at="$3"
    local latest=""
    latest=$(ls -t "$BACKUP_BASE"/backup_*.tar.gz 2>/dev/null | head -n 1 || true)
    python3 - <<PY || true
import json, os, socket
path = ${STATUS_FILE!r}
data = {
  "started_at": ${STARTED_AT!r},
  "finished_at": ${finished_at!r},
  "success": bool(${success}),
  "exit_code": int(${exit_code}),
  "backup_base": ${BACKUP_BASE!r},
  "backup_script": ${BACKUP_SCRIPT!r},
  "retention_days": int(${RETENTION_DAYS}),
  "latest_backup_tar": ${latest!r},
  "host": socket.gethostname(),
}
tmp = path + ".tmp"
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, sort_keys=True)
    f.write("\\n")
os.replace(tmp, path)
PY
}

on_exit() {
    code=$?
    finished="$(date -Is)"
    if [ "$code" -eq 0 ]; then
        write_status "1" "$code" "$finished"
    else
        write_status "0" "$code" "$finished"
    fi
    exit "$code"
}

trap on_exit EXIT

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
