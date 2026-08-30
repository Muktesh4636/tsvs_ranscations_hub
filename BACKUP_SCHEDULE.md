# Backup Schedule

**Data backups run every day at 6 PM; retention is 100 days.**

(Backups include database, media, static files, code, env, and SSL certs as done by the server backup script.)

## How it works

- **Schedule:** The scheduler runs once per day from cron (6 PM). Each run executes the server backup script and then applies retention.
- **Retention:** Backups older than **100 days** are deleted automatically (backup directories, `.tar.gz` archives, and log files in `/root/chip_3_backups/`).

## Server setup (one-time)

After you deploy code to the server:

```bash
cd /root/chip_3 && ./scripts/install_backup_schedule_on_server.sh
```

This installs `/root/backup_chip3_scheduled.sh` and adds a cron job to run it daily at 6 PM.

## 100-day retention

If the server’s own backup script (`/root/backup_chip3.sh`) also deletes old backups (e.g. “keep last 7 days”), that can conflict with 90-day retention. On the server, either:

- Remove or disable the retention/cleanup inside `/root/backup_chip3.sh`, so only this scheduler’s 100-day retention runs, or  
- Change that script to keep backups for 100 days instead of 7.

The scheduler script deletes in `/root/chip_3_backups/` anything older than 100 days (directories `backup_*`, files `backup_*.tar.gz`, `backup_log_*.txt`).

## Sync to second server (optional)

Daily backups can be copied to a second server (e.g. 159.198.46.36). On the **primary** server (where backup runs), do a one-time setup:

```bash
cd /root/chip_3
./scripts/setup_remote_backup.sh 159.198.46.36 root /root/chip3_backups 'YOUR_REMOTE_PASSWORD'
```

That creates `/root/chip_3_backups/.remote_backup_env` (not in repo). Each day after the backup and retention run, the latest `backup_*.tar.gz` is copied to the remote server. Install `sshpass` on the primary if needed: `apt-get install -y sshpass`.

## Changing retention

To use a different retention (e.g. 60 days), set `RETENTION_DAYS` before running the script, or edit `/root/backup_chip3_scheduled.sh` and change the default (90).
