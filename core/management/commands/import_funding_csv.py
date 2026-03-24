"""
Import funding + exchange_balance from a CSV exported from the server.

Expected columns: client_name, exchange_name, funding, exchange_balance

Rows with the same client+exchange pair are applied in order to accounts
for that pair (ordered by account id), so multiple accounts under the same
names each get the matching row.
"""

import csv
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand

from core.models import ClientExchangeAccount


class Command(BaseCommand):
    help = "Apply funding/exchange_balance from a CSV to ClientExchangeAccount rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_path",
            type=str,
            help="Path to CSV (client_name, exchange_name, funding, exchange_balance)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned updates without saving",
        )

    def handle(self, *args, **options):
        path = Path(options["csv_path"]).expanduser().resolve()
        dry = options["dry_run"]
        if not path.is_file():
            self.stderr.write(self.style.ERROR(f"File not found: {path}"))
            return

        # Preserve global order: group list of rows per (client, exchange)
        groups = defaultdict(list)
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cn = (row.get("client_name") or "").strip()
                en = (row.get("exchange_name") or "").strip()
                if not cn or not en:
                    continue
                try:
                    funding = int((row.get("funding") or "0").strip())
                    exbal = int((row.get("exchange_balance") or "0").strip())
                except ValueError:
                    self.stderr.write(self.style.WARNING(f"Skip bad row: {row}"))
                    continue
                key = (cn, en)
                groups[key].append({"funding": funding, "exchange_balance": exbal})

        updated = 0
        skipped = 0

        for (client_name, exchange_name), rows in sorted(groups.items(), key=lambda x: (x[0][0].lower(), x[0][1].lower())):
            accounts = list(
                ClientExchangeAccount.objects.filter(
                    client__name__iexact=client_name,
                    exchange__name__iexact=exchange_name,
                ).order_by("pk")
            )
            n_acc, n_row = len(accounts), len(rows)
            if n_acc == 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"No local account for {client_name!r} / {exchange_name!r} ({n_row} CSV row(s))"
                    )
                )
                skipped += n_row
                continue
            if n_acc != n_row:
                self.stdout.write(
                    self.style.WARNING(
                        f"{client_name!r} / {exchange_name!r}: {n_acc} account(s), {n_row} CSV row(s) — updating first {min(n_acc, n_row)}"
                    )
                )
            pairs = list(zip(accounts[: len(rows)], rows[: len(accounts)]))
            for acc, data in pairs:
                old_f, old_e = acc.funding, acc.exchange_balance
                if dry:
                    self.stdout.write(
                        f"[dry-run] {acc.pk} {client_name}/{exchange_name}: {old_f},{old_e} -> {data['funding']},{data['exchange_balance']}"
                    )
                else:
                    acc.funding = data["funding"]
                    acc.exchange_balance = data["exchange_balance"]
                    acc.save(update_fields=["funding", "exchange_balance", "updated_at"])
                    self.stdout.write(
                        f"Updated account {acc.pk} {client_name}/{exchange_name}: funding {old_f}->{acc.funding}, balance {old_e}->{acc.exchange_balance}"
                    )
                updated += 1

        if dry:
            self.stdout.write(self.style.SUCCESS(f"Dry run: would update {updated} account(s)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done. Updated {updated} account(s). Skipped missing pairs: {skipped} row(s)."))
