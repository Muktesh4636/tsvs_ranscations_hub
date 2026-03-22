#!/bin/bash
# One-time setup: run this ON THE SERVER after deploying code (e.g. cd /root/chip_3).
# Installs backup schedule: daily for first 30 days, then weekly on Tuesday.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="${SCRIPT_DIR}/backup_scheduled.sh"
DEST="/root/backup_chip3_scheduled.sh"
CRON_LINE="0 2 * * * /root/backup_chip3_scheduled.sh >> /var/log/chip3_backup_scheduled.log 2>&1"

if [ ! -f "$SOURCE" ]; then
    echo "Error: backup_scheduled.sh not found at $SOURCE. Run from repo or pass correct path."
    exit 1
fi

cp "$SOURCE" "$DEST"
chmod +x "$DEST"
echo "Installed: $DEST"

if crontab -l 2>/dev/null | grep -q "backup_chip3_scheduled"; then
    echo "Cron entry for backup_scheduled already exists."
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "Cron added: run daily at 2 AM, 90-day retention (see BACKUP_SCHEDULE.md)."
fi

echo "Done. Log: /var/log/chip3_backup_scheduled.log"
