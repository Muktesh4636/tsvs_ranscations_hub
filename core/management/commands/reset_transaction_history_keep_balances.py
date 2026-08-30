"""
1) pg_dump backup of the current DB (same connection as Django).
2) Delete all rows in core_transaction (audit history).
3) Keep ClientExchangeAccount.funding and exchange_balance unchanged.
4) Insert one ADJUSTMENT row per account with funding_before/after and
   exchange_balance_before/after set to the current account values (fields
   already exist on Transaction; no schema change).

Run after: python manage.py backup_local_postgres (optional separate step)
or this command runs backup first unless --skip-backup.
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import ClientExchangeAccount, Transaction


class Command(BaseCommand):
    help = "Backup DB, delete all Transaction rows, add one snapshot row per account."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-backup",
            action="store_true",
            help="Do not run pg_dump first (you already have a backup).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would happen; no backup, no DB writes.",
        )
        parser.add_argument(
            "--backup-dir",
            type=str,
            default="",
            help="Directory for SQL backup (default: <repo>/backups/local_backups).",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        skip_backup = options["skip_backup"]
        backup_dir = options["backup_dir"]

        db = settings.DATABASES["default"]
        if db["ENGINE"] != "django.db.backends.postgresql":
            self.stderr.write(self.style.ERROR("This command only supports PostgreSQL."))
            return

        if backup_dir:
            out_dir = Path(backup_dir).expanduser().resolve()
        else:
            # chip-3/backups/local_backups (next to manage.py tree)
            out_dir = Path(settings.BASE_DIR) / "backups" / "local_backups"
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = out_dir / f"pre_reset_transactions_{ts}.sql"

        if not dry and not skip_backup:
            self.stdout.write(f"Creating backup: {backup_path}")
            env = os.environ.copy()
            pwd = db.get("PASSWORD") or ""
            env["PGPASSWORD"] = str(pwd)
            host = db.get("HOST") or "localhost"
            port = str(db.get("PORT") or "5432")
            user = db.get("USER") or "postgres"
            name = db.get("NAME") or ""
            cmd = [
                "pg_dump",
                "-h",
                host,
                "-p",
                port,
                "-U",
                user,
                "-d",
                name,
                "-f",
                str(backup_path),
                "--no-owner",
                "--no-acl",
            ]
            try:
                subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
            except FileNotFoundError:
                self.stderr.write(self.style.ERROR("pg_dump not found. Install PostgreSQL client tools."))
                return
            except subprocess.CalledProcessError as e:
                self.stderr.write(self.style.ERROR(e.stderr or str(e)))
                return
            self.stdout.write(self.style.SUCCESS(f"Backup written ({backup_path.stat().st_size} bytes)."))

        n_tx = Transaction.objects.count()
        n_acc = ClientExchangeAccount.objects.count()

        if dry:
            self.stdout.write(f"[dry-run] Would delete {n_tx} transaction(s); {n_acc} account(s) keep funding/balance.")
            self.stdout.write(f"[dry-run] Would insert {n_acc} ADJUSTMENT snapshot row(s).")
            return

        with transaction.atomic():
            deleted, _ = Transaction.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} transaction row(s)."))

            created = 0
            now = timezone.now()
            for account in ClientExchangeAccount.objects.select_related("client", "exchange").order_by("pk"):
                fnd = int(account.funding)
                xbal = int(account.exchange_balance)
                Transaction.objects.create(
                    client_exchange=account,
                    date=now,
                    type="ADJUSTMENT",
                    amount=0,
                    funding_before=fnd,
                    funding_after=fnd,
                    exchange_balance_before=xbal,
                    exchange_balance_after=xbal,
                    sequence_no=1,
                    notes="Opening snapshot after transaction history reset. Balances unchanged on account.",
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Inserted {created} snapshot transaction(s). Funding/balance on accounts were not modified."))
