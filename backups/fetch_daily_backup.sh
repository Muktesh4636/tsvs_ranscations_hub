#!/bin/bash

# Configuration
REMOTE_USER="root"
REMOTE_HOST="72.61.148.117"
REMOTE_PASS="To1#NXG(ihxodLqmDUU6"
REMOTE_DIR="/root/daily_backups"
LOCAL_DIR="/Users/pradyumna/chip_3/backups/daily_backups"

# Create local directory if it doesn't exist
mkdir -p "$LOCAL_DIR"

# Get the filename of the latest backup on the server
LATEST_BACKUP=$(sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no $REMOTE_USER@$REMOTE_HOST "ls -t $REMOTE_DIR/backup_*.tar.gz | head -n 1")

if [ -z "$LATEST_BACKUP" ]; then
    echo "No backup files found on server."
    exit 1
fi

FILENAME=$(basename "$LATEST_BACKUP")

# Download the latest backup if it doesn't already exist locally
if [ ! -f "$LOCAL_DIR/$FILENAME" ]; then
    echo "Downloading latest backup: $FILENAME"
    sshpass -p "$REMOTE_PASS" scp -o StrictHostKeyChecking=no $REMOTE_USER@$REMOTE_HOST:"$LATEST_BACKUP" "$LOCAL_DIR/"
    echo "Download complete: $LOCAL_DIR/$FILENAME"
else
    echo "Latest backup $FILENAME already exists locally."
fi
