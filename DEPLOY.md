# Quick Deployment Guide

## Push Code to Server (One Command)

### Option 1: Using the provided script (Recommended)

```bash
cd chip-3
./push_to_server.sh
```

This script will:
- Sync all code files to the server
- Exclude unnecessary files (venv, __pycache__, .git, etc.)
- Optionally restart the Gunicorn service

### Option 2: Manual rsync command

```bash
cd chip-3
rsync -avz --progress \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='staticfiles/' \
    --exclude='media/' \
    --exclude='*.log' \
    --exclude='.env' \
    -e "sshpass -p 'To1#NXG(ihxodLqmDUU6' ssh -o StrictHostKeyChecking=no" \
    ./ root@72.61.148.117:/root/chip_3/
```

### Option 3: Using SSH key (if configured)

If you have SSH key authentication set up:

```bash
cd chip-3
rsync -avz --progress \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='staticfiles/' \
    --exclude='media/' \
    --exclude='*.log' \
    --exclude='.env' \
    ./ root@72.61.148.117:/root/chip_3/
```

### After pushing code

1. **Restart Gunicorn service:**
   ```bash
   sshpass -p 'To1#NXG(ihxodLqmDUU6' ssh root@72.61.148.117 "systemctl restart chip-broker.service"
   ```

2. **Collect static files (if needed):**
   ```bash
   sshpass -p 'To1#NXG(ihxodLqmDUU6' ssh root@72.61.148.117 "cd /root/chip_3 && source venv/bin/activate && python manage.py collectstatic --noinput"
   ```

3. **Run migrations (if needed):**
   ```bash
   sshpass -p 'To1#NXG(ihxodLqmDUU6' ssh root@72.61.148.117 "cd /root/chip_3 && source venv/bin/activate && python manage.py migrate"
   ```

### Quick one-liner (all-in-one)

```bash
cd chip-3 && rsync -avz --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' --exclude='.git/' --exclude='staticfiles/' --exclude='media/' --exclude='*.log' --exclude='.env' -e "sshpass -p 'To1#NXG(ihxodLqmDUU6' ssh -o StrictHostKeyChecking=no" ./ root@72.61.148.117:/root/chip_3/ && sshpass -p 'To1#NXG(ihxodLqmDUU6' ssh root@72.61.148.117 "systemctl restart chip-broker.service"
```

## Server Details

- **Server:** root@72.61.148.117
- **Path:** /root/chip_3
- **Service:** chip-broker.service (Gunicorn)

## Scheduled backups (optional)

Backups run **daily** with **90-day retention**. See [BACKUP_SCHEDULE.md](BACKUP_SCHEDULE.md). One-time setup on the server after deploy:

```bash
cd /root/chip_3 && ./scripts/install_backup_schedule_on_server.sh
```

## Notes

- The `.env` file is excluded from sync (contains sensitive credentials)
- Static files and media are excluded (they're generated/uploaded on server)
- Virtual environment is excluded (installed separately on server)
