"""
Backup the database used by your local dev server (e.g. http://127.0.0.1:8000/).
The app reads data from the DB in settings — not from the HTTP URL.

Outputs under <project>/backups/local_backups/:
  - PostgreSQL: local_site_data_<timestamp>.sql (pg_dump, full DB)
  - SQLite: copy of db file as local_site_data_<timestamp>.sqlite3

Optional JSON (may fail on some DB/driver setups): --json
"""

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Backup local/default database to backups/local_backups/"

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Also try Django dumpdata to JSON (can fail with some PostgreSQL setups).",
        )

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        out_dir = base / "backups" / "local_backups"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        db = settings.DATABASES["default"]
        engine = db["ENGINE"]

        if engine == "django.db.backends.postgresql":
            sql_path = out_dir / f"local_site_data_{ts}.sql"
            self.stdout.write(f"pg_dump → {sql_path}")
            env = os.environ.copy()
            env["PGPASSWORD"] = str(db.get("PASSWORD") or "")
            cmd = [
                "pg_dump",
                "-h",
                db.get("HOST") or "localhost",
                "-p",
                str(db.get("PORT") or "5432"),
                "-U",
                db.get("USER") or "postgres",
                "-d",
                db.get("NAME") or "",
                "-f",
                str(sql_path),
                "--no-owner",
                "--no-acl",
            ]
            try:
                subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
            except FileNotFoundError:
                raise CommandError("pg_dump not found. Install PostgreSQL client tools.")
            except subprocess.CalledProcessError as e:
                raise CommandError(e.stderr or str(e))
            self.stdout.write(self.style.SUCCESS(f"SQL backup: {sql_path} ({sql_path.stat().st_size} bytes)"))

        elif engine == "django.db.backends.sqlite3":
            db_name = db.get("NAME")
            if not db_name:
                raise CommandError("SQLite NAME not set.")
            src = Path(db_name)
            if not src.is_file():
                raise CommandError(f"SQLite file not found: {src}")
            dst = out_dir / f"local_site_data_{ts}.sqlite3"
            shutil.copy2(src, dst)
            self.stdout.write(self.style.SUCCESS(f"SQLite copy: {dst} ({dst.stat().st_size} bytes)"))
        else:
            raise CommandError(f"Unsupported ENGINE: {engine}")

        if options["json"]:
            json_path = out_dir / f"local_site_data_{ts}.json"
            self.stdout.write(f"Trying JSON dump → {json_path}")
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    call_command("dumpdata", indent=2, stdout=f, natural_foreign=True)
                self.stdout.write(self.style.SUCCESS(f"JSON: {json_path.stat().st_size} bytes"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"JSON dump skipped: {e}"))
