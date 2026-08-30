"""
Local/dev: zero funding & exchange balances, clear cycle locks, delete all
transactions, settlements, and pending-payment ledger rows. Keeps clients,
exchanges, and accounts (with percentages unchanged).

Usage:
  python manage.py reset_all_financial_data
  python manage.py reset_all_financial_data --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    Client,
    ClientExchangeAccount,
    PendingPaymentTransaction,
    Settlement,
    Transaction,
)


class Command(BaseCommand):
    help = "Set all funding/exchange_balance to 0, reset pending & cycle fields, delete all transactions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print counts only; do not modify the database.",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]

        n_tx = Transaction.objects.count()
        n_set = Settlement.objects.count()
        n_pend = PendingPaymentTransaction.objects.count()
        n_acc = ClientExchangeAccount.objects.count()

        self.stdout.write(
            f"Transactions: {n_tx}, Settlements: {n_set}, "
            f"PendingPaymentTransaction: {n_pend}, Accounts: {n_acc}"
        )

        if dry:
            self.stdout.write(self.style.WARNING("Dry run — no changes."))
            return

        with transaction.atomic():
            Transaction.objects.all().delete()
            Settlement.objects.all().delete()
            PendingPaymentTransaction.objects.all().delete()

            ClientExchangeAccount.objects.update(
                funding=0,
                exchange_balance=0,
                pending_balance=0,
                total_share_amount=0,
                company_share_amount=0,
                locked_initial_final_share=None,
                locked_share_percentage=None,
                locked_initial_pnl=None,
                cycle_start_date=None,
                locked_initial_funding=None,
            )
            Client.objects.update(pending_balance=0)

        self.stdout.write(
            self.style.SUCCESS(
                "Done. All funding and exchange balances are 0; transactions and related rows removed."
            )
        )
