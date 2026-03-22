#!/bin/bash
# One-time setup on the PRIMARY server (72.61.148.117) to enable daily backup sync to a second server.
# Run on primary: ./scripts/setup_remote_backup.sh <remote_host> [remote_user] [remote_path] [password]
# Example: ./scripts/setup_remote_backup.sh 159.198.46.36 root /root/chip3_backups 'Ol880Gq6LuN67YWahh'

set -e

REMOTE_HOST="${1:?Usage: $0 <remote_host> [remote_user] [remote_path] [password]}"
REMOTE_USER="${2:-root}"
REMOTE_PATH="${3:-/root/chip3_backups}"
REMOTE_PASS="${4:-}"

BACKUP_BASE="${BACKUP_BASE:-/root/chip_3_backups}"
mkdir -p "$BACKUP_BASE"
ENV_FILE="${BACKUP_BASE}/.remote_backup_env"

cat > "$ENV_FILE" << EOF
# Remote backup destination (do not commit this file)
export REMOTE_BACKUP_HOST="$REMOTE_HOST"
export REMOTE_BACKUP_USER="$REMOTE_USER"
export REMOTE_BACKUP_PATH="$REMOTE_PATH"
export REMOTE_BACKUP_PASS="$REMOTE_PASS"
EOF
chmod 600 "$ENV_FILE"
echo "Created $ENV_FILE. Daily backups will sync to ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}"
echo "Ensure sshpass is installed on this server: apt-get install -y sshpass"
