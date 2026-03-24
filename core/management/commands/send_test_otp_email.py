"""
Send a single test email to verify SMTP (Hostinger). Not used by signup or password change.

Example:
  python manage.py send_test_otp_email --to you@example.com
"""

import random
import string

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


def _generate_otp():
    return "".join(random.choices(string.digits, k=4))


class Command(BaseCommand):
    help = "Send one test message to verify SMTP (Hostinger / pravoo.in)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            type=str,
            default="mukteshreddy6@gmail.com",
            help="Recipient email address",
        )

    def handle(self, *args, **options):
        to_email = options["to"].strip()
        otp_code = _generate_otp()

        from_email = getattr(settings, "OTP_FROM_EMAIL", None) or getattr(
            settings, "SECURITY_FROM_EMAIL", None
        ) or settings.DEFAULT_FROM_EMAIL

        # Deliberately NOT the same wording as signup OTP or password-change mail.
        subject = "[SMTP test only] Transaction Hub mail delivery check"
        message = f"""This is a manual test from your server (manage.py send_test_otp_email).

It is NOT from signing up, NOT from changing your password, and NOT a security alert.

Sample code (ignore unless you ran the test yourself): {otp_code}

If you did not run a mail test, you can ignore this message.

— Transaction Hub (devops test)
"""
        self.stdout.write(f"From: {from_email}")
        self.stdout.write(f"To:   {to_email}")
        self.stdout.write(f"Code: {otp_code}")

        try:
            send_mail(
                subject,
                message,
                from_email,
                [to_email],
                fail_silently=False,
            )
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Send failed: {exc}"))
            self.stderr.write(
                "Configure EMAIL_* and OTP_FROM_EMAIL in .env (Hostinger SMTP)."
            )
            raise

        self.stdout.write(self.style.SUCCESS("Test email sent successfully."))
