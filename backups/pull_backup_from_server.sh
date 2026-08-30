#!/bin/bash
# Create a backup on the server and download it to local machine.
# Run from repo root or from backups/:  ./backups/pull_backup_from_server.sh

set -e

REMOTE_USER="root"
REMOTE_HOST="72.61.148.117"
REMOTE_PASS="To1#NXG(ihxodLqmDUU6"
# Where the server backup script writes (pre-deploy backups)
REMOTE_BACKUP_DIR="/root/chip_3_backups"
# Local destination (same as fetch_daily_backup.sh)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_DIR="${SCRIPT_DIR}/local_backups"
mkdir -p "$LOCAL_DIR"

if ! command -v sshpass &>/dev/null; then
    echo "Error: sshpass is required. Install with: brew install hudochenkov/sshpass/sshpass (macOS)"
    exit 1
fi

echo "Creating backup on server..."
sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "/root/backup_chip3.sh" 2>&1 || true

echo "Finding latest backup on server..."
LATEST_BACKUP=$(sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" \
    "ls -t $REMOTE_BACKUP_DIR/backup_*.tar.gz 2>/dev/null | head -n 1")

if [ -z "$LATEST_BACKUP" ]; then
    echo "No backup .tar.gz found in $REMOTE_BACKUP_DIR on server."
    exit 1
fi

FILENAME=$(basename "$LATEST_BACKUP")
LOCAL_PATH="$LOCAL_DIR/$FILENAME"

echo "Downloading $FILENAME to $LOCAL_PATH ..."
sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST:$LATEST_BACKUP" "$LOCAL_PATH"

echo "Done. Local backup: $LOCAL_PATH"
