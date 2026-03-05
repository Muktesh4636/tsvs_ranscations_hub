from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import time
import subprocess
import os
from pathlib import Path

from django.contrib.auth import logout, login, authenticate, get_user_model
from django.contrib.auth.decorators import login_required

User = get_user_model()
from django.db.models import Q, Sum, Count, F
from django.db.models.functions import Abs
from django.core.exceptions import FieldError
from django.db import transaction as db_transaction
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
import logging
import random
import string

logger = logging.getLogger('core.security')

from .models import (
    Client,
    Exchange,
    ClientExchangeAccount,
    Transaction,
    Settlement,
    EmailOTP,
    MobileLog,
    )
from .forms import SignupForm, OTPVerificationForm

# Health check view for monitoring
def health_check(request):
    """
    Health check endpoint for load balancers and monitoring systems.
    Returns 200 OK with basic system status.
    """
    from django.db import connection

    try:
        # Test database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            db_status = "healthy"
    except Exception:
        db_status = "unhealthy"

    # Basic system info
    status = {
        "status": "healthy" if db_status == "healthy" else "unhealthy",
        "database": db_status,
        "timestamp": timezone.now().isoformat(),
        "service": "chip-broker-portal"
    }

    response_status = 200 if status["status"] == "healthy" else 503
    return JsonResponse(status, status=response_status)

# TODO: core.utils.money module removed - add back if needed
# Placeholder functions
def round_share(value):
    

    """Placeholder - replace with actual implementation"""
    return Decimal(str(value)) if value else Decimal(0)

def round_capital(value):

    
    """Placeholder - replace with actual implementation"""
    return Decimal(str(value)) if value else Decimal(0)

AUTO_CLOSE_THRESHOLD = Decimal("0.01")


def calculate_share_split(total_share, my_share_pct, friend_share_pct):
    """Placeholder - replace with actual implementation"""
    return Decimal(0), Decimal(0), Decimal(0)


# Helper functions to eliminate duplicate logic
def calculate_display_remaining(client_pnl, remaining_amount):
    """
    Calculate display remaining amount with correct sign based on Client_PnL direction.
    
    Formula: DisplayRemaining = sign(Client_PnL) × RemainingRaw
    - IF Client_PnL < 0 (LOSS): DisplayRemaining = +RemainingRaw (client owes you)
    - IF Client_PnL > 0 (PROFIT): DisplayRemaining = -RemainingRaw (you owe client)
    
    Args:
        client_pnl: Client PnL value (can be negative, zero, or positive)
        remaining_amount: Raw remaining amount (always ≥ 0)
    
    Returns:
        BigInteger: Signed remaining amount for display
    """
    if client_pnl > 0:
        return -remaining_amount  # You owe client (negative)
    else:
        return remaining_amount  # Client owes you (positive)


def get_settlement_info_for_display(client_exchange):
    """
    Get settlement information for display purposes.
    
    This helper function encapsulates the common pattern of:
    1. Locking share if needed
    2. Getting remaining settlement amount
    3. Extracting relevant values
    
    Args:
        client_exchange: ClientExchangeAccount instance
    
    Returns:
        dict: Contains 'initial_final_share', 'remaining_amount', 'overpaid_amount', 
              'final_share', 'show_na', 'share_pct'
    """
    client_exchange.lock_initial_share_if_needed()
    settlement_info = client_exchange.get_remaining_settlement_amount()
    initial_final_share = settlement_info['initial_final_share']
    remaining_amount = settlement_info['remaining']
    overpaid_amount = settlement_info['overpaid']
    
    # Use initial locked share for display
    final_share = initial_final_share if initial_final_share > 0 else client_exchange.compute_my_share()
    show_na = (final_share == 0)
    
    client_pnl = client_exchange.compute_client_pnl()
    share_pct = client_exchange.get_share_percentage(client_pnl)
    
    return {
        'initial_final_share': initial_final_share,
        'remaining_amount': remaining_amount,
        'overpaid_amount': overpaid_amount,
        'final_share': final_share,
        'show_na': show_na,
        'share_pct': share_pct,
        'client_pnl': client_pnl,
    }


def create_client_helper(request, template_name):
    """
    Helper function to create a client (eliminates duplicate code between client_create and my_client_create).
    
    Args:
        request: Django request object
        template_name: Template name to render ('core/clients/create.html' or 'core/clients/create_my.html')
    
    Returns:
        HttpResponse: Render or redirect response
    """
    from django.contrib import messages
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip()
        referred_by = request.POST.get("referred_by", "").strip()
        
        # CRITICAL: Convert empty string to None (required for UNIQUE constraint)
        code = code if code else None
        
        if not name:
            messages.error(request, "Client name is required.")
            return render(request, template_name, {
                'code': code or '',
                'referred_by': referred_by,
            })
        
        # Check for duplicate code BEFORE saving (user-friendly error)
        if code is not None:
            existing_client = Client.objects.filter(code=code).first()
            if existing_client:
                messages.error(
                    request,
                    f"Client code '{code}' is already in use by client '{existing_client.name}'. "
                    f"Please choose a different code or leave it blank."
                )
                return render(request, template_name, {
                    'name': name,
                    'code': code,
                    'referred_by': referred_by,
                })
        
        try:
            # Create client
            client = Client(
                user=request.user,
                name=name,
                code=code,  # Already None if empty
                referred_by=referred_by if referred_by else None,
            )
            client.save()
            
            messages.success(request, f"Client '{name}' has been created successfully.")
            return redirect(reverse("client_list"))
            
        except ValidationError as e:
            messages.error(request, str(e))
            return render(request, template_name, {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })
        except IntegrityError as e:
            if 'unique constraint' in str(e).lower() or 'duplicate' in str(e).lower():
                messages.error(
                    request,
                    f"Client code '{code}' is already in use. Please choose a different code or leave it blank."
                )
            else:
                messages.error(request, f"Error creating client: {str(e)}")
            return render(request, template_name, {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })
        except Exception as e:
            messages.error(request, f"Error creating client: {str(e)}")
            return render(request, template_name, {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })
    
    return render(request, template_name)


def get_exchange_balance(client_exchange, as_of_date=None, use_cache=True):


    """
    TODO: Add your new calculation logic here.

    Args:
        client_exchange: ClientExchangeAccount instance

        as_of_date: Optional date to calculate as of. If None, uses current state.
        use_cache: If True and as_of_date is None, use cached value if available.
    
    Returns:
        Exchange balance as Decimal (placeholder - replace with your calculation)

    """
    # TODO: Add your new formulas and logic here
    return Decimal(0)



def update_outstanding_from_balance_change(client_exchange, old_balance, current_balance, balance_date=None):


    """
    TODO: Add your new calculation logic here.
    
    Args:
        client_exchange: ClientExchangeAccount instance (must be My Client)

        old_balance: Old Balance (balance after last settlement)
        current_balance: Current Balance (latest balance from exchange)
        balance_date: Date of the balance record (optional)
    
    Returns:
        dict with placeholder values - replace with your calculations

    """
    # TODO: Add your new formulas and logic here
    # Remove all old balance logic, current balance logic, share calculation logic
    return {
        "your_share": Decimal(0),
        "outstanding_before": Decimal(0),
        "outstanding_after": Decimal(0),
        "difference": Decimal(0),
    }


def create_loss_profit_from_balance_change(client_exchange, old_balance, new_balance, balance_date, note_suffix=""):


    """
    TODO: Add your new calculation logic here.
    
    Args:
        client_exchange: ClientExchangeAccount instance

        old_balance: Balance before the change
        new_balance: Balance after the change
        balance_date: Date of the balance record
        note_suffix: Optional suffix for transaction note
    
    Returns:
        Transaction object if created, None otherwise

    """
    # TODO: Add your new formulas and logic here
    # Remove all loss calculation, share calculation, old balance logic
    return None


def calculate_client_profit_loss(client_exchange, as_of_date=None):


    """
    TODO: Add your new calculation logic here.
    
    Args:
        client_exchange: ClientExchangeAccount instance

        as_of_date: Optional date to calculate as of (for time-travel). If None, uses current state.
    
    Returns:
        dict with placeholder values - replace with your calculations

    """
    # TODO: Add your new formulas and logic here
    return {
        "total_funding": Decimal(0),
        "exchange_balance": Decimal(0),
        "client_profit_loss": Decimal(0),
        "is_profit": False,
        "latest_balance_record": None,
    }


def calculate_admin_profit_loss(client_profit_loss, settings, admin_profit_share_pct=None, client_exchange=None):


    """
    TODO: Add your new calculation logic here.
    
    Args:
        client_profit_loss: Client's profit (positive) or loss (negative)

        settings: SystemSettings instance
        admin_profit_share_pct: Optional admin profit share percentage. If None, uses settings.admin_profit_share_pct
        client_exchange: Optional ClientExchangeAccount instance for company share calculation
    
    Returns:
        dict with placeholder values - replace with your calculations

    """
    # TODO: Add your new formulas and logic here
    return {
        "admin_earns": Decimal(0),
        "admin_pays": Decimal(0),
        "company_earns": Decimal(0),
        "company_pays": Decimal(0),
        "admin_net": Decimal(0),
        "admin_bears": Decimal(0),
        "admin_profit_share_pct_used": Decimal(0),
        "admin_profit": Decimal(0),
            "admin_loss": Decimal(0),
            "company_share_profit": Decimal(0),
        "company_share_loss": Decimal(0),
        }


def login_view(request):
    """
    Secure login view with rate limiting and account lockout protection.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")
    
    # Get client IP for rate limiting
    ip_address = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '127.0.0.1')
    login_rate_limit_key = f'login_rate_limit:{ip_address}'
    
    if request.method == "POST":
        # Check rate limit for login attempts
        login_attempts = cache.get(login_rate_limit_key, 0)
        max_login_attempts = getattr(settings, 'LOGIN_RATE_LIMIT_REQUESTS', 5)
        login_window = getattr(settings, 'LOGIN_RATE_LIMIT_WINDOW', 300)  # 5 minutes
        
        if login_attempts >= max_login_attempts:
            logger.warning(f'Login rate limit exceeded for IP: {ip_address}')
            return render(request, "core/auth/login.html", {
                "error": "Too many login attempts. Please try again in 5 minutes."
            })
        
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        
        # Validate input
        if not username or not password:
            cache.set(login_rate_limit_key, login_attempts + 1, login_window)
            return render(request, "core/auth/login.html", {
                "error": "Username and password are required."
            })
        
        # Check for account lockout (per username)
        username_lockout_key = f'login_lockout:{username}'
        lockout_until = cache.get(username_lockout_key)
        if lockout_until and time.time() < lockout_until:
            remaining_time = int((lockout_until - time.time()) / 60) + 1
            return render(request, "core/auth/login.html", {
                "error": f"Account temporarily locked. Try again in {remaining_time} minute(s)."
            })
        
        # Authenticate user
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Successful login - reset rate limit
            cache.delete(login_rate_limit_key)
            cache.delete(username_lockout_key)
            login(request, user)
            logger.info(f'Successful login for user: {username} from IP: {ip_address}')
            return redirect("dashboard")
        else:
            # Failed login - increment rate limit
            cache.set(login_rate_limit_key, login_attempts + 1, login_window)
            
            # Lock account after max attempts
            if login_attempts + 1 >= max_login_attempts:
                lockout_duration = login_window  # Lock for the same duration as rate limit window
                cache.set(username_lockout_key, time.time() + lockout_duration, lockout_duration)
                logger.warning(f'Account locked for username: {username} from IP: {ip_address}')
            
            # Generic error message (don't reveal if username exists)
            return render(request, "core/auth/login.html", {
                "error": "Invalid username or password."
            })
    
    return render(request, "core/auth/login.html")


def csrf_failure(request, reason=""):
    """
    Custom CSRF failure view with logging.
    """
    logger.warning(f'CSRF failure: {reason} from IP: {request.META.get("REMOTE_ADDR")}')
    return render(request, "core/auth/csrf_error.html", {
        "error": "Security verification failed. Please try again."
    }, status=403)


def logout_view(request):
    """Logout view."""
    logout(request)
    return redirect("login")


def generate_otp():
    """Generate a 6-digit OTP code."""
    return ''.join(random.choices(string.digits, k=6))


def send_otp_email(email, username, otp_code):
    """Send OTP code to user's email."""
    subject = 'Verify Your Email - Transaction Hub'
    message = f"""
Hello {username},

Thank you for signing up for Transaction Hub!

Your email verification code is: {otp_code}

This code will expire in 10 minutes.

If you didn't request this code, please ignore this email.

Best regards,
Transaction Hub Team
"""
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error(f'Failed to send OTP email to {email}: {str(e)}')
        return False


def signup_view(request):
    """
    Signup view - collects username and email, sends OTP for verification.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")
    
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            
            # Generate OTP
            otp_code = generate_otp()
            expires_at = timezone.now() + timedelta(minutes=10)
            
            # Delete any existing OTP for this email
            EmailOTP.objects.filter(email=email).delete()
            
            # Create new OTP record
            email_otp = EmailOTP.objects.create(
                email=email,
                username=username,
                otp_code=otp_code,
                expires_at=expires_at
            )
            
            # Send OTP email
            if send_otp_email(email, username, otp_code):
                # Store email, username, and password in session for verification step
                request.session['signup_email'] = email
                request.session['signup_username'] = username
                request.session['signup_password'] = password
                return redirect('verify_otp')
            else:
                # If email sending fails, delete the OTP record
                email_otp.delete()
                return render(request, "core/auth/signup.html", {
                    "form": form,
                    "error": "Failed to send verification email. Please try again."
                })
    else:
        form = SignupForm()
    
    return render(request, "core/auth/signup.html", {"form": form})


def verify_otp_view(request):
    """
    OTP verification view - verifies OTP and creates user account.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")
    
    # Check if user came from signup
    email = request.session.get('signup_email')
    username = request.session.get('signup_username')
    password = request.session.get('signup_password')
    
    if not email or not username or not password:
        return redirect('signup')
    
    if request.method == "POST":
        form = OTPVerificationForm(request.POST, email=email)
        if form.is_valid():
            otp_code = form.cleaned_data['otp_code']
            
            try:
                email_otp = EmailOTP.objects.get(email=email, otp_code=otp_code, is_verified=False)
                
                # Verify username matches
                if email_otp.username != username:
                    return render(request, "core/auth/verify_otp.html", {
                        "form": form,
                        "email": email,
                        "error": "Invalid verification code. Please try again."
                    })
                
                # Check if OTP is expired
                if email_otp.is_expired():
                    return render(request, "core/auth/verify_otp.html", {
                        "form": form,
                        "email": email,
                        "error": "OTP code has expired. Please request a new one."
                    })
                
                # Verify OTP
                email_otp.is_verified = True
                email_otp.save()
                
                # Create user account
                try:
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password
                    )
                    user.is_active = True
                    user.save()
                    
                    # Send welcome email
                    try:
                        send_mail(
                            'Welcome to Transaction Hub',
                            f"""
Hello {username},

Your account has been successfully created!

You can now login with your username and password at:
{request.build_absolute_uri(reverse('login'))}

Best regards,
Transaction Hub Team
""",
                            settings.DEFAULT_FROM_EMAIL,
                            [email],
                            fail_silently=False,
                        )
                    except Exception as e:
                        logger.warning(f'Failed to send welcome email to {email}: {str(e)}')
                    
                    # Clear session data
                    del request.session['signup_email']
                    del request.session['signup_username']
                    del request.session['signup_password']
                    
                    # Log the user in
                    login(request, user)
                    
                    logger.info(f'New user account created: {username} ({email})')
                    
                    return redirect("dashboard")
                except Exception as e:
                    logger.error(f'Failed to create user account: {str(e)}')
                    return render(request, "core/auth/verify_otp.html", {
                        "form": form,
                        "email": email,
                        "error": "Failed to create account. Please try again."
                    })
                
            except EmailOTP.DoesNotExist:
                return render(request, "core/auth/verify_otp.html", {
                    "form": form,
                    "email": email,
                    "error": "Invalid OTP code. Please check and try again."
                })
    else:
        form = OTPVerificationForm(email=email)
    
    return render(request, "core/auth/verify_otp.html", {
        "form": form,
        "email": email
    })


@require_http_methods(["POST"])
def resend_otp_view(request):
    """
    Resend OTP code to user's email.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")
    
    email = request.session.get('signup_email')
    username = request.session.get('signup_username')
    password = request.session.get('signup_password')
    
    if not email or not username or not password:
        return redirect('signup')
    
    # Generate new OTP
    otp_code = generate_otp()
    expires_at = timezone.now() + timedelta(minutes=10)
    
    # Delete old OTP and create new one
    EmailOTP.objects.filter(email=email).delete()
    email_otp = EmailOTP.objects.create(
        email=email,
        username=username,
        otp_code=otp_code,
        expires_at=expires_at
    )
    
    # Send new OTP email
    if send_otp_email(email, username, otp_code):
        from django.contrib import messages
        messages.success(request, 'A new verification code has been sent to your email.')
        return redirect('verify_otp')
    else:
        email_otp.delete()
        return render(request, "core/auth/verify_otp.html", {
            "form": OTPVerificationForm(email=email),
            "email": email,
            "error": "Failed to send verification email. Please try again."
        })


@login_required
def dashboard(request):


    """Minimal dashboard view summarizing key metrics with filters."""

    today = date.today()

    # Filters
    client_id = request.GET.get("client")
    exchange_id = request.GET.get("exchange")
    search_query = request.GET.get("search", "")
    # Get client_type from GET (to update session) or from session
    client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type_filter == '':
        client_type_filter = 'all'
    
    # Base queryset
    transactions_qs = Transaction.objects.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").filter(client_exchange__client__user=request.user)
    
    # All clients are now "my clients" - no filtering needed
    
    if client_id:
        transactions_qs = transactions_qs.filter(client_exchange__client_id=client_id)

    if exchange_id:
        transactions_qs = transactions_qs.filter(client_exchange__exchange_id=exchange_id)

    if search_query:
        transactions_qs = transactions_qs.filter(
            Q(client_exchange__client__name__icontains=search_query) |
            Q(client_exchange__client__code__icontains=search_query) |
            Q(client_exchange__exchange__name__icontains=search_query)
        )

    # CORRECTNESS LOGIC: Turnover = Σ(|ExchangeBalanceAfter − ExchangeBalanceBefore|) for TRADE transactions only
    # Turnover measures trading activity, NOT funding or settlements
    trade_qs = transactions_qs.filter(type='TRADE').exclude(
        exchange_balance_before__isnull=True
    ).exclude(
        exchange_balance_after__isnull=True
    )
    # Calculate turnover as sum of absolute exchange balance movements from trades
    total_turnover = sum(
        abs(tx.exchange_balance_after - tx.exchange_balance_before)
        for tx in trade_qs
    ) or 0
    your_profit = 0  # Computed from accounts, not transactions
    # Company profit removed - no longer applicable
    company_profit = Decimal(0)

    # Pending sections removed - no longer using PendingAmount model
    pending_clients_owe = Decimal(0)
    
    # Pending payments computed from accounts, not transactions
    pending_you_owe_clients = Decimal(0)  # Computed from accounts where Client_PnL > 0

    # All clients (scoped to current user)
    clients_qs = Client.objects.filter(user=request.user)
    
    # Active clients count
    active_clients_count = clients_qs.count()
    
    # Calculate current balance for selected client(s) and exchange
    current_balance = Decimal(0)
    has_transactions = False
    
    if client_id:
        client = Client.objects.filter(pk=client_id, user=request.user).first()
        if client:
                # Specific exchange selected - show balance for that exchange only
                client_exchange = client.exchange_accounts.filter(exchange_id=exchange_id).first()



                if client_exchange:




                    # Check if there are any transactions for this exchange

                    has_transactions = Transaction.objects.filter(client_exchange=client_exchange).exists()




                    if has_transactions:
                        current_balance = get_exchange_balance(client_exchange)
                else:










                # No exchange selected - calculate total balance across all exchanges
                    client_exchanges = client.exchange_accounts.all()
                for ce in client_exchanges:
                    # Only include exchanges that have transactions
                    if Transaction.objects.filter(client_exchange=ce).exists():
                        has_transactions = True
                        current_balance += get_exchange_balance(ce)
    
    if client_type_filter:
        # Filtered by client type

        filtered_clients = clients_qs

        for client in filtered_clients:
            if exchange_id:

                # Specific exchange selected
                client_exchange = client.exchange_accounts.filter(exchange_id=exchange_id).first()


                if client_exchange:
                    if Transaction.objects.filter(client_exchange=client_exchange).exists():
                        has_transactions = True


                        current_balance += get_exchange_balance(client_exchange)
        
        # TODO: Fix else block logic - structure needs to be corrected
        # else:



                # All exchanges
            # TODO: Fix indentation - client_exchanges = client.exchange_accounts.all()


        # TODO: Fix indentation - for ce in client_exchanges:


            # TODO: Fix indentation - if Transaction.objects.filter(client_exchange=ce).exists():


                # TODO: Fix indentation - has_transactions = True



                # TODO: Fix indentation - current_balance += get_exchange_balance(ce)




    # Get all accounts for the current user
    all_accounts = ClientExchangeAccount.objects.filter(client__user=request.user).select_related("client", "exchange")
    
    # Calculate totals from accounts
    total_funding = sum(account.funding for account in all_accounts)
    total_exchange_balance = sum(account.exchange_balance for account in all_accounts)
    total_client_pnl = sum(account.compute_client_pnl() for account in all_accounts)
    
    # Check if this is the payments dashboard
    is_payments_dashboard = request.resolver_match.url_name == 'payments_dashboard'

    if is_payments_dashboard:
        # For payments dashboard: show client-payments ledger metrics (cash + pending).
        from .models import PendingPaymentTransaction
        payment_transactions = (
            PendingPaymentTransaction.objects.filter(client__user=request.user)
            .select_related("client", "client_exchange", "client_exchange__exchange")
        )

        total_received = sum(tx.amount for tx in payment_transactions if tx.type == "RECEIVED")
        total_paid = sum(tx.amount for tx in payment_transactions if tx.type == "GIVEN")
        net_profit = int(total_received) - int(total_paid)

        all_clients_for_pending = Client.objects.filter(user=request.user)
        pending_receivable = sum(c.pending_balance for c in all_clients_for_pending if c.pending_balance > 0)
        pending_payable = abs(sum(c.pending_balance for c in all_clients_for_pending if c.pending_balance < 0))
        net_pending = int(pending_receivable) - int(pending_payable)

        total_my_share = net_profit
        recent_payment_transactions = payment_transactions.order_by("-date", "-id")[:10]
    else:
        # FINANCIAL INTERPRETATION: Apply sign to Total My Share
        # - If client_pnl < 0 (LOSS): Client owes you → share is POSITIVE
        # - If client_pnl > 0 (PROFIT): You owe client → share is NEGATIVE
        total_my_share = Decimal(0)
        for account in all_accounts:
            client_pnl = account.compute_client_pnl()
            share_amount = account.compute_my_share()
            if client_pnl < 0:
                # LOSS CASE: Client owes you → share is POSITIVE
                total_my_share += share_amount
            elif client_pnl > 0:
                # PROFIT CASE: You owe client → share is NEGATIVE
                total_my_share -= share_amount
            # If client_pnl == 0, share is 0, so no change
        recent_payment_transactions = None
        total_received = None
        total_paid = None
        net_profit = None
        pending_receivable = None
        pending_payable = None
        net_pending = None
    
    # Count totals
    total_clients = Client.objects.filter(user=request.user).count()
    total_exchanges = Exchange.objects.count()
    total_accounts = all_accounts.count()
    
    # Get recent accounts (last 10 updated)
    recent_accounts = all_accounts.order_by("-updated_at")[:10]
    
    context = {
        "today": today,
        "total_clients": total_clients,
        "total_exchanges": total_exchanges,
        "total_accounts": total_accounts,
        "total_funding": total_funding,
        "total_exchange_balance": total_exchange_balance,
        "total_client_pnl": total_client_pnl,
        "total_my_share": total_my_share,
        # Payments dashboard metrics (only meaningful when payments_dashboard)
        "payments_total_received": total_received,
        "payments_total_paid": total_paid,
        "payments_net_profit": net_profit,
        "payments_pending_receivable": pending_receivable,
        "payments_pending_payable": pending_payable,
        "payments_net_pending": net_pending,
        "recent_payment_transactions": recent_payment_transactions,
        "recent_accounts": recent_accounts,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "pending_clients_owe": pending_clients_owe,
        "pending_you_owe_clients": pending_you_owe_clients,
        "active_clients_count": active_clients_count,
        "total_exchanges_count": Exchange.objects.count(),
        "recent_transactions": transactions_qs.order_by("-created_at", "-id")[:10],
        "all_clients": clients_qs.order_by("name"),
        "all_exchanges": Exchange.objects.all().order_by("name"),
        "selected_client": int(client_id) if client_id else None,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "search_query": search_query,
        "client_type_filter": client_type_filter,
        "current_balance": current_balance,
        "has_transactions": has_transactions,
    }
    return render(request, "core/dashboard.html", context)


@login_required


def client_list(request):


    """List all clients (both company and my clients)"""
    client_search = request.GET.get("client_search", "")
    exchange_id = request.GET.get("exchange", "")
    
    clients = Client.objects.filter(user=request.user).order_by("name")
    
    # Filter by client name or code
    if client_search:
        clients = clients.filter(
            Q(name__icontains=client_search) | Q(code__icontains=client_search)
        )
    
    # Filter by exchange
    if exchange_id:
        clients = clients.filter(
            exchange_accounts__exchange_id=exchange_id
        ).distinct()
    
    # Get all exchanges for dropdown
    all_exchanges = Exchange.objects.all().order_by("name")
    
    return render(request, "core/clients/list.html", {
        "clients": clients,
        "client_search": client_search,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "all_exchanges": all_exchanges,
        "client_type": "all",
    })


@login_required


@login_required


def my_clients_list(request):


    """List only my (personal) clients"""
    client_search = request.GET.get("client_search", "")
    exchange_id = request.GET.get("exchange", "")
    
    clients = Client.objects.filter(user=request.user).order_by("name")
    
    # Filter by client name or code
    if client_search:
        clients = clients.filter(
            Q(name__icontains=client_search) | Q(code__icontains=client_search)
        )
    
    # Filter by exchange
    if exchange_id:
        clients = clients.filter(
            exchange_accounts__exchange_id=exchange_id
        ).distinct()
    
    # Get all exchanges for dropdown
    all_exchanges = Exchange.objects.all().order_by("name")
    
    return render(request, "core/clients/list.html", {
        "clients": clients,
        "client_search": client_search,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "all_exchanges": all_exchanges,
        "client_type": "my",
    })


@login_required




def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk, user=request.user)

    # Get all exchange accounts for this client
    accounts = client.exchange_accounts.select_related("exchange").all()

    # Client-payments view: keep pending balances consistent and auto-seed dues when missing.
    # This prevents stale client.pending_balance values (e.g. after deleting an account)
    # and ensures a newly-loss/profit account surfaces a pending due even before running
    # "Generate pending dues" from the settlements page.
    if request.resolver_match and request.resolver_match.url_name == "payments_client_detail":
        from .models import PendingPaymentTransaction
        with db_transaction.atomic():
            client = Client.objects.select_for_update().get(pk=client.pk, user=request.user)
            accounts_locked = (
                ClientExchangeAccount.objects.select_for_update()
                .select_related("exchange")
                .filter(client=client)
                .all()
            )

            # Client-payments: `account.pending_balance` is the source of truth.
            # It is mutated only by:
            # - "Generate pending dues" (adds your personal share)
            # - Recording real payments (PendingPaymentTransaction.save/delete)
            # Do NOT recompute/overwrite account.pending_balance here, otherwise it will "flip" unpredictably.
            client_total = sum(int(acc.pending_balance or 0) for acc in accounts_locked)

            legacy_paid = (
                PendingPaymentTransaction.objects.filter(
                    client=client, client_exchange__isnull=True, type="GIVEN"
                ).aggregate(total=Sum("amount"))["total"]
                or 0
            )
            legacy_received = (
                PendingPaymentTransaction.objects.filter(
                    client=client, client_exchange__isnull=True, type="RECEIVED"
                ).aggregate(total=Sum("amount"))["total"]
                or 0
            )
            client_total += int(legacy_paid) - int(legacy_received)
            client.pending_balance = int(client_total)
            client.save(update_fields=["pending_balance"])

        # Refresh querysets after potential updates
        accounts = client.exchange_accounts.select_related("exchange").all()

        # For client-payments UI, show ONLY "My Own %" and corresponding share (company split excluded).
        from decimal import Decimal, ROUND_FLOOR
        for acc in accounts:
            pnl_now = int(acc.compute_client_pnl() or 0)
            abs_pnl = abs(int(pnl_now))
            own_pct = Decimal(str(acc.my_own_percentage or 0))
            total_pct = Decimal(str(acc.my_percentage or 0))
            pct_used = own_pct if own_pct > 0 else total_pct
            acc.display_my_pct = pct_used
            if abs_pnl > 0 and pct_used > 0:
                exact = Decimal(abs_pnl) * (pct_used / Decimal("100"))
                acc.display_my_share = int(exact.to_integral_value(rounding=ROUND_FLOOR))
            else:
                acc.display_my_share = 0

    # Calculate totals
    total_funding = sum(account.funding for account in accounts)
    total_exchange_balance = sum(account.exchange_balance for account in accounts)
    total_client_pnl = sum(account.compute_client_pnl() for account in accounts)

    # Per-exchange settlement summary (who owes whom, remaining amount)
    exchange_settlements = []
    if request.resolver_match and request.resolver_match.url_name == "payments_client_detail":
        # Client-payments: drive from the per-account pending ledger (real cash settlements)
        for account in accounts:
            pending = int(account.pending_balance or 0)
            if pending == 0:
                continue
            label = account.exchange.code or account.exchange.name
            exchange_settlements.append({
                "account": account,
                "exchange_label": label,
                "remaining": abs(pending),
                "client_owes_me": pending > 0,
            })
    else:
        # Trading settlements: drive from masked-share settlement tracker
        for account in accounts:
            pnl = account.compute_client_pnl()
            account.lock_initial_share_if_needed()
            info = account.get_remaining_settlement_amount()
            remaining = info["remaining"]
            if remaining <= 0:
                continue
            label = account.exchange.code or account.exchange.name
            exchange_settlements.append({
                "account": account,
                "exchange_label": label,
                "remaining": remaining,
                "client_owes_me": pnl < 0,
            })

    # Totals for client-payments detail: how much client needs to pay you, and you need to pay client
    total_client_owes_me = sum(
        item["remaining"] for item in exchange_settlements if item["client_owes_me"]
    )
    total_i_owe_client = sum(
        item["remaining"] for item in exchange_settlements if not item["client_owes_me"]
    )

    transactions = (
        Transaction.objects.filter(client_exchange__client=client)
        .select_related("client_exchange", "client_exchange__exchange")
        .order_by("-created_at", "-id")[:50]
    )
    
    return render(
        request,
        "core/clients/detail.html",
        {
            "client": client,
            "accounts": accounts,
            "total_funding": total_funding,
            "total_exchange_balance": total_exchange_balance,
            "total_client_pnl": total_client_pnl,
            "exchange_settlements": exchange_settlements,
            "total_client_owes_me": total_client_owes_me,
            "total_i_owe_client": total_i_owe_client,
            "transactions": transactions,
        },
    )


@login_required


def client_give_money(request, client_pk):


    """
    Give money to a client for a specific exchange (FUNDING transaction).
    Funding ONLY increases exchange balance. It does NOT affect pending.
    """
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    
    if request.method == "POST":

        tx_date = request.POST.get("date")
        amount = round_share(Decimal(request.POST.get("amount", 0) or 0))  # Share-space: round DOWN
        note = request.POST.get("note", "")
        
        if client_exchange_id and tx_date and amount > 0:


            
            # Get current exchange balance
            current_balance = get_exchange_balance(client_exchange)

            
            # Create FUNDING transaction
            transaction = Transaction.objects.create(

                client_exchange=client_exchange,

                date=datetime.strptime(tx_date, "%Y-%m-%d").date(),

                type='FUNDING',

                amount=amount,

                exchange_balance_after=account.exchange_balance,
                notes=note,

            )

            
            # Update exchange balance by creating/updating balance record
            # Funding increases exchange balance
            new_balance = current_balance + amount

    # TODO: ClientDailyBalance model removed - add back if needed
    # ClientDailyBalance.objects.update_or_create(
    #     client_exchange=client_exchange,
    #     date=datetime.strptime(tx_date, "%Y-%m-%d").date(),
    #     defaults={
    #         "remaining_balance": new_balance,
    #         "extra_adjustment": Decimal(0),
    #         "note": note or f"Funding: +₹{amount}",
    #     }
    # )
            # Funding does NOT affect pending (separate ledger)
            
            # Redirect to client detail
            return redirect("client_detail", pk=client.pk)
    
    # If GET or validation fails, redirect back to client detail
    return redirect("client_detail", pk=client.pk)


@login_required


def settle_payment(request):
    
    
    """
    Simple settlement - creates a SETTLEMENT transaction.
    All partial payment logic, old balance calculations, and formulas have been removed.
    """
    if request.method == "POST":

        from django.shortcuts import get_object_or_404, redirect
        from django.urls import reverse
        from decimal import Decimal
        from core.models import Client, ClientExchangeAccount, Transaction
        from core.utils.money import round_share
        
        client_id = request.POST.get("client_id")
        client_exchange_id = request.POST.get("client_exchange_id")
        amount_raw = request.POST.get("amount", "0") or "0"
        amount = round_share(Decimal(str(amount_raw)))
        tx_date = request.POST.get("date")
        note = request.POST.get("note", "")
        payment_type = request.POST.get("payment_type", "client_pays")
        
        report_type = request.POST.get("report_type") or request.GET.get("report_type", "weekly")
        client_type_filter = request.POST.get("client_type") or request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
        if client_type_filter == '':
            client_type_filter = 'all'

        request.session['client_type_filter'] = client_type_filter
        
        if client_id and client_exchange_id and amount > 0 and tx_date:
            try:
                client = get_object_or_404(Client, pk=client_id, user=request.user)
                client_exchange = get_object_or_404(ClientExchangeAccount, pk=client_exchange_id, client=client)
                
                from django.db import transaction as db_transaction
                from django.contrib import messages
                with db_transaction.atomic():
                    # CORRECTNESS LOGIC: Sign depends ONLY on Client_PnL at time of payment
                    # IF Client_PnL > 0 (client in profit): Transaction.amount = -SharePayment (you paid client)
                    # ELSE IF Client_PnL < 0 (client in loss): Transaction.amount = +SharePayment (client paid you)
                    client_pnl = client_exchange.compute_client_pnl()
                    if client_pnl > 0:
                        # PROFIT CASE: YOU pay client → amount is NEGATIVE (your loss)
                        transaction_amount = -amount
                    elif client_pnl < 0:
                        # LOSS CASE: Client pays YOU → amount is POSITIVE (your profit)
                        transaction_amount = amount
                    else:
                        # PnL = 0 (should not happen, but handle gracefully)
                        transaction_amount = 0
                    
                    # Legacy settle_payment - doesn't update balances, just records transaction
                    # Set before = after since balances don't change
                    funding_before = client_exchange.funding
                    exchange_before = client_exchange.exchange_balance
                    
                    Transaction.objects.create(
    client_exchange=client_exchange,
                        type='SETTLEMENT_SHARE',  # Use new type
                            amount=transaction_amount,  # Positive if client pays you, negative if you pay client
                        date=timezone.make_aware(datetime.strptime(tx_date, "%Y-%m-%d")) if isinstance(tx_date, str) else tx_date,
                        funding_before=funding_before,
                        funding_after=client_exchange.funding,
                        exchange_balance_before=exchange_before,
                        exchange_balance_after=client_exchange.exchange_balance,
                        notes=note or f"Settlement: ₹{amount} ({payment_type})"
                    )
                    
                    messages.success(request, f"Settlement of ₹{amount} recorded successfully.")
                    
                    redirect_url = f"?section={'clients-owe' if payment_type == 'client_pays' else 'you-owe'}&report_type={report_type}"
                    if client_type_filter and client_type_filter != 'all':
                        redirect_url += f"&client_type={client_type_filter}"
                    return redirect(reverse("pending_summary") + redirect_url)
            except Exception as e:
                redirect_url = f"?report_type={report_type}"
                if client_type_filter and client_type_filter != 'all':
                    redirect_url += f"&client_type={client_type_filter}"
                return redirect(reverse("pending_summary") + redirect_url)
                    
    
    # If GET or validation fails, redirect to pending summary
    from django.shortcuts import redirect
    from django.urls import reverse
    report_type = request.GET.get("report_type", "weekly")
    return redirect(reverse("pending_summary") + f"?report_type={report_type}")


@login_required
def client_create(request):
    """Create a new client
    
    Rules:
    - Client code must be UNIQUE if provided (non-NULL)
    - Client code can be EMPTY/NULL
    - Multiple clients can have the same name
    - If client code is NULL, the index (ID) will always be different
    - Two clients must NEVER have the same non-NULL client code
    """
    if request.method == "POST":
        from django.contrib import messages
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError
        
        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip()
        referred_by = request.POST.get("referred_by", "").strip()
        
        # CRITICAL: Convert empty string to None (required for UNIQUE constraint)
        # Empty strings ('') conflict with UNIQUE, but NULL values don't
        code = code if code else None
        
        if not name:
            messages.error(request, "Client name is required.")
            return render(request, "core/clients/create.html", {
                'code': code or '',
                'referred_by': referred_by,
            })
        
        # Check for duplicate code BEFORE saving (user-friendly error)
        if code is not None:
            existing_client = Client.objects.filter(code=code).first()
            if existing_client:
                messages.error(
                    request,
                    f"Client code '{code}' is already in use by client '{existing_client.name}'. "
                    f"Please choose a different code or leave it blank."
                )
                return render(request, "core/clients/create.html", {
                    'name': name,
                    'code': code,
                    'referred_by': referred_by,
                })
        
        try:
            # Create client
            client = Client(
                user=request.user,
                name=name,
                code=code,  # Already None if empty
                referred_by=referred_by if referred_by else None,
            )
            # This will call clean() and save()
            client.save()
            
            messages.success(request, f"Client '{name}' has been created successfully.")
            return redirect(reverse("client_list"))
            
        except ValidationError as e:
            # Handle validation errors from model.clean()
            messages.error(request, str(e))
            return render(request, "core/clients/create.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })
        except IntegrityError as e:
            # Handle database integrity errors (shouldn't happen with pre-check, but safety net)
            if 'unique constraint' in str(e).lower() or 'duplicate' in str(e).lower():
                messages.error(
                    request,
                    f"Client code '{code}' is already in use. Please choose a different code or leave it blank."
                )
            else:
                messages.error(request, f"Error creating client: {str(e)}")
            return render(request, "core/clients/create.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })
        except Exception as e:
            messages.error(request, f"Error creating client: {str(e)}")
            return render(request, "core/clients/create.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })
    
    return render(request, "core/clients/create.html")


@login_required
def my_client_create(request):
    """Create a my (personal) client
    
    Rules:
    - Client code must be UNIQUE if provided (non-NULL)
    - Client code can be EMPTY/NULL
    - Multiple clients can have the same name
    - If client code is NULL, the index (ID) will always be different
    - Two clients must NEVER have the same non-NULL client code
    """
    if request.method == "POST":
        from django.shortcuts import redirect
        from django.urls import reverse
        from django.contrib import messages
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError
        from core.models import Client

        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip()
        referred_by = request.POST.get("referred_by", "").strip()
        
        # CRITICAL: Convert empty string to None (required for UNIQUE constraint)
        # Empty strings ('') conflict with UNIQUE, but NULL values don't
        code = code if code else None
        
        if not name:
            messages.error(request, "Client name is required.")
            return render(request, "core/clients/create_my.html", {
                'code': code or '',
                'referred_by': referred_by,
            })
        
        # Check for duplicate code BEFORE saving (user-friendly error)
        if code is not None:
            existing_client = Client.objects.filter(code=code).first()
            if existing_client:
                messages.error(
                    request,
                    f"Client code '{code}' is already in use by client '{existing_client.name}'. "
                    f"Please choose a different code or leave it blank."
                )
                return render(request, "core/clients/create_my.html", {
                    'name': name,
                    'code': code,
                    'referred_by': referred_by,
                })
        
        try:
            # Create client
            client = Client(
                user=request.user,
                name=name,
                code=code,  # Already None if empty
                referred_by=referred_by if referred_by else None,
            )
            # This will call clean() and save()
            client.save()
            
            messages.success(request, f"Client '{name}' has been created successfully.")
            return redirect("client_list")
            
        except ValidationError as e:
            # Handle validation errors from model.clean()
            messages.error(request, str(e))
            return render(request, "core/clients/create_my.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })
        except IntegrityError as e:
            # Handle database integrity errors (shouldn't happen with pre-check, but safety net)
            if 'unique constraint' in str(e).lower() or 'duplicate' in str(e).lower():
                messages.error(
                    request,
                    f"Client code '{code}' is already in use. Please choose a different code or leave it blank."
                )
            else:
                messages.error(request, f"Error creating client: {str(e)}")
            return render(request, "core/clients/create_my.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })
        except Exception as e:
            messages.error(request, f"Error creating client: {str(e)}")
            return render(request, "core/clients/create_my.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })

    return render(request, "core/clients/create_my.html")


@login_required
def client_delete(request, pk):


    """
    Permanently delete a client and all related data.

    ⚠️ This is a HARD DELETE:
        - Deletes ClientExchangeAccount rows for this client

       - Cascades to Transactions, LossSnapshots, balances, ledgers, etc.
       - Use only when you truly want to wipe this client from the system.
    """
    # Get client - check if it exists and belongs to the user
    # If client has no user assigned (None), allow deletion (legacy data)
    try:
        client = Client.objects.get(pk=pk)
        # Check if user matches, or if client has no user assigned (allow deletion)
        if client.user is not None and client.user != request.user:
            from django.http import Http404
            raise Http404("Client not found")
    except Client.DoesNotExist:
        from django.contrib import messages
        messages.error(request, "Client not found. It may have been already deleted.")
        return redirect(reverse("client_list"))
    
    if request.method == "POST":
        # Store client name before deletion for success/error messages
        client_name = client.name
        
        try:
            # First delete all related objects for each client-exchange
            client_exchanges = ClientExchangeAccount.objects.filter(client=client)

            for ce in client_exchanges:
                # Delete loss snapshots (must go before ClientDailyBalance if PROTECT is used)
                # LossSnapshot.objects.filter(client_exchange=ce).delete()

                # Delete derived daily balance snapshots (reporting cache)
                # DailyBalanceSnapshot.objects.filter(client_exchange=ce).delete()

                # Delete daily balance records linked via client_exchange
                # ClientDailyBalance.objects.filter(client_exchange=ce).delete()

                # Delete outstanding ledgers
                # OutstandingAmount.objects.filter(client_exchange=ce).delete()

                # Delete all transactions
                Transaction.objects.filter(client_exchange=ce).delete()

                # Finally delete the client-exchange itself
                ce.delete()


            # TODO: ClientDailyBalance model removed
            # Delete legacy ClientDailyBalance rows that reference client directly (no client_exchange)
            # ClientDailyBalance.objects.filter(client=client).delete()

            # Now delete the client itself
            client.delete()

            from django.contrib import messages
            messages.success(request, f"Client '{client_name}' has been deleted permanently.")
            
            return redirect(reverse("client_list"))
        except Exception as e:
            from django.contrib import messages


            import traceback

            error_msg = f"Error deleting client '{client_name}': {str(e)}"

            # Error logging removed to prevent BrokenPipeError - use Django logging instead
            import logging

            logger = logging.getLogger(__name__)

            try:

                logger.error(f"Error in client_delete: {traceback.format_exc()}")

            except:


                pass

            messages.error(request, error_msg)

            return redirect(reverse("client_list"))

    
    # If GET, show confirmation or redirect
    return redirect(reverse("client_detail", args=[client.pk]))


@login_required


def exchange_list(request):


    exchanges = Exchange.objects.all().order_by("name")

    return render(request, "core/exchanges/list.html", {"exchanges": exchanges})


@login_required


def transaction_list(request):


    """Transaction list with filtering options."""
    client_id = request.GET.get("client")
    exchange_id = request.GET.get("exchange")
    client_exchange_id = request.GET.get("client_exchange")  # Filter by specific client-exchange account
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    tx_type = request.GET.get("type")
    search_query = request.GET.get("search", "")
    # Get client_type from GET (to update session) or from session
    client_type = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type == '':

    
        pass
    transactions = Transaction.objects.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").filter(client_exchange__client__user=request.user)
    
    # All clients are now "my clients" - no filtering needed
    
    # Filter by specific client-exchange account (highest priority)
    selected_client_exchange_obj = None
    if client_exchange_id:
        try:
            # Validate that the client_exchange belongs to the current user
            selected_client_exchange_obj = ClientExchangeAccount.objects.select_related('client', 'exchange').get(
                pk=client_exchange_id,
                client__user=request.user
            )
            transactions = transactions.filter(client_exchange_id=client_exchange_id)
            # Pre-select client and exchange in dropdowns
            client_id = str(selected_client_exchange_obj.client_id)
            exchange_id = str(selected_client_exchange_obj.exchange_id)
        except (ClientExchangeAccount.DoesNotExist, ValueError):
            # Invalid client_exchange_id - ignore it
            client_exchange_id = None
            selected_client_exchange_obj = None
    
    if client_id and not client_exchange_id:
        transactions = transactions.filter(client_exchange__client_id=client_id)

    if exchange_id and not client_exchange_id:
        transactions = transactions.filter(client_exchange__exchange_id=exchange_id)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            transactions = transactions.filter(date__gte=start_date)
        except ValueError:
            pass

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            transactions = transactions.filter(date__lte=end_date)
        except ValueError:
            pass

    if tx_type:
        # Filter transactions by type
        # Map FUNDING_MANUAL to also include legacy FUNDING transactions
        if tx_type == 'FUNDING_MANUAL':
            transactions = transactions.filter(type__in=['FUNDING_MANUAL', 'FUNDING'])
        else:
            transactions = transactions.filter(type=tx_type)


    if search_query:
        transactions = transactions.filter(
            Q(client_exchange__client__name__icontains=search_query) |
            Q(client_exchange__client__code__icontains=search_query) |
            Q(client_exchange__exchange__name__icontains=search_query) |
            Q(client_exchange__exchange__code__icontains=search_query) |
            Q(notes__icontains=search_query)
        )
    
    # Order by created_at DESC, id DESC (Strict chronological order)
    try:
        transactions = transactions.order_by("-created_at", "-id")[:200]
    except (FieldError, AttributeError):
        # Fallback if field not found
        transactions = transactions.order_by("-id")[:200]
    
    # Filter clients based on client_type for the dropdown
    # All clients are now my clients - no filter needed
    all_clients_qs = Client.objects.filter(user=request.user)
    
    # Validate that selected client exists and belongs to the current user
    if client_id:
        try:
            Client.objects.get(pk=client_id, user=request.user)
        except Client.DoesNotExist:
            client_id = None
    
    return render(request, "core/transactions/list.html", {
        "transactions": transactions,
        "all_clients": all_clients_qs.order_by("name"),
        "all_exchanges": Exchange.objects.all().order_by("name"),
        "selected_client": int(client_id) if client_id else None,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "selected_client_exchange": int(client_exchange_id) if client_exchange_id else None,
        "selected_client_exchange_obj": selected_client_exchange_obj,  # For displaying name
        "start_date": start_date_str,
        "end_date": end_date_str,
        "selected_type": tx_type,
        "search_query": search_query,
        "client_type": client_type,
        "client_type_filter": client_type,  # For template conditional display
    })


def calculate_net_tallies_from_transactions(client_exchange, as_of_date=None):


    """
    TODO: Add your new calculation logic here.
    
    Args:
        client_exchange: ClientExchangeAccount instance

        as_of_date: Optional date to calculate as of. If None, uses all transactions.
    
    Returns:
        dict with placeholder values - replace with your calculations

    """
    # TODO: Add your new formulas and logic here
    return {
        "net_client_tally": Decimal(0),
        "net_company_tally": Decimal(0),
        "your_earnings": Decimal(0),
        "your_share_from_losses": Decimal(0),
        "your_share_from_profits": Decimal(0),
        "company_share_from_losses": Decimal(0),
        "company_share_from_profits": Decimal(0),
    }


@login_required
def pending_summary(request):
    """
    Settlements Summary.
    
    TODO: Add your new formulas and logic here.
    """
    from datetime import timedelta
    
    today = date.today()
    report_type = request.GET.get("report_type", "daily")  # daily, weekly, monthly
    search_query = request.GET.get("search", "").strip()
    # Get client_type from GET (to update session) or from session
    client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type_filter == '':
        pass
    # Update session to preserve client_type_filter for navigation bar
    request.session['client_type_filter'] = client_type_filter
    request.session.modified = True
    
    # Calculate date range based on report type (always current date)
    if report_type == "daily":
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    elif report_type == "weekly":
        start_date = today - timedelta(days=7)

        end_date = today
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        today_weekday = today.weekday()
        date_range_label = f"Weekly ({weekday_names[today_weekday]} to {weekday_names[today_weekday]}): {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    elif report_type == "monthly":
        day_of_month = today.day

        if today.month == 1:
            last_month = 12
            last_year = today.year - 1
        else:
            last_month = today.month - 1
            last_year = today.year


            last_month_days = (date(today.year, today.month, 1) - timedelta(days=1)).day

            start_date = date(today.year, last_month, min(day_of_month, last_month_days))

        end_date = today
        date_range_label = f"Monthly ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')})"
    else:
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    
    # Get all active client exchanges
    client_exchanges = ClientExchangeAccount.objects.filter(
        client__user=request.user,
    ).select_related("client", "exchange").all()
    
    # Filter by search query if provided
    if search_query:
        client_exchanges = client_exchanges.filter(
            Q(client__name__icontains=search_query) |
            Q(client__code__icontains=search_query) |
            Q(exchange__name__icontains=search_query) |
            Q(exchange__code__icontains=search_query)
        )
    
    # Filter by client type if specified
    # All clients are now my clients - no filter needed
    # client_exchanges already contains all clients
    
    # TODO: SystemSettings model removed - add back if needed
    # settings = SystemSettings.load()
    settings = None  # Placeholder
    
    # Check if admin wants to combine my share and company share (for client sharing)
    # Default to true (checked) if not specified in URL
    combine_shares_param = request.GET.get("combine_shares")
    if combine_shares_param is None:
        combine_shares = True
    else:

        combine_shares = combine_shares_param.lower() == "true"
    
    
    # Separate lists
    clients_owe_list = []  # Clients Need To Pay Me
    you_owe_list = []  # I Need To Pay Clients
    
    # WhatsApp number for all clients (requested by user)
    whatsapp_number = "9182351381"
    
    # Sort client_exchanges by client name to group them
    client_exchanges = client_exchanges.order_by('client__name', 'exchange__name')

    # Settlements page should show YOUR personal share by default:
    # - If my_own_percentage is configured (>0), use that.
    # - Otherwise fall back to my_percentage.
    from decimal import Decimal, ROUND_FLOOR

    def _share_from_pct(abs_pnl: int, pct: Decimal) -> int:
        if abs_pnl <= 0:
            return 0
        if pct is None:
            return 0
        pct = Decimal(str(pct))
        if pct <= 0:
            return 0
        exact = Decimal(abs_pnl) * (pct / Decimal("100"))
        return int(exact.to_integral_value(rounding=ROUND_FLOOR))

    for client_exchange in client_exchanges:
        client_pnl = int(client_exchange.compute_client_pnl() or 0)
        abs_pnl = abs(int(client_pnl))

        is_loss_case = client_pnl < 0
        is_profit_case = client_pnl > 0
        is_neutral_case = client_pnl == 0

        own_pct = Decimal(str(client_exchange.my_own_percentage or 0))
        total_pct = Decimal(str(client_exchange.my_percentage or 0))
        pct_used = own_pct if own_pct > 0 else total_pct

        share_used = _share_from_pct(abs_pnl, pct_used)
        show_na = is_neutral_case or share_used == 0

        item = {
            "client": client_exchange.client,
            "exchange": client_exchange.exchange,
            "account": client_exchange,
            "client_pnl": client_pnl,
            "amount_owed": abs_pnl if not is_neutral_case else 0,
            "my_share_amount": share_used,
            "remaining_amount": share_used if not show_na else 0,
            "share_percentage": pct_used,
            "show_na": show_na,
        }

        if is_loss_case or is_neutral_case:
            clients_owe_list.append(item)
        elif is_profit_case:
            you_owe_list.append(item)
    
    # Sort lists by client name first, then by amount (descending)
    def get_sort_key(item):
        client_name = item["client"].name.lower()
        if item.get("show_na", False):
            amount = 0
        elif "my_share_amount" in item:
            amount = abs(item["my_share_amount"])
        elif "amount_owed" in item:
            amount = abs(item["amount_owed"])
        elif "client_pnl" in item:
            amount = abs(item["client_pnl"])
        else:
            amount = 0
        # Primary sort by client name, secondary by amount (descending)
        # We use a tuple (client_name, -amount)
        return (client_name, -float(amount))
    
    clients_owe_list.sort(key=get_sort_key)
    you_owe_list.sort(key=get_sort_key)
    
    # Calculate totals (using remaining amounts for settlement tracking)
    total_clients_owe = sum(item.get("amount_owed", 0) for item in clients_owe_list)
    # Remaining amounts are already absolute values (calculated above)
    total_my_share_clients_owe = sum(item.get("remaining_amount", 0) for item in clients_owe_list)
    total_you_owe = sum(item.get("amount_owed", 0) for item in you_owe_list)
    # Remaining amounts are already absolute values (calculated above)
    total_my_share_you_owe = sum(item.get("remaining_amount", 0) for item in you_owe_list)
    
    # Get all clients for search dropdown
    all_clients = Client.objects.filter(user=request.user).order_by("name")
    
    context = {
        "clients_owe_you": clients_owe_list,
        "you_owe_clients": you_owe_list,
        "total_clients_owe": total_clients_owe,
        "total_my_share_clients_owe": total_my_share_clients_owe,
        "total_you_owe": total_you_owe,
        "total_my_share_you_owe": total_my_share_you_owe,
        "today": today,
        "report_type": report_type,
        "client_type_filter": client_type_filter,
        "start_date": start_date,
        "end_date": end_date,
        "date_range_label": date_range_label,
        "settings": settings,
        "combine_shares": combine_shares,
        "search_query": search_query,
        "all_clients": all_clients,
        "whatsapp_number": whatsapp_number,
    }
    return render(request, "core/pending/summary.html", context)


@login_required
@require_http_methods(["POST"])
def settle_all_payments(request):
    """
    Generate pending dues in client-payments for all accounts.

    NOTE:
    This action does NOT represent a real cash payment. It only calculates how much
    is due (your share) and reflects it into the pending ledger (`pending_balance`)
    so real payments can be recorded later from client-payments screens.
    """
    from django.db import transaction
    from django.core.exceptions import ValidationError
    from django.contrib import messages
    from .models import Settlement, PendingPaymentTransaction

    def _recalculate_pending_for_client(client_id: int):
        """
        Rebuild pending balances from source-of-truth records.

        IMPORTANT:
        In client-payments, `account.pending_balance` is a running ledger:
        - It is updated when you click "Generate pending dues"
        - It is updated when you record real payments (PendingPaymentTransaction.save/delete)

        So here we only rebuild `client.pending_balance` as:
          sum(account.pending_balance) + legacy(GIVEN - RECEIVED)
        """
        from .models import Client, ClientExchangeAccount, PendingPaymentTransaction
        from django.db.models import Sum

        client = Client.objects.select_for_update().get(pk=client_id, user=request.user)
        accounts = ClientExchangeAccount.objects.select_for_update().filter(client=client)

        client_total = sum(int(acc.pending_balance or 0) for acc in accounts)

        legacy_paid = (
            PendingPaymentTransaction.objects.filter(client=client, client_exchange__isnull=True, type="GIVEN")
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )
        legacy_received = (
            PendingPaymentTransaction.objects.filter(client=client, client_exchange__isnull=True, type="RECEIVED")
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )
        client_total += int(legacy_paid) - int(legacy_received)

        client.pending_balance = int(client_total)
        client.save(update_fields=["pending_balance"])

    # Get all account IDs for this user
    account_ids = list(
        ClientExchangeAccount.objects.filter(client__user=request.user).values_list("pk", flat=True)
    )
    settled_count = 0
    errors = []
    touched_client_ids = set()

    for account_id in account_ids:
        try:
            with transaction.atomic():
                account = (
                    ClientExchangeAccount.objects
                    .select_for_update()
                    .get(pk=account_id, client__user=request.user)
                )
                client_pnl_before = account.compute_client_pnl()

                if client_pnl_before == 0:
                    continue

                account.lock_initial_share_if_needed()
                # Total share (My Total %) for internal masked-settlement + cycle closing.
                share_total = int(account.compute_my_share() or 0)
                if share_total <= 0:
                    continue

                # Personal share for Client Payments pending ledger (My Own % when set).
                from decimal import Decimal, ROUND_FLOOR
                own_pct = Decimal(str(account.my_own_percentage or 0))
                if own_pct > 0:
                    exact_own = Decimal(str(abs(int(client_pnl_before)))) * (own_pct / Decimal("100"))
                    share_own = int(exact_own.to_integral_value(rounding=ROUND_FLOOR))
                else:
                    share_own = int(share_total)

                now = timezone.now()

                # Remove old incorrect "Settle all payments" payment entries (not real cash).
                PendingPaymentTransaction.objects.filter(
                    client_exchange=account,
                    notes__icontains="Settle all payments",
                ).delete()

                # 1) Add due into Client Payments pending ledger (ONLY ONCE per cycle)
                # +pending_balance => client owes me, -pending_balance => I owe client
                due_delta = int(share_own) if client_pnl_before < 0 else -int(share_own)
                if int(share_own) > 0 and due_delta != 0:
                    account.pending_balance = int(account.pending_balance) + int(due_delta)
                    account.save(update_fields=["pending_balance"])

                # 2) Internal settlement + auto-refunding (AUDIT)
                # This clears the "remaining share" in the settlement tracker and writes audit transactions
                # so they are visible on the exchange account page.
                #
                # IMPORTANT: still NOT a real cash payment. Real cash is recorded in client-payments.
                funding_before = int(account.funding)
                exchange_before = int(account.exchange_balance)

                masked_capital = int(account.compute_masked_capital(share_total) or 0)
                if masked_capital <= 0:
                    masked_capital = abs(int(client_pnl_before))

                settlement = Settlement.objects.create(
                    client_exchange=account,
                    amount=share_total,
                    date=now,
                    notes="Dues generated (Client Payments) - not a real payment",
                )

                if client_pnl_before < 0:
                    # LOSS: settlement reduces funding by masked capital (PnL -> 0)
                    if funding_before - masked_capital < 0:
                        errors.append(f"{account.client.name} / {account.exchange.name}: funding would go negative")
                        continue

                    funding_after_settlement = funding_before - masked_capital
                    exchange_after_settlement = exchange_before

                    account.funding = funding_after_settlement
                    account.exchange_balance = exchange_after_settlement
                    account.save(update_fields=["funding", "exchange_balance"])

                    Transaction.objects.create(
                        client_exchange=account,
                        date=now,
                        type="RECORD_PAYMENT",
                        amount=share_total,  # +ve: client owes me (loss case)
                        funding_before=funding_before,
                        funding_after=funding_after_settlement,
                        exchange_balance_before=exchange_before,
                        exchange_balance_after=exchange_after_settlement,
                        notes=f"Dues generated (not paid). Masked Capital: {masked_capital}. Linked Settlement ID: {settlement.id}",
                    )

                    # Auto re-funding: add masked capital back (restores original funding and exchange balance)
                    funding_before_refund = int(account.funding)
                    exchange_before_refund = int(account.exchange_balance)
                    account.funding = funding_before_refund + masked_capital
                    account.exchange_balance = exchange_before_refund + masked_capital
                    account.save(update_fields=["funding", "exchange_balance"])

                    Transaction.objects.create(
                        client_exchange=account,
                        date=now,
                        type="FUNDING_AUTO",
                        amount=masked_capital,
                        funding_before=funding_before_refund,
                        funding_after=int(account.funding),
                        exchange_balance_before=exchange_before_refund,
                        exchange_balance_after=int(account.exchange_balance),
                        notes=f"Auto Re-Funding after dues generation (Settlement ID: {settlement.id}). Amount: {masked_capital} (Masked Capital)",
                    )
                else:
                    # PROFIT: settlement reduces exchange balance by masked capital (PnL -> 0)
                    if exchange_before - masked_capital < 0:
                        errors.append(f"{account.client.name} / {account.exchange.name}: exchange balance would go negative")
                        continue

                    funding_after_settlement = funding_before
                    exchange_after_settlement = exchange_before - masked_capital

                    account.funding = funding_after_settlement
                    account.exchange_balance = exchange_after_settlement
                    account.save(update_fields=["funding", "exchange_balance"])

                    Transaction.objects.create(
                        client_exchange=account,
                        date=now,
                        type="RECORD_PAYMENT",
                        amount=-share_total,  # -ve: I owe client (profit case)
                        funding_before=funding_before,
                        funding_after=funding_after_settlement,
                        exchange_balance_before=exchange_before,
                        exchange_balance_after=exchange_after_settlement,
                        notes=f"Dues generated (not paid). Masked Capital: {masked_capital}. Linked Settlement ID: {settlement.id}",
                    )

                # Close cycle (so it disappears from /clients/settlements/)
                account.close_cycle()

                # Convention:
                #   +pending_balance => client owes me
                #   -pending_balance => I owe client
                settled_count += 1
                touched_client_ids.add(account.client_id)
        except ClientExchangeAccount.DoesNotExist:
            pass
        except ValidationError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"Account {account_id}: {str(e)}")

    if errors:
        for err in errors[:5]:  # Show first 5 errors
            messages.error(request, err)
        if len(errors) > 5:
            messages.error(request, f"... and {len(errors) - 5} more errors.")
    if settled_count > 0:
        messages.success(request, f"Pending dues generated in Client Payments for {settled_count} account(s).")
    elif not errors:
        messages.info(request, "No dues to generate.")

    # Recalculate pending for impacted clients to keep balances consistent.
    try:
        with transaction.atomic():
            for cid in touched_client_ids:
                _recalculate_pending_for_client(cid)
    except Exception:
        pass

    return redirect(reverse("pending_summary"))


@login_required
def export_pending_csv(request):
    """
    Export pending payments report as CSV.
    Export format mirrors Settlements UI table exactly.
    """
    import csv
    
    # Get search query if any
    search_query = request.GET.get("search", "").strip()
    section = request.GET.get("section", "all")  # "clients-owe", "you-owe", or "all"
    
    # Get all client exchanges for the user
    client_exchanges = ClientExchangeAccount.objects.filter(
        client__user=request.user
    ).select_related("client", "exchange")
    
    # Apply search filter if provided
    if search_query:
        client_exchanges = client_exchanges.filter(
            Q(client__name__icontains=search_query) |
            Q(client__code__icontains=search_query) |
            Q(exchange__name__icontains=search_query) |
            Q(exchange__code__icontains=search_query)
        )
    
    # Use EXACT same data building logic as pending_summary (personal share by default).
    from decimal import Decimal, ROUND_FLOOR

    def _share_from_pct(abs_pnl: int, pct: Decimal) -> int:
        if abs_pnl <= 0:
            return 0
        if pct is None:
            return 0
        pct = Decimal(str(pct))
        if pct <= 0:
            return 0
        exact = Decimal(abs_pnl) * (pct / Decimal("100"))
        return int(exact.to_integral_value(rounding=ROUND_FLOOR))

    clients_owe_list = []
    you_owe_list = []

    for client_exchange in client_exchanges:
        client_pnl = int(client_exchange.compute_client_pnl() or 0)
        abs_pnl = abs(int(client_pnl))

        is_loss_case = client_pnl < 0
        is_profit_case = client_pnl > 0
        is_neutral_case = client_pnl == 0

        own_pct = Decimal(str(client_exchange.my_own_percentage or 0))
        total_pct = Decimal(str(client_exchange.my_percentage or 0))
        pct_used = own_pct if own_pct > 0 else total_pct

        share_used = _share_from_pct(abs_pnl, pct_used)
        show_na = is_neutral_case or share_used == 0

        item = {
            "client": client_exchange.client,
            "exchange": client_exchange.exchange,
            "account": client_exchange,
            "client_pnl": client_pnl,
            "amount_owed": abs_pnl if not is_neutral_case else 0,
            "my_share_amount": share_used,
            "remaining_amount": share_used if not show_na else 0,
            "share_percentage": pct_used,
            "show_na": show_na,
        }

        if is_loss_case or is_neutral_case:
            clients_owe_list.append(item)
        elif is_profit_case:
            you_owe_list.append(item)
            # CRITICAL FIX: Lock share and use locked share for remaining calculation
            client_exchange.lock_initial_share_if_needed()
            settlement_info = client_exchange.get_remaining_settlement_amount()
            initial_final_share = settlement_info['initial_final_share']
            remaining_amount = settlement_info['remaining']
            overpaid_amount = settlement_info['overpaid']
            
            # Use initial locked share for display
            final_share = initial_final_share if initial_final_share > 0 else client_exchange.compute_my_share()
            
            # MASKED SHARE SETTLEMENT SYSTEM: Client MUST always appear in pending list
            # If FinalShare = 0, show N.A instead of filtering out
            show_na = (final_share == 0)
            
            unpaid_profit = client_pnl  # Client_PnL is positive (profit)
            
            # Use helper method to get appropriate share percentage
            share_pct = client_exchange.get_share_percentage(client_pnl)
            
            # Add to list (ALWAYS, even if FinalShare = 0)
            # CRITICAL FIX (FAIL CASE 2): Remaining display sign based on PnL direction
            display_remaining = calculate_display_remaining(client_pnl, remaining_amount)
            # Store absolute value for display (always positive)
            remaining_display = abs(display_remaining) if display_remaining else 0
            
            # FINANCIAL INTERPRETATION: Client PnL > 0 (PROFIT) → You owe client → DisplayRemaining is NEGATIVE
            you_owe_list.append({
                "client": client_exchange.client,
                "exchange": client_exchange.exchange,
                "account": client_exchange,
                "client_pnl": client_pnl,
                "amount_owed": unpaid_profit,
                "my_share_amount": final_share,
                "remaining_amount": remaining_display,  # Absolute value for display (always positive)
                "share_percentage": share_pct,
                "show_na": show_na,  # Flag for N.A display
            })
            continue
    
    # Sort lists by amount (descending)
    # Sort by Final Share or amount_owed, handling N.A cases
    def get_csv_sort_key(item):
        if item.get("show_na", False):
            return 0  # N.A items sort to bottom
        if "my_share_amount" in item:
            return abs(item["my_share_amount"])
        elif "amount_owed" in item:
            return abs(item["amount_owed"])
        elif "client_pnl" in item:
            return abs(item["client_pnl"])
        else:
            return 0
    
    clients_owe_list.sort(key=get_csv_sort_key, reverse=True)
    you_owe_list.sort(key=get_csv_sort_key, reverse=True)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    filename = f"settlements_{date.today().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    # Write header row - Matching table column order: Period, Master, U_CODE, OPENING POINTS, AVL.POINTS(CLOSING POINTS), PROFIT(+)/LOSS(-), MY SHARE, MY%
    headers = [
        'Period',
        'Master',
        'U_CODE',
        'OPENING POINTS',
        'AVL.POINTS(CLOSING POINTS)',
        'PROFIT(+)/LOSS(-)',
        'MY SHARE',
        'MY%'
    ]
    writer.writerow(headers)
    
    today_str = date.today().strftime('%Y-%m-%d')
    
    # Write Clients Owe You section (if requested)
    if section in ["all", "clients-owe"]:
        # Sort by client name to group them for Period/U_CODE logic
        clients_owe_list.sort(key=lambda x: (x["client"].name.lower(), -abs(x["client_pnl"])))
        
        for item in clients_owe_list:
            row_data = [
                today_str,  # Always show Period
                f'{item["exchange"].name}{f" ({item["exchange"].code})" if item["exchange"].code else ""}',
                item["client"].name if item["client"].name == "VENU" else (item["client"].code or '-'),  # Always show U_CODE
                int(item["account"].funding),
                int(item["account"].exchange_balance),
                'N.A' if item.get("show_na", False) else int(item["client_pnl"]),
                'N.A' if item.get("show_na", False) else int(item.get("remaining_amount", 0)),
                item.get("share_percentage", item["account"].my_percentage)
            ]
            writer.writerow(row_data)
    
    # Write You Owe Clients section (if requested)
    if section in ["all", "you-owe"]:
        # Sort by client name to group them for Period/U_CODE logic
        you_owe_list.sort(key=lambda x: (x["client"].name.lower(), -abs(x["client_pnl"])))
        
        for item in you_owe_list:
            row_data = [
                today_str,  # Always show Period
                f'{item["exchange"].name}{f" ({item["exchange"].code})" if item["exchange"].code else ""}',
                item["client"].name if item["client"].name == "VENU" else (item["client"].code or '-'),  # Always show U_CODE
                int(item["account"].funding),
                int(item["account"].exchange_balance),
                'N.A' if item.get("show_na", False) else int(item["client_pnl"]),
                'N.A' if item.get("show_na", False) else int(item.get("remaining_amount", 0)),
                item.get("share_percentage", item["account"].my_percentage)
            ]
            writer.writerow(row_data)
    
    return response


@login_required
def export_client_pending_csv(request, client_id):
    """
    Export pending payments report for a specific client as CSV.
    """
    import csv

    # WhatsApp number for all clients (requested by user)
    whatsapp_number = "9182351381"

    # Get the specific client
    client = get_object_or_404(Client, pk=client_id, user=request.user)

    # Get all client exchanges for this specific client
    client_exchanges = ClientExchangeAccount.objects.filter(
        client=client,
        client__user=request.user
    ).select_related("client", "exchange")

    # Use the same "personal share" logic as /clients/settlements/:
    # If my_own_percentage is set (>0), use it; otherwise fall back to my_percentage.
    from decimal import Decimal, ROUND_FLOOR

    def _share_from_pct(abs_pnl: int, pct: Decimal) -> int:
        if abs_pnl <= 0:
            return 0
        if pct is None:
            return 0
        pct = Decimal(str(pct))
        if pct <= 0:
            return 0
        exact = Decimal(abs_pnl) * (pct / Decimal("100"))
        return int(exact.to_integral_value(rounding=ROUND_FLOOR))

    clients_owe_list = []
    you_owe_list = []

    for client_exchange in client_exchanges:
        client_pnl = int(client_exchange.compute_client_pnl() or 0)
        abs_pnl = abs(int(client_pnl))

        is_loss_case = client_pnl < 0
        is_profit_case = client_pnl > 0
        is_neutral_case = client_pnl == 0

        own_pct = Decimal(str(client_exchange.my_own_percentage or 0))
        total_pct = Decimal(str(client_exchange.my_percentage or 0))
        pct_used = own_pct if own_pct > 0 else total_pct
        share_used = _share_from_pct(abs_pnl, pct_used)

        show_na = is_neutral_case or share_used == 0
        item = {
            "client": client_exchange.client,
            "exchange": client_exchange.exchange,
            "account": client_exchange,
            "client_pnl": client_pnl,
            "amount_owed": abs_pnl if not is_neutral_case else 0,
            "my_share_amount": share_used,
            "remaining_amount": share_used if not show_na else 0,
            "share_percentage": pct_used,
            "show_na": show_na,
        }

        if is_loss_case or is_neutral_case:
            clients_owe_list.append(item)
        elif is_profit_case:
            you_owe_list.append(item)

    # Sort lists by amount (descending)
    # Sort by Final Share or amount_owed, handling N.A cases
    def get_sort_key(item):
        if item.get("show_na", False):
            return 0  # N.A items sort to bottom
        if "my_share_amount" in item:
            return abs(item["my_share_amount"])
        elif "amount_owed" in item:
            return abs(item["amount_owed"])
        elif "client_pnl" in item:
            return abs(item["client_pnl"])
        else:
            return 0

    clients_owe_list.sort(key=get_sort_key, reverse=True)
    you_owe_list.sort(key=get_sort_key, reverse=True)

    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{client.name}_settlements.csv"'

    writer = csv.writer(response)

    # Write header for "Clients Owe You" section
    if clients_owe_list:
        writer.writerow(['=== CLIENTS OWE YOU ==='])
        writer.writerow([])
        writer.writerow(['Period', 'Master', 'U_CODE', 'OPENING POINTS', 'AVL.POINTS(CLOSING POINTS)', 'PROFIT(+)/LOSS(-)', 'MY SHARE', 'MY%', 'Status'])

        today_str = timezone.now().strftime('%Y-%m-%d')
        for item in clients_owe_list:
            row_data = [
                today_str,  # Always show Period
                f'{item["exchange"].name}{f" ({item["exchange"].code})" if item["exchange"].code else ""}',
                item["client"].name if item["client"].name == "VENU" else (item["client"].code or '-'),  # Always show U_CODE
                f'{item["account"].funding:.2f}',
                f'{item["account"].exchange_balance:.2f}',
                'N.A' if item.get("show_na", False) else f'{item["client_pnl"]:.2f}',
                'N.A' if item.get("show_na", False) else f'{item["remaining_amount"]:.2f}',
                f'{item.get("share_percentage", item["account"].my_percentage)}%',
                'Pending' if not item.get("show_na", False) else 'Settled'
            ]
            writer.writerow(row_data)
        writer.writerow([])

    # Write header for "You Owe Clients" section
    if you_owe_list:
        writer.writerow(['=== YOU OWE CLIENTS ==='])
        writer.writerow([])
        writer.writerow(['Period', 'Master', 'U_CODE', 'OPENING POINTS', 'AVL.POINTS(CLOSING POINTS)', 'PROFIT(+)/LOSS(-)', 'MY SHARE', 'MY%', 'Status'])

        today_str = timezone.now().strftime('%Y-%m-%d')
        for item in you_owe_list:
            row_data = [
                today_str,  # Always show Period
                f'{item["exchange"].name}{f" ({item["exchange"].code})" if item["exchange"].code else ""}',
                item["client"].name if item["client"].name == "VENU" else (item["client"].code or '-'),  # Always show U_CODE
                f'{item["account"].funding:.2f}',
                f'{item["account"].exchange_balance:.2f}',
                'N.A' if item.get("show_na", False) else f'{item["client_pnl"]:.2f}',
                'N.A' if item.get("show_na", False) else f'{item["remaining_amount"]:.2f}',
                f'{item.get("share_percentage", item["account"].my_percentage)}%',
                'Pending' if not item.get("show_na", False) else 'Settled'
            ]
            writer.writerow(row_data)
        writer.writerow([])

    return response


@login_required


def report_overview(request):


    """High-level reporting screen with simple totals and graphs."""
    from datetime import timedelta
    from collections import defaultdict
    from decimal import Decimal
    from django.db.models import Sum, Count

    today = date.today()
    is_payments_reports = bool(
        getattr(request, "resolver_match", None)
        and request.resolver_match.url_name == "payments_report_overview"
    )
    profit_basis = "cashflow"
    report_type = request.GET.get("report_type", "monthly")  # Default to monthly
    # Get client_type from GET (to update session) or from session
    client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type_filter == '':

        pass
    client_id = request.GET.get("client")  # Specific client ID
    exchange_id = request.GET.get("exchange")  # Specific exchange ID
    
    # Month selection parameter
    month_str = request.GET.get("month", today.strftime("%Y-%m"))
    try:
        year, month = map(int, month_str.split("-"))
        selected_month_start = date(year, month, 1)
        if month == 12:
            selected_month_end = date(year, 12, 31)
        else:
            selected_month_end = date(year, month + 1, 1) - timedelta(days=1)
    except (ValueError, IndexError):
        selected_month_start = date(today.year, today.month, 1)
        if today.month == 12:
            selected_month_end = date(today.year, 12, 31)
        else:
            selected_month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)



    
    # Time travel parameters (override month selection if provided)
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    as_of_str = request.GET.get("date")
    time_travel_mode = False
    date_filter = {}
    
    if start_date_str and end_date_str:

        start_date_filter = date.fromisoformat(start_date_str)
        end_date_filter = date.fromisoformat(end_date_str)
        date_filter = {"date__gte": start_date_filter, "date__lte": end_date_filter}
    elif as_of_str:
        time_travel_mode = True

        as_of_filter = date.fromisoformat(as_of_str)
        date_filter = {"date__lte": as_of_filter}
    elif not time_travel_mode:
        # Apply month filter if no time travel parameters
        date_filter = {"date__gte": selected_month_start, "date__lte": selected_month_end}
    
    # Base queryset with time travel filter if applicable, always filtered by user
    user_filter = {"client_exchange__client__user": request.user}
    
    # All clients are now "my clients" - no filtering needed
    
    # Add specific client filter if specified
    if client_id:
        user_filter["client_exchange__client_id"] = client_id
    
    # Add specific exchange filter if specified
    if exchange_id:
        user_filter["client_exchange__exchange_id"] = exchange_id

    # Initialize base queryset with user filter
    base_qs = Transaction.objects.filter(**user_filter)
    
    # Apply date filter if provided
    if date_filter:
        base_qs = base_qs.filter(**date_filter)

    
    # Filter to only show transactions after payments are recorded (settled)
    # Get all client_exchanges that have at least one settlement
    settled_client_exchanges = Transaction.objects.filter(
        **user_filter,
        type='RECORD_PAYMENT'
    ).values_list('client_exchange_id', flat=True).distinct()
    
    # For each settled client_exchange, get the latest settlement date
    # Only include profit/loss transactions up to that settlement date
    settled_data = {}
    for client_exchange_id in settled_client_exchanges:
        latest_settlement = Transaction.objects.filter(
            client_exchange_id=client_exchange_id,
            type='RECORD_PAYMENT'
        ).order_by('-date', '-created_at').first()
        if latest_settlement:


    
            pass
    # Filter base_qs to only include:
    # 1. RECORD_PAYMENT and FUNDING transactions (always include)
    # 2. PROFIT/LOSS transactions only if they're for settled client_exchanges and before/on settlement date
    from django.db.models import Q, F
    # Include TRADE transactions for turnover calculation (needed for turnover metrics)
    settled_filter = Q(type__in=['RECORD_PAYMENT', 'FUNDING', 'TRADE'])
    
    # Add profit/loss transactions that are settled
    # Note: This section is for old transaction types that don't exist in PIN-TO-PIN
    # Transactions are now just audit records, not used for profit/loss calculation
    for client_exchange_id, settlement_date in settled_data.items():
        # This logic is deprecated - transactions don't have TYPE_PROFIT or TYPE_LOSS
        pass
    
    # Apply the filter
    base_qs = base_qs.filter(settled_filter)
    
    # Get clients for dropdown (filtered by client_type if applicable)
    # All clients are now my clients - no filter needed
    clients_qs = Client.objects.filter(user=request.user)
    all_clients = clients_qs.order_by("name")
    
    # Get exchanges for dropdown
    from core.models import Exchange
    all_exchanges = Exchange.objects.all().order_by("name")
    
    # Get selected client if specified
    selected_client = None
    if client_id:
        try:
            selected_client = Client.objects.get(pk=client_id, user=request.user)
        except Client.DoesNotExist:
            pass

    # -------------------------------------------------------------------------
    # Client-payments → Reports (cash ledger)
    # What user wants here is simple net cash: Received - Paid.
    # This is driven by PendingPaymentTransaction (not trading PnL snapshot).
    # -------------------------------------------------------------------------
    if is_payments_reports:
        from .models import PendingPaymentTransaction
        from django.utils import timezone
        from datetime import datetime, timedelta

        profit_basis = "cashflow_ledger"

        ledger_qs = (
            PendingPaymentTransaction.objects.filter(client__user=request.user)
            .select_related("client", "client_exchange", "client_exchange__exchange")
            .order_by("-date", "-id")
        )

        if client_id:
            ledger_qs = ledger_qs.filter(client_id=client_id)
        if exchange_id:
            # Exchange filter is only reliable for new linked transactions
            ledger_qs = ledger_qs.filter(client_exchange__exchange_id=exchange_id)

        # Apply date filter (convert date -> aware datetime bounds)
        if date_filter:
            filter_dict = {}
            if "date__gte" in date_filter:
                d = date_filter["date__gte"]
                if isinstance(d, date):
                    filter_dict["date__gte"] = timezone.make_aware(datetime.combine(d, datetime.min.time()))
                else:
                    filter_dict["date__gte"] = d
            if "date__lte" in date_filter:
                d = date_filter["date__lte"]
                if isinstance(d, date):
                    filter_dict["date__lte"] = timezone.make_aware(datetime.combine(d, datetime.max.time()))
                else:
                    filter_dict["date__lte"] = d
            if filter_dict:
                ledger_qs = ledger_qs.filter(**filter_dict)

        total_received = ledger_qs.filter(type="RECEIVED").aggregate(total=Sum("amount"))["total"] or 0
        total_paid = ledger_qs.filter(type="GIVEN").aggregate(total=Sum("amount"))["total"] or 0
        net_profit = int(total_received) - int(total_paid)

        # For this section, "turnover" means cash moved
        total_turnover = int(total_received) + int(total_paid)

        # Pending totals (should match Pending Payments page)
        pending_clients = Client.objects.filter(user=request.user)
        if client_id:
            pending_clients = pending_clients.filter(pk=client_id)
        pending_receivable = sum(c.pending_balance for c in pending_clients if c.pending_balance > 0)
        pending_payable = abs(sum(c.pending_balance for c in pending_clients if c.pending_balance < 0))
        net_pending = int(pending_receivable) - int(pending_payable)

        # Chart range (max 30 days)
        chart_start = today - timedelta(days=30)
        chart_end = today
        if "date__gte" in date_filter and isinstance(date_filter.get("date__gte"), date):
            chart_start = date_filter["date__gte"]
        if "date__lte" in date_filter and isinstance(date_filter.get("date__lte"), date):
            chart_end = date_filter["date__lte"]
        if (chart_end - chart_start).days > 30:
            chart_start = chart_end - timedelta(days=30)

        daily_bucket = defaultdict(lambda: {"received": 0, "paid": 0})
        for tx in ledger_qs.filter(date__date__gte=chart_start, date__date__lte=chart_end):
            d = tx.date.date()
            if tx.type == "RECEIVED":
                daily_bucket[d]["received"] += int(tx.amount)
            else:
                daily_bucket[d]["paid"] += int(tx.amount)

        date_labels = []
        profit_data = []
        loss_data = []
        turnover_data = []
        cur = chart_start
        days_count = 0
        while cur <= chart_end and days_count < 30:
            r = daily_bucket[cur]["received"]
            p = daily_bucket[cur]["paid"]
            net = r - p
            date_labels.append(cur.strftime("%Y-%m-%d"))
            profit_data.append(float(net) if net > 0 else 0.0)
            loss_data.append(float(abs(net)) if net < 0 else 0.0)
            turnover_data.append(float(r + p))
            cur += timedelta(days=1)
            days_count += 1

        type_labels = ["Received", "Paid"]
        type_counts = [
            ledger_qs.filter(type="RECEIVED").aggregate(c=Count("id"))["c"] or 0,
            ledger_qs.filter(type="GIVEN").aggregate(c=Count("id"))["c"] or 0,
        ]
        type_amounts = [float(total_received or 0), float(total_paid or 0)]
        type_colors = ["#10b981", "#ef4444"]

        # Top clients by net profit (same 30d chart window)
        per_client = defaultdict(int)
        for tx in ledger_qs.filter(date__date__gte=chart_start, date__date__lte=chart_end).select_related("client"):
            per_client[tx.client_id] += int(tx.amount) if tx.type == "RECEIVED" else -int(tx.amount)

        top = sorted(per_client.items(), key=lambda kv: kv[1], reverse=True)[:10]
        client_map = {c.id: c for c in all_clients}
        client_labels = []
        client_profits = []
        for cid, net in top:
            c = client_map.get(cid)
            if not c:
                continue
            client_labels.append(c.name)
            client_profits.append(float(net))

        context = {
            "report_type": report_type,
            "client_type_filter": client_type_filter,
            "all_clients": all_clients,
            "all_exchanges": all_exchanges,
            "selected_client": selected_client,
            "selected_client_id": int(client_id) if client_id else None,
            "selected_exchange_id": int(exchange_id) if exchange_id else None,
            "today": today,
            "profit_basis": profit_basis,
            "net_pending": net_pending,
            "pending_receivable": int(pending_receivable),
            "pending_payable": int(pending_payable),
            "total_turnover": int(total_turnover),
            "your_total_profit": int(net_profit),
            "your_total_income_from_clients": int(total_received),
            "your_total_paid_to_clients": int(total_paid),
            "my_profit": 0,
            "friend_profit": 0,
            "company_profit": 0,
            "daily_labels": json.dumps(date_labels),
            "daily_profit": json.dumps(profit_data),
            "daily_loss": json.dumps(loss_data),
            "daily_turnover": json.dumps(turnover_data),
            "weekly_labels": json.dumps([]),
            "weekly_profit": json.dumps([]),
            "weekly_loss": json.dumps([]),
            "weekly_turnover": json.dumps([]),
            "type_labels": json.dumps(type_labels),
            "type_counts": json.dumps(type_counts),
            "type_amounts": json.dumps(type_amounts),
            "type_colors": json.dumps(type_colors),
            "monthly_labels": json.dumps([]),
            "monthly_profit": json.dumps([]),
            "monthly_loss": json.dumps([]),
            "monthly_turnover": json.dumps([]),
            "client_labels": json.dumps(client_labels),
            "client_profits": json.dumps(client_profits),
            "time_travel_mode": time_travel_mode,
            "start_date_str": start_date_str,
            "end_date_str": end_date_str,
            "as_of_str": as_of_str,
            "time_travel_transactions": [],
            "selected_month": month_str,
            "selected_month_start": selected_month_start,
            "selected_month_end": selected_month_end,
        }
        return render(request, "core/reports/overview.html", context)


    # Overall totals (filtered by time travel if applicable)
    # CORRECTNESS LOGIC: Turnover = Σ(|ExchangeBalanceAfter − ExchangeBalanceBefore|) for TRADE transactions only
    # Turnover measures trading activity, NOT funding or settlements
    trade_qs = base_qs.filter(type='TRADE').exclude(
        exchange_balance_before__isnull=True
    ).exclude(
        exchange_balance_after__isnull=True
    )
    # Calculate turnover as sum of absolute exchange balance movements from trades
    total_turnover = sum(
        abs(tx.exchange_balance_after - tx.exchange_balance_before)
        for tx in trade_qs
    ) or 0
    
    # 📘 YOUR TOTAL PROFIT Calculation (CORRECTNESS LOGIC)
    # 
    # ═══════════════════════════════════════════════════════════════════════════
    # 1️⃣ CORE RULE (DO NOT BREAK THIS)
    # ═══════════════════════════════════════════════════════════════════════════
    # Record Payment = Profit or Loss Event
    #
    # Who pays          Meaning                      Effect on YOU
    # ──────────────────────────────────────────────────────────────────────────
    # Client → You      Client loss settlement       ✅ Your PROFIT  (+X)
    # You → Client      Client profit settlement     ❌ Your LOSS    (-X)
    #
    # SIGN CONVENTION (SINGLE SOURCE OF TRUTH):
    #   +X = Client paid YOU (Client loss)  → Your PROFIT
    #   -X = YOU paid client (Client profit) → Your LOSS
    #
    # ═══════════════════════════════════════════════════════════════════════════
    # 2️⃣ SHARE SPLIT LOGIC (YOUR + COMPANY)
    # ═══════════════════════════════════════════════════════════════════════════
    # Split Your Total Profit using weighted average percentages from all transactions
    #
    # Formula:
    #   1. Calculate weighted average ratios from all payment transactions
    #   2. My Profit = Your Total Profit × (weighted My Own % ratio)
    #   3. Friend Profit = Your Total Profit × (weighted Friend % ratio)
    #
    # Example: Your Total Profit = -81
    #   If weighted ratios are: My Own = 0.1 (10%), Friend = 0.9 (90%)
    #   My Profit = -81 × 0.1 = -8.1 ≈ -8
    #   Friend Profit = -81 × 0.9 = -72.9 ≈ -73
    #   Verification: -8 + (-73) = -81 ✓
    # ═══════════════════════════════════════════════════════════════════════════
    #
    # SINGLE SOURCE OF TRUTH: RECORD_PAYMENT transactions only
    # Split is calculated from Your Total Profit, ensuring exact match
    from django.utils import timezone
    from datetime import datetime
    
    # Get all RECORD_PAYMENT transactions for user
    # Also include SETTLEMENT_SHARE for backward compatibility (old transactions)
    payment_qs = Transaction.objects.filter(
        client_exchange__client__user=request.user,
        type__in=['RECORD_PAYMENT', 'SETTLEMENT_SHARE']
    )
    
    # Apply client filter (if specified)
    if client_id:
        payment_qs = payment_qs.filter(client_exchange__client_id=client_id)
    
    # Apply exchange filter (if specified)
    if exchange_id:
        payment_qs = payment_qs.filter(client_exchange__exchange_id=exchange_id)
    
    # Apply date filter (if specified) - convert date to datetime for comparison
    if date_filter:
        filter_dict = {}
        if 'date__gte' in date_filter:
            date_gte = date_filter['date__gte']
            if isinstance(date_gte, date):
                filter_dict['date__gte'] = timezone.make_aware(
                    datetime.combine(date_gte, datetime.min.time())
                )
            else:
                filter_dict['date__gte'] = date_gte
        if 'date__lte' in date_filter:
            date_lte = date_filter['date__lte']
            if isinstance(date_lte, date):
                filter_dict['date__lte'] = timezone.make_aware(
                    datetime.combine(date_lte, datetime.max.time())
                )
            else:
                filter_dict['date__lte'] = date_lte
        if filter_dict:
            payment_qs = payment_qs.filter(**filter_dict)
    
    # Calculate total profit (simple sum - sign is absolute truth)
    your_total_profit = payment_qs.aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Calculate breakdown for display
    your_total_income_from_clients = payment_qs.filter(amount__gt=0).aggregate(
        total=Sum("amount")
    )["total"] or Decimal(0)
    
    your_total_paid_to_clients = abs(
        payment_qs.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    )
    
    # 📘 MY PROFIT AND COMPANY PROFIT Calculation (CORRECTNESS LOGIC)
    # Calculate from Your Total Profit using weighted average percentages
    # Formula: My Profit = Your Total Profit × (weighted My Own % / weighted My Total %)
    #          Friend Profit = Your Total Profit × (weighted Friend % / weighted My Total %)
    
    my_profit_total = Decimal(0)
    friend_profit_total = Decimal(0)
    
    # Calculate weighted average percentages based on payment amounts
    total_weighted_my_own = Decimal(0)
    total_weighted_friend = Decimal(0)
    total_weighted_amount = Decimal(0)
    
    # Use the same payment_qs queryset from Your Total Profit calculation
    payment_transactions = payment_qs.select_related("client_exchange")
    
    tx_count = 0
    skipped_no_config = 0
    skipped_zero_pct = 0
    
    for tx in payment_transactions:
        tx_count += 1
        payment_amount = Decimal(str(tx.amount))  # Can be positive or negative
        account = tx.client_exchange
        my_total_pct = Decimal(str(account.my_percentage))
        
        if my_total_pct == 0:
            skipped_zero_pct += 1
            continue
        
        my_own_pct = Decimal(str(getattr(account, "my_own_percentage", 0) or 0))
        friend_pct = Decimal(str(getattr(account, "company_percentage", 0) or 0))

        # Weight by absolute payment amount
        weight = abs(payment_amount)
        weighted_my_own_contrib = weight * (my_own_pct / my_total_pct)
        weighted_friend_contrib = weight * (friend_pct / my_total_pct)
        total_weighted_my_own += weighted_my_own_contrib
        total_weighted_friend += weighted_friend_contrib
        total_weighted_amount += weight
    
    # Split Your Total Profit using weighted average percentages
    if total_weighted_amount > 0:
        # Calculate weighted average ratios
        weighted_my_own_ratio = total_weighted_my_own / total_weighted_amount
        weighted_friend_ratio = total_weighted_friend / total_weighted_amount
        
        # Split total profit proportionally (works for both positive and negative)
        my_profit_total = your_total_profit * weighted_my_own_ratio
        friend_profit_total = your_total_profit * weighted_friend_ratio
    elif your_total_profit == 0:
        # No profit/loss, so no split needed
        my_profit_total = Decimal(0)
        friend_profit_total = Decimal(0)
    else:
        # No report configs found, all goes to me
        my_profit_total = your_total_profit
        friend_profit_total = Decimal(0)
    
    # Verify: My Profit + Friend Profit should equal Your Total Profit (within rounding)
    # This ensures the split is correct
    
    # Remove company_profit (obsolete)
    company_profit = Decimal(0)

    # -------------------------------------------------------------------------
    # Client Payments → Reports should be "report" (PnL/share snapshot),
    # not only cash-flow from settlements.
    # This also avoids confusing users when they haven't settled yet.
    # -------------------------------------------------------------------------
    if is_payments_reports:
        profit_basis = "pnl"

        accounts_qs = ClientExchangeAccount.objects.filter(client__user=request.user).select_related(
            "client", "exchange"
        )
        if client_id:
            accounts_qs = accounts_qs.filter(client_id=client_id)
        if exchange_id:
            accounts_qs = accounts_qs.filter(exchange_id=exchange_id)

        your_total_profit = Decimal(0)
        your_total_income_from_clients = Decimal(0)
        your_total_paid_to_clients = Decimal(0)
        my_profit_total = Decimal(0)
        friend_profit_total = Decimal(0)

        for account in accounts_qs:
            pnl = account.compute_client_pnl()
            if pnl == 0:
                continue

            share_amount = Decimal(str(account.compute_my_share()))
            signed_share = share_amount if pnl < 0 else -share_amount  # + => client owes me, - => I owe client

            your_total_profit += signed_share
            if signed_share >= 0:
                your_total_income_from_clients += signed_share
            else:
                your_total_paid_to_clients += abs(signed_share)

            my_total_pct = Decimal(str(account.my_percentage or 0))
            if my_total_pct != 0:
                my_own_pct = Decimal(str(getattr(account, "my_own_percentage", 0) or 0))
                friend_pct = Decimal(str(getattr(account, "company_percentage", 0) or 0))
                my_profit_total += signed_share * (my_own_pct / my_total_pct)
                friend_profit_total += signed_share * (friend_pct / my_total_pct)
            else:
                my_profit_total += signed_share

    # Daily trends for last 30 days (or filtered by time travel)
    if time_travel_mode and start_date_str and end_date_str:

        end_date = date.fromisoformat(end_date_str)
        # Limit to 30 days or the actual range, whichever is smaller
        days_diff = (end_date - start_date).days
        if days_diff > 30:
            end_date = start_date + timedelta(days=30)
    else:
        start_date = today - timedelta(days=30)
        end_date = today
    
    daily_data = defaultdict(lambda: {"profit": 0, "loss": 0, "turnover": 0})
    
    # Daily turnover from TRADE transactions (exchange balance movement)
    daily_trades = base_qs.filter(
        type='TRADE',
        date__gte=start_date,
        date__lte=end_date
    ).exclude(
        exchange_balance_before__isnull=True
    ).exclude(
        exchange_balance_after__isnull=True
    )
    
    for tx in daily_trades:
        tx_date = tx.date
        turnover_amount = abs(tx.exchange_balance_after - tx.exchange_balance_before)
        daily_data[tx_date]["turnover"] += float(turnover_amount)
    
    # Daily profit/loss from RECORD_PAYMENT transactions (CORRECTNESS LOGIC)
    daily_payments = base_qs.filter(
        type='RECORD_PAYMENT',
        date__gte=start_date,
        date__lte=end_date
    ).values("date").annotate(
        profit_sum=Sum("amount")
    )
    
    for item in daily_payments:
        tx_date = item['date']
        profit_amount = float(item["profit_sum"] or 0)
        if profit_amount > 0:
            daily_data[tx_date]["profit"] += profit_amount
        elif profit_amount < 0:
            daily_data[tx_date]["loss"] += abs(profit_amount)
    
    # Create sorted date list and data arrays
    # Only include dates up to end_date
    date_labels = []
    profit_data = []
    loss_data = []
    turnover_data = []
    
    current_date = start_date
    days_count = 0
    while current_date <= end_date and days_count < 30:

        # Access defaultdict directly - it will return default dict if key doesn't exist
        day_data = daily_data[current_date]
        profit_data.append(float(day_data.get("profit", 0)))
        loss_data.append(float(day_data.get("loss", 0)))
        turnover_data.append(float(day_data.get("turnover", 0)))
        current_date += timedelta(days=1)
        days_count += 1
    
    # Transaction type breakdown (filtered by time travel if applicable)
    type_breakdown = base_qs.values("type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_counts = []
    type_amounts = []
    type_colors = []
    
    # Map transaction type strings to display labels
    type_map = {
        'FUNDING': ("Funding", "#4b5563"),
        'TRADE': ("Trade", "#6b7280"),
        'FEE': ("Fee", "#9ca3af"),
        'ADJUSTMENT': ("Adjustment", "#6b7280"),
        'RECORD_PAYMENT': ("Record Payment", "#10b981"),
    }
    
    for item in type_breakdown:
        tx_type = item["type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_counts.append(item["count"])
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)

    
    # Monthly trends (last 6 months)
    monthly_labels = []
    monthly_profit = []
    monthly_loss = []
    monthly_turnover = []
    
    for i in range(6):
        month_date = today.replace(day=1)
        for _ in range(i):
                

                month_date = month_date.replace(year=month_date.year - 1, month=12)

                month_date = month_date.replace(month=month_date.month - 1)

        
        # Calculate month end date
        if month_date.month == 12:
            month_end = date(month_date.year, 12, 31)
        else:
            month_end = month_date.replace(month=month_date.month + 1) - timedelta(days=1)


        
        monthly_labels.insert(0, month_date.strftime("%b %Y"))
        
        # Get transactions for this month (filtered by time travel if applicable)
        month_transactions = base_qs.filter(
            date__gte=month_date,
            date__lte=month_end
        )
        
        # Monthly profit/loss from RECORD_PAYMENT transactions (CORRECTNESS LOGIC)
        month_payments = month_transactions.filter(type='RECORD_PAYMENT')
        month_profit_val = month_payments.filter(amount__gt=0).aggregate(
            total=Sum("amount")
        )["total"] or 0
        month_loss_val = abs(month_payments.filter(amount__lt=0).aggregate(
            total=Sum("amount")
        )["total"] or 0)
        
        # Turnover from TRADE transactions (exchange balance movement)
        month_trade_qs = month_transactions.filter(type='TRADE').exclude(
            exchange_balance_before__isnull=True
        ).exclude(
            exchange_balance_after__isnull=True
        )
        month_turnover_val = sum(
            abs(tx.exchange_balance_after - tx.exchange_balance_before)
            for tx in month_trade_qs
        ) or 0
        
        monthly_profit.insert(0, float(month_profit_val))
        monthly_loss.insert(0, float(month_loss_val))
        monthly_turnover.insert(0, float(month_turnover_val))
    
    # Top clients by profit (last 30 days or filtered)
    # NOTE: your_share_amount field doesn't exist in Transaction model
    # Return empty lists since we can't calculate profit from Transaction records
    top_clients = []
    client_labels = []
    client_profits = []

    # Weekly data (last 4 weeks)
    weekly_labels = []
    weekly_profit = []
    weekly_loss = []
    weekly_turnover = []
    
    # Initialize week_end to end_date (or today if end_date not set)
    week_end = end_date

    for i in range(4):
        week_start = week_end - timedelta(days=6)
        weekly_labels.insert(0, f"Week {4-i} ({week_start.strftime('%b %d')} - {week_end.strftime('%b %d')})")
        
        week_transactions = base_qs.filter(
            date__gte=week_start,
            date__lte=week_end
        )
        
        # Weekly profit/loss from RECORD_PAYMENT transactions, turnover from TRADE transactions (CORRECTNESS LOGIC)
        week_payments = week_transactions.filter(type='RECORD_PAYMENT')
        week_profit_val = week_payments.filter(amount__gt=0).aggregate(
            total=Sum("amount")
        )["total"] or 0
        week_loss_val = abs(week_payments.filter(amount__lt=0).aggregate(
            total=Sum("amount")
        )["total"] or 0)
        
        # Turnover from TRADE transactions (exchange balance movement)
        week_trade_qs = week_transactions.filter(type='TRADE').exclude(
            exchange_balance_before__isnull=True
        ).exclude(
            exchange_balance_after__isnull=True
        )
        week_turnover_val = sum(
            abs(tx.exchange_balance_after - tx.exchange_balance_before)
            for tx in week_trade_qs
        ) or 0
        
        weekly_profit.insert(0, float(week_profit_val))
        weekly_loss.insert(0, float(week_loss_val))
        weekly_turnover.insert(0, float(week_turnover_val))
        
        # Move week_end backwards for next iteration
        week_end = week_start - timedelta(days=1)

    # Time travel data
    time_travel_transactions = base_qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")[:50]
    
    # Convert Decimal/float values to integers for proper formatting
    # Ensure all values are integers to avoid float formatting issues
    try:
        total_turnover_int = int(round(float(total_turnover or 0)))
    except (ValueError, TypeError):
        total_turnover_int = 0
    
    try:
        your_total_profit_int = int(round(float(your_total_profit or 0)))
    except (ValueError, TypeError):
        your_total_profit_int = 0
    
    try:
        your_total_income_int = int(round(float(your_total_income_from_clients or 0)))
    except (ValueError, TypeError):
        your_total_income_int = 0
    
    try:
        your_total_paid_int = int(round(float(your_total_paid_to_clients or 0)))
    except (ValueError, TypeError):
        your_total_paid_int = 0
    
    # Pass Decimal values directly for my_profit and friend_profit to preserve decimals
    # The template will use currency_inr_decimal filter to format with 2 decimal places
    context = {
        "report_type": report_type,
        "client_type_filter": client_type_filter,
        "all_clients": all_clients,
        "all_exchanges": all_exchanges,
        "selected_client": selected_client,
        "selected_client_id": int(client_id) if client_id else None,
        "selected_exchange_id": int(exchange_id) if exchange_id else None,
        "today": today,
        "total_turnover": total_turnover_int,
        "your_total_profit": your_total_profit_int,
        "your_total_income_from_clients": your_total_income_int,
        "your_total_paid_to_clients": your_total_paid_int,
        "my_profit": my_profit_total,  # Pass Decimal directly to preserve decimals
        "friend_profit": friend_profit_total,  # Pass Decimal directly to preserve decimals
        "company_profit": company_profit,  # Kept for backward compatibility, always 0
        "profit_basis": profit_basis,
        "daily_labels": json.dumps(date_labels),
        "daily_profit": json.dumps(profit_data),
        "daily_loss": json.dumps(loss_data),
        "daily_turnover": json.dumps(turnover_data),
        "weekly_labels": json.dumps(weekly_labels),
        "weekly_profit": json.dumps(weekly_profit),
        "weekly_loss": json.dumps(weekly_loss),
        "weekly_turnover": json.dumps(weekly_turnover),
        "type_labels": json.dumps(type_labels),
        "type_counts": json.dumps(type_counts),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "monthly_labels": json.dumps(monthly_labels),
        "monthly_profit": json.dumps(monthly_profit),
        "monthly_loss": json.dumps(monthly_loss),
        "monthly_turnover": json.dumps(monthly_turnover),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
        "time_travel_mode": time_travel_mode,
        "start_date_str": start_date_str,
        "end_date_str": end_date_str,
        "as_of_str": as_of_str,
        "time_travel_transactions": time_travel_transactions,
        "selected_month": month_str,
        "selected_month_start": selected_month_start,
        "selected_month_end": selected_month_end,
    }
    return render(request, "core/reports/overview.html", context)


@login_required


def time_travel_report(request):


    """
    Time‑travel reporting: filter transactions and aggregates by date range or up to a selected date.
    For now this uses live aggregation over `Transaction`; it can later leverage
    `DailyBalanceSnapshot` for faster queries.
    """
    # Get date parameters
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    as_of_str = request.GET.get("date")  # Legacy single date parameter
    # Get client_type from GET (to update session) or from session
    client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type_filter == '':

    
        pass
    # Base filter
    base_filter = {"client_exchange__client__user": request.user}
    
    # All clients are now "my clients" - no filtering needed
    
    # Determine date range
    if start_date_str and end_date_str:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        as_of = end_date  # For display purposes
        qs = Transaction.objects.filter(**base_filter, date__gte=start_date, date__lte=end_date)
        date_range_mode = True
    elif as_of_str:
        # Legacy: single date (up to that date)
        as_of = date.fromisoformat(as_of_str)
        qs = Transaction.objects.filter(**base_filter, date__lte=as_of)
        date_range_mode = False
        start_date = None
        end_date = None
    else:

        # Default: today
        as_of = date.today()
        qs = Transaction.objects.filter(**base_filter, date__lte=as_of)
        date_range_mode = False
        start_date = None
        end_date = None

    # CORRECTNESS LOGIC: Turnover = Σ(|ExchangeBalanceAfter − ExchangeBalanceBefore|) for TRADE transactions only
    # Turnover measures trading activity, NOT funding or settlements
    trade_qs = qs.filter(type='TRADE').exclude(
        exchange_balance_before__isnull=True
    ).exclude(
        exchange_balance_after__isnull=True
    )
    # Calculate turnover as sum of absolute exchange balance movements from trades
    total_turnover = sum(
        abs(tx.exchange_balance_after - tx.exchange_balance_before)
        for tx in trade_qs
    ) or 0
    
    # Your Total Profit = Sum(RECORD_PAYMENT.amount) - signed sum
    your_profit = payment_qs.aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    company_profit = Decimal(0)

    # Calculate pending amounts correctly
    # Clients owe you = pending amounts for transactions up to as_of date
    client_exchange_filter = {"client__user": request.user}
    # All clients are now "my clients" - no filtering needed
    
    if date_range_mode:
        client_exchanges_in_range = ClientExchangeAccount.objects.filter(
            **client_exchange_filter,

            transactions__date__gte=start_date,

            transactions__date__lte=end_date

        ).distinct()
        pending_clients_owe = Decimal(0)  # No longer using pending amounts
    else:

        # For single date, calculate pending as of that date
        client_exchanges_up_to = ClientExchangeAccount.objects.filter(
            **client_exchange_filter,

            transactions__date__lte=as_of

        ).distinct()
        pending_clients_owe = Decimal(0)  # No longer using pending amounts
    
    # You owe clients = calculated from accounts (not from deprecated transaction fields)
    # This is now calculated in pending_summary view using account balances
    pending_you_owe_clients = Decimal(0)

    recent_transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")[:50]

    context = {
        "as_of": as_of,
        "start_date": start_date,
        "end_date": end_date,
        "start_date_str": start_date_str,
        "end_date_str": end_date_str,
        "date_range_mode": date_range_mode,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "pending_clients_owe": pending_clients_owe,
        "pending_you_owe_clients": pending_you_owe_clients,
        "recent_transactions": recent_transactions,
        "client_type_filter": client_type_filter,
    }
    return render(request, "core/reports/time_travel.html", context)


@login_required


def company_share_summary(request):


    # Company share summary removed - no longer needed
    from django.contrib import messages
    messages.info(request, "Company share summary is no longer available.")
    return redirect(reverse("client_list"))


# Exchange Management Views
@login_required


def exchange_create(request):
    """Create a new standalone exchange (A, B, C, D, etc.)."""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        version_name = request.POST.get("version_name", "").strip() or None
        code = request.POST.get("code", "").strip()
        
        if name:
            # Check for case-insensitive duplicate names
            existing = Exchange.objects.filter(name__iexact=name)
            if existing.exists():
                from django.contrib import messages
                messages.error(request, f"'{name}' already exists.")
                return render(request, "core/exchanges/create.html")
            
            try:
                Exchange.objects.create(
                    name=name,
                    version_name=version_name,
                    code=code if code else None,
                )
                from django.contrib import messages
                messages.success(request, f"Exchange '{name}' has been created successfully.")
                return redirect(reverse("exchange_list"))
            except Exception as e:
                # Handle any other validation errors (including model-level validation)
                from django.contrib import messages
                # Check if it's a duplicate name error
                existing = Exchange.objects.filter(name__iexact=name)
                if existing.exists():
                    messages.error(request, f"'{name}' already exists.")
                else:
                    messages.error(request, f"Error creating exchange: {str(e)}")
                return render(request, "core/exchanges/create.html")
        else:
            from django.contrib import messages
            messages.error(request, "Exchange name is required.")
    
    return render(request, "core/exchanges/create.html")


@login_required


def exchange_edit(request, pk):


    """Edit an existing standalone exchange."""
    exchange = get_object_or_404(Exchange, pk=pk)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        version_name = request.POST.get("version_name", "").strip() or None
        code = request.POST.get("code", "").strip() or None
        
        # If name is being changed, check for case-insensitive duplicate
        if name and name != exchange.name:
            existing = Exchange.objects.filter(name__iexact=name).exclude(pk=exchange.pk)
            if existing.exists():
                from django.contrib import messages
                messages.error(request, f"'{name}' already exists.")
                return render(request, "core/exchanges/edit.html", {"exchange": exchange})
            exchange.name = name
        
        try:
            exchange.version_name = version_name
            exchange.code = code
            exchange.save()
            from django.contrib import messages
            messages.success(request, f"Exchange '{exchange.name}' has been updated successfully.")
            return redirect(reverse("exchange_list"))
        except Exception as e:
            from django.contrib import messages
            # Check if it's a duplicate name error
            if name:
                existing = Exchange.objects.filter(name__iexact=name).exclude(pk=exchange.pk)
                if existing.exists():
                    messages.error(request, f"'{name}' already exists.")
                else:
                    messages.error(request, f"Error updating exchange: {str(e)}")
            else:
                messages.error(request, f"Error updating exchange: {str(e)}")
            return render(request, "core/exchanges/edit.html", {"exchange": exchange})
    
    return render(request, "core/exchanges/edit.html", {"exchange": exchange})


@login_required


def client_exchange_create(request, client_pk):


    """Link a client to an exchange with specific percentages."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    exchanges = Exchange.objects.all().order_by("name")
    
    if request.method == "POST":

        my_share = request.POST.get("my_share_pct")
        company_share = request.POST.get("company_share_pct")
        
        if exchange_id and my_share and company_share:


            my_share_decimal = Decimal(my_share)

            company_share_decimal = Decimal(company_share)

            
            # Validate company share is less than 100%
            if company_share_decimal >= 100:
                client_type = "company" if False else "my"

                return render(request, "core/exchanges/link_to_client.html", {

                    "client": client,

                    "exchanges": exchanges,

                    "client_type": client_type,

                    "error": "Company share must be less than 100%",

                })
            
            client_exchange = ClientExchangeAccount.objects.create(
                client=client,
                exchange=exchange,
                my_share_pct=my_share_decimal,
                company_share_pct=company_share_decimal,
            )
            
            # Redirect to appropriate namespace based on client type
            return redirect("client_detail", pk=client.pk)
    
    client_type = "company" if False else "my"
    return render(request, "core/exchanges/link_to_client.html", {
        "client": client,
        "exchanges": exchanges,
        "client_type": client_type,
    })


@login_required


@login_required


def my_client_exchange_create(request, client_pk):


    """Link an exchange to a client."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    exchanges = Exchange.objects.all().order_by("name")
    
    if request.method == "POST":
        my_share = request.POST.get("my_share_pct")
        
        if exchange_id and my_share:
            my_share_decimal = Decimal(my_share)
            
            client_exchange = ClientExchangeAccount.objects.create(
                client=client,
                exchange=exchange,
                my_share_pct=my_share_decimal,
            )
            
            return redirect(reverse("my_clients:detail", args=[client.pk]))

    
    return render(request, "core/exchanges/link_to_client.html", {
        "client": client,
        "exchanges": exchanges,
        "client_type": "my",
    })


@login_required


def client_exchange_edit(request, pk):


    """Edit client-exchange link percentages. Exchange can be edited at any time."""
    client_exchange = get_object_or_404(ClientExchangeAccount, pk=pk, client__user=request.user)
    
    # Exchange can always be edited
    can_edit_exchange = True
    
    if request.method == "POST":
        old_my_percentage = client_exchange.my_percentage
        # Get percentage values from form
        my_percentage = request.POST.get("my_percentage", "").strip()
        loss_share_percentage = request.POST.get("loss_share_percentage", "").strip()
        profit_share_percentage = request.POST.get("profit_share_percentage", "").strip()
        friend_percentage = request.POST.get("friend_percentage", "").strip()
        my_own_percentage = request.POST.get("my_own_percentage", "").strip()
        
        # Update exchange if exchange was provided
        new_exchange_id = request.POST.get("exchange")
        if new_exchange_id:
            new_exchange = get_object_or_404(Exchange, pk=new_exchange_id)

            # Allow multiple accounts for the same exchange (client can have duplicates).
            # Only update if the exchange actually changed.
            if new_exchange.pk != client_exchange.exchange_id:
                client_exchange.exchange = new_exchange

        # Update percentages (using Decimal for precision)
        from decimal import Decimal
        percentage_updated = False
        if my_percentage and my_percentage.strip():
            try:
                my_pct = Decimal(str(my_percentage))
                if 0 <= my_pct <= 100:
                    # Keep loss/profit share % in sync with My Total % (decimal supported).
                    
                    # Update my_percentage
                    client_exchange.my_percentage = my_pct
                    
                    # Keep loss/profit shares aligned to My Total %.
                    client_exchange.loss_share_percentage = my_pct
                    
                    # Always update profit_share_percentage
                    client_exchange.profit_share_percentage = my_pct
                    percentage_updated = True
            except (ValueError, TypeError) as e:
                from django.contrib import messages
                messages.error(request, f"Error updating percentages: {str(e)}")
                # Re-render form with error
                exchanges = Exchange.objects.all().order_by("name")
                client_type = "company" if False else "my"
                has_transactions = Transaction.objects.filter(client_exchange=client_exchange).exists()
                can_edit_loss_percentage = not has_transactions
                return render(request, "core/exchanges/edit_client_link.html", {
                    "client_exchange": client_exchange,
                    "exchanges": exchanges,
                    "can_edit_exchange": can_edit_exchange,
                    "days_since_creation": days_since_creation,
                    "days_remaining": days_remaining,
                    "client_type": client_type,
                    "can_edit_loss_percentage": can_edit_loss_percentage,
                    "has_transactions": has_transactions,
                    "error": f"Invalid percentage value: {str(e)}",
                })
        
        # Always save the client_exchange (exchange might have been updated, percentages updated above)
        client_exchange.save()
        
        # Track if report config was successfully updated
        report_config_updated = False
        
        # Update / normalize stored split percentages on the account.
        # IMPORTANT: Company% + MyOwn% must equal My Total %.
        if friend_percentage or my_own_percentage:
            try:
                epsilon = Decimal("0.01")
                # Ensure proper Decimal conversion - handle empty strings and preserve decimal precision
                friend_pct = Decimal(str(friend_percentage).strip()) if friend_percentage and friend_percentage.strip() else Decimal('0')
                own_pct = Decimal(str(my_own_percentage).strip()) if my_own_percentage and my_own_percentage.strip() else Decimal('0')
                my_total_pct = Decimal(str(client_exchange.my_percentage))
                
                sum_percentages = friend_pct + own_pct

                # If My Total % changed and sum doesn't match, auto-rebalance.
                if old_my_percentage is not None and Decimal(str(old_my_percentage)) != my_total_pct and abs(sum_percentages - my_total_pct) >= epsilon:
                    # Prefer keeping Company% if possible, adjust My Own %.
                    if friend_pct > my_total_pct:
                        friend_pct = my_total_pct
                        own_pct = Decimal("0")
                    else:
                        own_pct = my_total_pct - friend_pct
                    sum_percentages = friend_pct + own_pct

                # Validate: company % + my own % = my total %
                if abs(sum_percentages - my_total_pct) < epsilon:
                    client_exchange.company_percentage = friend_pct
                    client_exchange.my_own_percentage = own_pct
                    client_exchange.save(update_fields=["company_percentage", "my_own_percentage"])
                    report_config_updated = True
                else:
                    from django.contrib import messages
                    messages.warning(
                        request,
                        f"Company % ({friend_pct:.2f}) + My Own % ({own_pct:.2f}) = {sum_percentages:.2f}, "
                        f"but My Total % = {my_total_pct:.2f}. Report config not updated."
                    )
            except (ValueError, TypeError) as e:
                # Invalid decimal values - skip report config update
                from django.contrib import messages
                messages.warning(request, f"Invalid percentage values: {str(e)}")
                pass
        
        # Only show success message once, and only if update was successful
        from django.contrib import messages
        if percentage_updated or report_config_updated:
            messages.success(request, "Percentages updated successfully.")
        
        return redirect("exchange_account_detail", pk=client_exchange.pk)

    
    # GET request - prepare context
    exchanges = Exchange.objects.all().order_by("name")
    client_type = "company" if False else "my"
    
    # Check if loss percentage can be edited (immutable if transactions exist)
    has_transactions = Transaction.objects.filter(client_exchange=client_exchange).exists()
    can_edit_loss_percentage = not has_transactions
    
    return render(request, "core/exchanges/edit_client_link.html", {
        "client_exchange": client_exchange,
        "exchanges": exchanges,
        "can_edit_exchange": can_edit_exchange,
        "client_type": client_type,
        "can_edit_loss_percentage": can_edit_loss_percentage,
        "has_transactions": has_transactions,
    })


@login_required
@require_http_methods(["POST"])
def client_exchange_delete(request, pk):
    """
    Delete ONE client-exchange account for the current user.

    This is a destructive action: it removes the exchange account and all trading audit history
    (Transactions/Settlements) for that account. It also deletes linked payment ledger entries
    (PendingPaymentTransaction) so the client's pending totals remain consistent.
    """
    from django.contrib import messages
    from django.db import transaction as db_transaction
    from django.utils.http import url_has_allowed_host_and_scheme
    from .models import PendingPaymentTransaction, Client

    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()

    with db_transaction.atomic():
        account = (
            ClientExchangeAccount.objects.select_for_update()
            .select_related("client", "exchange")
            .get(pk=pk, client__user=request.user)
        )
        client = Client.objects.select_for_update().get(pk=account.client_id, user=request.user)

        # 1) Delete linked payment transactions first so they reverse their effects on pending balances.
        linked_payments = PendingPaymentTransaction.objects.filter(client_exchange=account).order_by("-date", "-id")
        for tx in linked_payments:
            tx.delete()

        # 2) If this account still has a residual pending_balance (e.g., seeded but no payments recorded),
        # remove it from the client before deleting the account.
        if account.pending_balance:
            client.pending_balance = int(client.pending_balance) - int(account.pending_balance)
            client.save(update_fields=["pending_balance"])

        # 3) Delete trading audit history for this account (hard delete).
        Settlement.objects.filter(client_exchange=account).delete()
        Transaction.objects.filter(client_exchange=account).delete()

        exchange_name = account.exchange.name
        account.delete()

    messages.success(request, f"Deleted exchange account '{exchange_name}' for client '{client.name}'.")

    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect(reverse("client_detail", args=[client.pk]))


# Transaction Management Views
@login_required


def transaction_create(request):
    """Create a new transaction (audit-only)."""
    from datetime import date as date_today
    from django.contrib import messages
    
    clients = Client.objects.filter(user=request.user).order_by("name")
    
    if request.method == "POST":
        client_exchange_id = request.POST.get("client_exchange")
        tx_date = request.POST.get("date")
        tx_type = request.POST.get("type")  # Use 'type' not 'transaction_type'
        amount = Decimal(request.POST.get("amount", 0))
        note = request.POST.get("note", "")
        
        if client_exchange_id and tx_date and tx_type and amount != 0:
            try:
                client_exchange = ClientExchangeAccount.objects.get(
                    pk=client_exchange_id,
                    client__user=request.user
                )
                
                # Transactions are audit-only - create transaction record with balances
                # For manual transactions, before = after (no balance change)
                funding_before = client_exchange.funding
                exchange_before = client_exchange.exchange_balance
                
                transaction = Transaction.objects.create(
                    client_exchange=client_exchange,
                    date=timezone.make_aware(datetime.strptime(tx_date, "%Y-%m-%d").date()),
                    type=tx_type,  # Use 'type' field
                    amount=int(amount),
                    exchange_balance_after=client_exchange.exchange_balance,
                    notes=note,
                )
                
                messages.success(request, "Transaction created successfully.")
                return redirect(reverse("transaction_list"))
            except Exception as e:
                messages.error(request, f"Error creating transaction: {str(e)}")

    
    # Get client-exchanges for selected client (if provided)
    client_id = request.GET.get("client")
    client_exchanges = ClientExchangeAccount.objects.filter(client__user=request.user).select_related("client", "exchange")
    if client_id:

        pass
    client_exchanges = client_exchanges.order_by("client__name", "exchange__name")
    
    return render(request, "core/transactions/create.html", {
        "clients": clients,
        "client_exchanges": client_exchanges,
        "selected_client": int(client_id) if client_id else None,
        "today": date_today.today(),
    })


@login_required


def transaction_detail(request, pk):


    """Show detailed view of a transaction with balance before and after."""
    transaction = get_object_or_404(Transaction, pk=pk, client_exchange__client__user=request.user)
    client_exchange = transaction.client_exchange
    client = client_exchange.client
    
    # Get transactions before this one (same date but created before, or earlier dates)
    transactions_before = Transaction.objects.filter(
        client_exchange=client_exchange,
    ).filter(
        Q(date__lt=transaction.date) | 
        (Q(date=transaction.date) & Q(created_at__lt=transaction.created_at))
    )
    
    # Transactions are audit-only in PIN-TO-PIN system
    # Balance is stored in ClientExchangeAccount, not calculated from transactions
    # Get balance from account directly
    balance_before = client_exchange.exchange_balance
    balance_after = transaction.exchange_balance_after if hasattr(transaction, 'exchange_balance_after') else balance_before
    
    # Calculate differences
    balance_change = (balance_after or 0) - (balance_before or 0)
    
    # Determine client type for URL routing
    client_type = "my"  # All clients are now "my clients"
    
    # Shares are not stored in transactions - they're calculated from accounts
    calculated_your_share = Decimal(0)
    calculated_company_share = Decimal(0)
    calculated_client_share = Decimal(0)

    
    context = {
        "transaction": transaction,
        "client": client,
        "client_exchange": client_exchange,
        "client_type": client_type,
        "calculated_your_share": calculated_your_share,
        "calculated_company_share": calculated_company_share,
        "calculated_client_share": calculated_client_share,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "balance_change": balance_change,
    }
    return render(request, "core/transactions/detail.html", context)


@login_required


def transaction_edit(request, pk):
    """Edit an existing transaction (audit-only)."""
    from django.contrib import messages

    transaction = get_object_or_404(Transaction, pk=pk, client_exchange__client__user=request.user)
    
    if request.method == "POST":
        tx_date = request.POST.get("date")
        tx_type = request.POST.get("type")
        amount_str = request.POST.get("amount", "0")
        note = request.POST.get("note", "")
        
        if tx_date and tx_type:
            try:
                # Convert string amount to Decimal then to int (for BigIntegerField)
                amount = int(Decimal(amount_str.replace(',', '')))
                
                # Parse date - handle potential errors
                try:
                    naive_dt = datetime.strptime(tx_date, "%Y-%m-%d")
                except ValueError:
                    messages.error(request, "Invalid date format. Please use YYYY-MM-DD.")
                    return render(request, "core/transactions/edit.html", {"transaction": transaction})

                # Maintain original time if available
                if transaction.date:
                    original_time = transaction.date
                    # If it's aware, make it naive for the replace operation
                    if timezone.is_aware(original_time):
                        original_time = timezone.make_naive(original_time)
                    
                    naive_dt = naive_dt.replace(
                        hour=original_time.hour,
                        minute=original_time.minute,
                        second=original_time.second
                    )
                
                # Ensure it's aware before saving
                if not timezone.is_aware(naive_dt):
                    transaction.date = timezone.make_aware(naive_dt)
                else:
                    transaction.date = naive_dt

                transaction.type = tx_type
                transaction.amount = amount
                transaction.notes = note
                transaction.save()

                messages.success(request, "Transaction audit log updated successfully.")
                
                # Redirect to the account detail page if possible, otherwise to transaction list
                return redirect(reverse("exchange_account_detail", args=[transaction.client_exchange.pk]))
            except ValueError as ve:
                messages.error(request, f"Invalid numeric data: {str(ve)}")
            except Exception as e:
                messages.error(request, f"Error updating transaction: {str(e)}")
    
    return render(request, "core/transactions/edit.html", {"transaction": transaction})


def transaction_delete_logic(transaction):
    """Core logic to delete a transaction and revert balances, shared between web and API."""
    from django.db import transaction as db_transaction
    from .models import Settlement, Transaction
    account = transaction.client_exchange
    
    with db_transaction.atomic():
        # 1. Capture transaction details before deletion
        transaction_type = transaction.type
        transaction_amount = transaction.amount
        
        # 2. Initial revert using "before" values (primary method)
        if transaction.funding_before is not None:
            account.funding = transaction.funding_before
        
        if transaction.exchange_balance_before is not None:
            account.exchange_balance = transaction.exchange_balance_before
        
        # Adjust balances for auto-refunding entries that may not track before/after values
        if transaction.type == 'FUNDING_AUTO' and transaction.funding_before is None:
            auto_amount = transaction.amount or 0
            account.funding = max(0, account.funding - auto_amount)
            account.exchange_balance = max(0, account.exchange_balance - auto_amount)
        
        # 3. Special case: If we're deleting a payment settlement, delete corresponding Settlement record
        if transaction_type in ['RECORD_PAYMENT', 'SETTLEMENT_SHARE']:
            last_settlement = Settlement.objects.filter(client_exchange=account).order_by('-date', '-id').first()
            if last_settlement:
                if last_settlement.amount == abs(transaction_amount):
                    last_settlement.delete()
        
        # 4. Delete the transaction record
        transaction.delete()
        
        # 5. RECOMPUTE SAFETY NET: Sync account balance with the NEW latest transaction
        # This ensures the Account Summary always matches the last valid state in history.
        latest_tx = Transaction.objects.filter(client_exchange=account).order_by('-created_at', '-id').first()
        if latest_tx:
            if latest_tx.funding_after is not None:
                account.funding = latest_tx.funding_after
            if latest_tx.exchange_balance_after is not None:
                account.exchange_balance = latest_tx.exchange_balance_after
        else:
            # No transactions left - reset everything to zero
            account.funding = 0
            account.exchange_balance = 0
        
        # 6. Reset the PnL cycle. This is CRITICAL.
        account.locked_initial_final_share = None
        account.locked_share_percentage = None
        account.locked_initial_pnl = None
        account.cycle_start_date = None
        account.locked_initial_funding = None
        
        # 7. Save account changes
        account.save()
        
        # 8. Force a fresh re-lock of the share based on the NEW reverted balances
        account.lock_initial_share_if_needed()

@login_required
def transaction_delete(request, pk):
    """Delete only the latest transaction and revert account balances."""
    from django.contrib import messages
    from django.shortcuts import get_object_or_404, redirect
    from django.urls import reverse
    
    transaction = get_object_or_404(Transaction, pk=pk, client_exchange__client__user=request.user)
    account = transaction.client_exchange
    
    # Check if this is the latest transaction for this account
    latest_tx = Transaction.objects.filter(client_exchange=account).order_by('-created_at', '-id').first()
    
    if not latest_tx or transaction.pk != latest_tx.pk:
        messages.error(request, "Only the last transaction can be deleted to maintain logic consistency.")
        return redirect(reverse("exchange_account_detail", args=[account.pk]))
    
    try:
        transaction_delete_logic(transaction)
        messages.success(request, "Last transaction deleted. Balances and My Share have been recomputed successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting transaction: {str(e)}")
        
    return redirect(reverse("exchange_account_detail", args=[account.pk]))


@login_required


def get_exchanges_for_client(request):


    """AJAX endpoint to get client-exchanges for a client."""
    client_id = request.GET.get("client_id")
    if client_id:

        return JsonResponse(list(client_exchanges), safe=False)
    return JsonResponse([], safe=False)


@login_required


def get_latest_balance_for_exchange(request, client_pk):


    """AJAX endpoint to get latest balance data for a client-exchange."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    client_exchange_id = request.GET.get("client_exchange_id")
    
    if client_exchange_id:
        try:
            client_exchange = ClientExchangeAccount.objects.get(pk=client_exchange_id, client=client)
            
            # Get calculated balance from account (not transactions)
            # In PIN-TO-PIN system, balance comes from exchange_balance field
            calculated_balance = client_exchange.exchange_balance
            
            # TODO: ClientDailyBalance model removed - add back if needed
            latest_balance = None
            
            if latest_balance:
                return JsonResponse({
                    "success": True,
                    "date": latest_balance.date.isoformat(),
                    "remaining_balance": str(latest_balance.remaining_balance),
                    "note": latest_balance.note or "",
                    "calculated_balance": str(calculated_balance),
                    "has_recorded_balance": True,
                    "total_funding": str(client_exchange.funding),
                })
            else:
                return JsonResponse({
                    "success": True,
                    "date": date.today().isoformat(),
                    "remaining_balance": str(calculated_balance),
                    "note": "",
                    "calculated_balance": str(calculated_balance),
                    "has_recorded_balance": False,
                    "total_funding": str(client_exchange.funding),
                })
        except ClientExchangeAccount.DoesNotExist:
            pass


    
    return JsonResponse({"success": False, "error": "Exchange ID required"}, status=400)


# Period-based Reports
@login_required


def report_daily(request):


    """Daily report for a specific date with graphs and analysis."""
    report_date_str = request.GET.get("date", date.today().isoformat())
    report_date = date.fromisoformat(report_date_str)
    # Get client_type from GET (to update session) or from session
    client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type_filter == '':

    
        pass
    # Base filter
    base_filter = {"client_exchange__client__user": request.user, "date": report_date}
    
    # All clients are now "my clients" - no filtering needed
    
    qs = Transaction.objects.filter(**base_filter)
    
    # CORRECTNESS LOGIC: Turnover = Σ(|ExchangeBalanceAfter − ExchangeBalanceBefore|) for TRADE transactions only
    # Turnover measures trading activity, NOT funding or settlements
    trade_qs = qs.filter(type='TRADE').exclude(
        exchange_balance_before__isnull=True
    ).exclude(
        exchange_balance_after__isnull=True
    )
    # Calculate turnover as sum of absolute exchange balance movements from trades
    total_turnover = sum(
        abs(tx.exchange_balance_after - tx.exchange_balance_before)
        for tx in trade_qs
    ) or 0
    
    # Your Total Profit = Sum(RECORD_PAYMENT.amount) - signed sum
    payment_qs = qs.filter(type='RECORD_PAYMENT')
    
    # Your Total Profit = Sum(RECORD_PAYMENT.amount) - signed sum
    your_total_profit = payment_qs.aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Income from clients = Sum of positive amounts
    your_profit = payment_qs.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Loss (paid to clients) = Absolute value of negative amounts
    your_loss = abs(payment_qs.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0))
    
    # 📘 MY PROFIT AND FRIEND PROFIT Calculation (split from Your Total Profit)
    # Calculate weighted average percentages, then split Your Total Profit
    
    my_profit_total = Decimal(0)
    friend_profit_total = Decimal(0)
    
    # Calculate weighted average percentages based on payment amounts
    total_weighted_my_own = Decimal(0)
    total_weighted_friend = Decimal(0)
    total_weighted_amount = Decimal(0)
    
    # Get payment transactions for splitting (single-table percentages).
    payment_transactions = payment_qs.select_related("client_exchange")
    
    tx_count = 0
    skipped_no_config = 0
    skipped_zero_pct = 0
    
    for tx in payment_transactions:
        tx_count += 1
        payment_amount = Decimal(str(tx.amount))  # Can be positive or negative
        account = tx.client_exchange
        my_total_pct = Decimal(str(account.my_percentage))
        
        if my_total_pct == 0:
            skipped_zero_pct += 1
            continue
        
        my_own_pct = Decimal(str(getattr(account, "my_own_percentage", 0) or 0))
        friend_pct = Decimal(str(getattr(account, "company_percentage", 0) or 0))

        # Weight by absolute payment amount
        weight = abs(payment_amount)
        weighted_my_own_contrib = weight * (my_own_pct / my_total_pct)
        weighted_friend_contrib = weight * (friend_pct / my_total_pct)
        total_weighted_my_own += weighted_my_own_contrib
        total_weighted_friend += weighted_friend_contrib
        total_weighted_amount += weight
    
    # Split Your Total Profit using weighted average percentages
    if total_weighted_amount > 0:
        # Calculate weighted average ratios
        weighted_my_own_ratio = total_weighted_my_own / total_weighted_amount
        weighted_friend_ratio = total_weighted_friend / total_weighted_amount
        
        # Split total profit proportionally (works for both positive and negative)
        my_profit_total = your_total_profit * weighted_my_own_ratio
        friend_profit_total = your_total_profit * weighted_friend_ratio
    elif your_total_profit == 0:
        # No profit/loss, so no split needed
        my_profit_total = Decimal(0)
        friend_profit_total = Decimal(0)
    else:
        # No report configs found, all goes to me
        my_profit_total = your_total_profit
        friend_profit_total = Decimal(0)
    
    company_profit = Decimal(0)
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-created_at")
    
    # Chart data - transaction type breakdown
    type_data = qs.values("type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        'FUNDING': ("Funding", "#4b5563"),
        'TRADE': ("Trade", "#6b7280"),
        'FEE': ("Fee", "#9ca3af"),
        'ADJUSTMENT': ("Adjustment", "#6b7280"),
        'RECORD_PAYMENT': ("Record Payment", "#10b981"),
    }
    for item in type_data:
        tx_type = item["type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)

    
    # Client-wise breakdown
    # Profit/Loss from RECORD_PAYMENT transactions
    client_payment_data = payment_qs.values("client_exchange__client__name", "client_exchange__client__code").annotate(
        profit=Sum("amount", filter=Q(amount__gt=0)),
        loss=Sum(Abs(F("amount")), filter=Q(amount__lt=0)),
        net_profit=Sum("amount")
    )
    
    # Turnover from TRADE transactions (exchange balance movement) per client
    client_trade_qs = trade_qs.values("client_exchange__client__name")
    client_turnover_map = {}
    for client_name in client_trade_qs.values_list("client_exchange__client__name", flat=True).distinct():
        client_trades = trade_qs.filter(client_exchange__client__name=client_name)
        client_turnover = sum(
            abs(tx.exchange_balance_after - tx.exchange_balance_before)
            for tx in client_trades
        ) or 0
        client_turnover_map[client_name] = client_turnover
    
    # Combine profit/loss and turnover data
    client_data = []
    for item in client_payment_data:
        client_name = item["client_exchange__client__name"]
        client_code = item["client_exchange__client__code"]
        client_data.append({
            "name": client_name,
            "code": client_code,
            "profit": item["profit"] or 0,
            "loss": item["loss"] or 0,
            "net_profit": item["net_profit"] or 0,
            "turnover": client_turnover_map.get(client_name, 0)
        })
    
    # Sort by net profit descending
    client_performance = sorted(client_data, key=lambda x: x["net_profit"], reverse=True)
    
    # Sort by turnover and limit to top 10 for charts
    client_data_chart = sorted(client_data, key=lambda x: x["turnover"], reverse=True)[:10]
    
    client_labels = [item["name"] for item in client_data_chart]
    client_profits = [float(item["profit"] or 0) for item in client_data_chart]
    
    # Analysis
    net_profit = float(your_total_profit)  # Net profit = signed sum
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    
    context = {
        "report_date": report_date,
        "total_turnover": total_turnover,
        "your_total_profit": your_total_profit,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "client_type_filter": client_type_filter,
        "my_profit": my_profit_total,  # Pass Decimal directly to preserve decimals
        "friend_profit": friend_profit_total,  # Pass Decimal directly to preserve decimals
        "company_profit": company_profit,
        "transactions": transactions,
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
        "client_performance": client_performance,
    }
    return render(request, "core/reports/daily.html", context)


@login_required


def report_weekly(request):


    """Weekly report for a specific week with graphs and analysis."""
    week_start_str = request.GET.get("week_start", None)
    if week_start_str:
        week_start = date.fromisoformat(week_start_str)
    else:
        # Default to current week (Monday)
        today = date.today()
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday)
    
    week_end = week_start + timedelta(days=6)
    
    qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__gte=week_start, date__lte=week_end)
    
    # CORRECTNESS LOGIC: Turnover = Σ(|ExchangeBalanceAfter − ExchangeBalanceBefore|) for TRADE transactions only
    # Turnover measures trading activity, NOT funding or settlements
    trade_qs = qs.filter(type='TRADE').exclude(
        exchange_balance_before__isnull=True
    ).exclude(
        exchange_balance_after__isnull=True
    )
    # Calculate turnover as sum of absolute exchange balance movements from trades
    total_turnover = sum(
        abs(tx.exchange_balance_after - tx.exchange_balance_before)
        for tx in trade_qs
    ) or 0
    
    # Your Total Profit = Sum(RECORD_PAYMENT.amount) - signed sum
    payment_qs = qs.filter(type='RECORD_PAYMENT')
    your_total_profit = payment_qs.aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Income from clients = Sum of positive amounts
    your_profit = payment_qs.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Loss (paid to clients) = Absolute value of negative amounts
    your_loss = abs(payment_qs.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0))
    
    # 📘 MY PROFIT AND FRIEND PROFIT Calculation (split from Your Total Profit)
    # Calculate weighted average percentages, then split Your Total Profit
    
    my_profit_total = Decimal(0)
    friend_profit_total = Decimal(0)
    
    # Calculate weighted average percentages based on payment amounts
    total_weighted_my_own = Decimal(0)
    total_weighted_friend = Decimal(0)
    total_weighted_amount = Decimal(0)
    
    # Get payment transactions for splitting (single-table percentages).
    payment_transactions = payment_qs.select_related("client_exchange")
    
    tx_count = 0
    skipped_no_config = 0
    skipped_zero_pct = 0
    
    for tx in payment_transactions:
        tx_count += 1
        payment_amount = Decimal(str(tx.amount))  # Can be positive or negative
        account = tx.client_exchange
        my_total_pct = Decimal(str(account.my_percentage))
        
        if my_total_pct == 0:
            skipped_zero_pct += 1
            continue
        
        my_own_pct = Decimal(str(getattr(account, "my_own_percentage", 0) or 0))
        friend_pct = Decimal(str(getattr(account, "company_percentage", 0) or 0))

        # Weight by absolute payment amount
        weight = abs(payment_amount)
        weighted_my_own_contrib = weight * (my_own_pct / my_total_pct)
        weighted_friend_contrib = weight * (friend_pct / my_total_pct)
        total_weighted_my_own += weighted_my_own_contrib
        total_weighted_friend += weighted_friend_contrib
        total_weighted_amount += weight
    
    # Split Your Total Profit using weighted average percentages
    if total_weighted_amount > 0:
        # Calculate weighted average ratios
        weighted_my_own_ratio = total_weighted_my_own / total_weighted_amount
        weighted_friend_ratio = total_weighted_friend / total_weighted_amount
        
        # Split total profit proportionally (works for both positive and negative)
        my_profit_total = your_total_profit * weighted_my_own_ratio
        friend_profit_total = your_total_profit * weighted_friend_ratio
    elif your_total_profit == 0:
        # No profit/loss, so no split needed
        my_profit_total = Decimal(0)
        friend_profit_total = Decimal(0)
    else:
        # No report configs found, all goes to me
        my_profit_total = your_total_profit
        friend_profit_total = Decimal(0)
    
    company_profit = Decimal(0)
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    # Daily breakdown for the week
    daily_labels = []
    daily_profit = []
    daily_loss = []
    daily_turnover = []
    
    for i in range(7):
        current_date = week_start + timedelta(days=i)
        daily_labels.append(current_date.strftime("%a %d"))
        
        day_qs = qs.filter(date=current_date)
        # Profit/Loss from RECORD_PAYMENT transactions
        day_payment_qs = day_qs.filter(type='RECORD_PAYMENT')
        day_profit = day_payment_qs.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or 0
        day_loss = abs(day_payment_qs.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or 0)
        # Turnover from TRADE transactions (exchange balance movement)
        day_trade_qs = day_qs.filter(type='TRADE').exclude(
            exchange_balance_before__isnull=True
        ).exclude(
            exchange_balance_after__isnull=True
        )
        day_turnover = sum(
            abs(tx.exchange_balance_after - tx.exchange_balance_before)
            for tx in day_trade_qs
        ) or 0
        
        daily_profit.append(float(day_profit))
        daily_loss.append(float(day_loss))
        daily_turnover.append(float(day_turnover))
    
    # Transaction type breakdown
    type_data = qs.values("type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        'FUNDING': ("Funding", "#4b5563"),
        'TRADE': ("Trade", "#6b7280"),
        'FEE': ("Fee", "#9ca3af"),
        'ADJUSTMENT': ("Adjustment", "#6b7280"),
        'RECORD_PAYMENT': ("Record Payment", "#10b981"),
    }
    for item in type_data:
        tx_type = item["type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)

    
    # Analysis
    net_profit = float(your_total_profit)  # Net profit = signed sum
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    avg_daily_turnover = float(total_turnover) / 7
    
    # Client-wise breakdown for the week
    client_payment_data = payment_qs.values("client_exchange__client__name", "client_exchange__client__code").annotate(
        profit=Sum("amount", filter=Q(amount__gt=0)),
        loss=Sum(Abs(F("amount")), filter=Q(amount__lt=0)),
        net_profit=Sum("amount")
    )
    
    # Turnover from TRADE transactions per client
    client_turnover_map = {}
    client_trade_names = trade_qs.values_list("client_exchange__client__name", flat=True).distinct()
    for client_name in client_trade_names:
        client_trades = trade_qs.filter(client_exchange__client__name=client_name)
        client_turnover = sum(
            abs(tx.exchange_balance_after - tx.exchange_balance_before)
            for tx in client_trades
        ) or 0
        client_turnover_map[client_name] = client_turnover
    
    client_data = []
    for item in client_payment_data:
        client_name = item["client_exchange__client__name"]
        client_data.append({
            "name": client_name,
            "code": item["client_exchange__client__code"],
            "profit": item["profit"] or 0,
            "loss": item["loss"] or 0,
            "net_profit": item["net_profit"] or 0,
            "turnover": client_turnover_map.get(client_name, 0)
        })
    
    client_performance = sorted(client_data, key=lambda x: x["net_profit"], reverse=True)

    context = {
        "week_start": week_start,
        "week_end": week_end,
        "total_turnover": total_turnover,
        "your_total_profit": your_total_profit,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "avg_daily_turnover": avg_daily_turnover,
        "my_profit": my_profit_total,  # Pass Decimal directly to preserve decimals
        "friend_profit": friend_profit_total,  # Pass Decimal directly to preserve decimals
        "company_profit": company_profit,
        "transactions": transactions,
        "daily_labels": json.dumps(daily_labels),
        "daily_profit": json.dumps(daily_profit),
        "daily_loss": json.dumps(daily_loss),
        "daily_turnover": json.dumps(daily_turnover),
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "client_performance": client_performance,
    }
    return render(request, "core/reports/weekly.html", context)


@login_required


def report_monthly(request):


    """Monthly report for a specific month with graphs and analysis."""
    month_str = request.GET.get("month", date.today().strftime("%Y-%m"))
    year, month = map(int, month_str.split("-"))
    
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)
    
    qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__gte=month_start, date__lte=month_end)
    
    # CORRECTNESS LOGIC: Turnover = Σ(|ExchangeBalanceAfter − ExchangeBalanceBefore|) for TRADE transactions only
    # Turnover measures trading activity, NOT funding or settlements
    trade_qs = qs.filter(type='TRADE').exclude(
        exchange_balance_before__isnull=True
    ).exclude(
        exchange_balance_after__isnull=True
    )
    # Calculate turnover as sum of absolute exchange balance movements from trades
    total_turnover = sum(
        abs(tx.exchange_balance_after - tx.exchange_balance_before)
        for tx in trade_qs
    ) or 0
    
    # Your Total Profit = Sum(RECORD_PAYMENT.amount) - signed sum
    payment_qs = qs.filter(type='RECORD_PAYMENT')
    your_total_profit = payment_qs.aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Income from clients = Sum of positive amounts
    your_profit = payment_qs.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Loss (paid to clients) = Absolute value of negative amounts
    your_loss = abs(payment_qs.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0))
    
    # 📘 MY PROFIT AND FRIEND PROFIT Calculation (split from Your Total Profit)
    # Calculate weighted average percentages, then split Your Total Profit
    
    my_profit_total = Decimal(0)
    friend_profit_total = Decimal(0)
    
    # Calculate weighted average percentages based on payment amounts
    total_weighted_my_own = Decimal(0)
    total_weighted_friend = Decimal(0)
    total_weighted_amount = Decimal(0)
    
    # Get payment transactions for splitting (single-table percentages).
    payment_transactions = payment_qs.select_related("client_exchange")
    
    tx_count = 0
    skipped_no_config = 0
    skipped_zero_pct = 0
    
    for tx in payment_transactions:
        tx_count += 1
        payment_amount = Decimal(str(tx.amount))  # Can be positive or negative
        account = tx.client_exchange
        my_total_pct = Decimal(str(account.my_percentage))
        
        if my_total_pct == 0:
            skipped_zero_pct += 1
            continue
        
        my_own_pct = Decimal(str(getattr(account, "my_own_percentage", 0) or 0))
        friend_pct = Decimal(str(getattr(account, "company_percentage", 0) or 0))

        # Weight by absolute payment amount
        weight = abs(payment_amount)
        weighted_my_own_contrib = weight * (my_own_pct / my_total_pct)
        weighted_friend_contrib = weight * (friend_pct / my_total_pct)
        total_weighted_my_own += weighted_my_own_contrib
        total_weighted_friend += weighted_friend_contrib
        total_weighted_amount += weight
    
    # Split Your Total Profit using weighted average percentages
    if total_weighted_amount > 0:
        # Calculate weighted average ratios
        weighted_my_own_ratio = total_weighted_my_own / total_weighted_amount
        weighted_friend_ratio = total_weighted_friend / total_weighted_amount
        
        # Split total profit proportionally (works for both positive and negative)
        my_profit_total = your_total_profit * weighted_my_own_ratio
        friend_profit_total = your_total_profit * weighted_friend_ratio
    elif your_total_profit == 0:
        # No profit/loss, so no split needed
        my_profit_total = Decimal(0)
        friend_profit_total = Decimal(0)
    else:
        # No report configs found, all goes to me
        my_profit_total = your_total_profit
        friend_profit_total = Decimal(0)
    
    company_profit = Decimal(0)
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    # Weekly breakdown for the month
    weekly_labels = []
    weekly_profit = []
    weekly_loss = []
    weekly_turnover = []
    
    current_date = month_start
    week_num = 1
    while current_date <= month_end:
        week_end_date = min(current_date + timedelta(days=6), month_end)

        weekly_labels.append(f"Week {week_num} ({current_date.strftime('%d')}-{week_end_date.strftime('%d %b')})")
        
        week_qs = qs.filter(date__gte=current_date, date__lte=week_end_date)
        # Profit/Loss from RECORD_PAYMENT transactions
        week_payment_qs = week_qs.filter(type='RECORD_PAYMENT')
        week_profit = week_payment_qs.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or 0
        week_loss = abs(week_payment_qs.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or 0)
        # Turnover from TRADE transactions (exchange balance movement)
        week_trade_qs = week_qs.filter(type='TRADE').exclude(
            exchange_balance_before__isnull=True
        ).exclude(
            exchange_balance_after__isnull=True
        )
        week_turnover = sum(
            abs(tx.exchange_balance_after - tx.exchange_balance_before)
            for tx in week_trade_qs
        ) or 0
        
        weekly_profit.append(float(week_profit))
        weekly_loss.append(float(week_loss))
        weekly_turnover.append(float(week_turnover))
        
        current_date = week_end_date + timedelta(days=1)
        week_num += 1
    
    # Transaction type breakdown
    type_data = qs.values("type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        'FUNDING': ("Funding", "#4b5563"),
        'TRADE': ("Trade", "#6b7280"),
        'FEE': ("Fee", "#9ca3af"),
        'ADJUSTMENT': ("Adjustment", "#6b7280"),
        'RECORD_PAYMENT': ("Record Payment", "#10b981"),
    }
    for item in type_data:
        tx_type = item["type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)

    
    # Top clients
    # Profit from RECORD_PAYMENT transactions
    client_payment_data = payment_qs.values("client_exchange__client__name").annotate(
        profit=Sum("amount", filter=Q(amount__gt=0))
    )
    
    # Turnover from TRADE transactions (exchange balance movement) per client
    client_trade_qs = trade_qs.values("client_exchange__client__name")
    client_turnover_map = {}
    for client_name in client_trade_qs.values_list("client_exchange__client__name", flat=True).distinct():
        client_trades = trade_qs.filter(client_exchange__client__name=client_name)
        client_turnover = sum(
            abs(tx.exchange_balance_after - tx.exchange_balance_before)
            for tx in client_trades
        ) or 0
        client_turnover_map[client_name] = client_turnover
    
    # Combine profit and turnover data
    client_data = []
    for item in client_payment_data:
        client_name = item["client_exchange__client__name"]
        client_data.append({
            "client_exchange__client__name": client_name,
            "profit": item["profit"] or 0,
            "turnover": client_turnover_map.get(client_name, 0)
        })
    
    # Sort by profit and limit to top 10
    client_data = sorted(client_data, key=lambda x: x["profit"] or 0, reverse=True)[:10]
    
    client_labels = [item["client_exchange__client__name"] for item in client_data]
    client_profits = [float(item["profit"] or 0) for item in client_data]
    
    # Analysis
    net_profit = float(your_total_profit)  # Net profit = signed sum
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    days_in_month = (month_end - month_start).days + 1
    avg_daily_turnover = float(total_turnover) / days_in_month if days_in_month > 0 else 0
    
    # Client-wise breakdown for the month
    client_payment_data = payment_qs.values("client_exchange__client__name", "client_exchange__client__code").annotate(
        profit=Sum("amount", filter=Q(amount__gt=0)),
        loss=Sum(Abs(F("amount")), filter=Q(amount__lt=0)),
        net_profit=Sum("amount")
    )
    
    # Turnover from TRADE transactions per client
    client_turnover_map = {}
    client_trade_names = trade_qs.values_list("client_exchange__client__name", flat=True).distinct()
    for client_name in client_trade_names:
        client_trades = trade_qs.filter(client_exchange__client__name=client_name)
        client_turnover = sum(
            abs(tx.exchange_balance_after - tx.exchange_balance_before)
            for tx in client_trades
        ) or 0
        client_turnover_map[client_name] = client_turnover
    
    client_data = []
    for item in client_payment_data:
        client_name = item["client_exchange__client__name"]
        client_data.append({
            "name": client_name,
            "code": item["client_exchange__client__code"],
            "profit": item["profit"] or 0,
            "loss": item["loss"] or 0,
            "net_profit": item["net_profit"] or 0,
            "turnover": client_turnover_map.get(client_name, 0)
        })
    
    client_performance = sorted(client_data, key=lambda x: x["net_profit"], reverse=True)

    context = {
        "month_start": month_start,
        "month_end": month_end,
        "total_turnover": total_turnover,
        "your_total_profit": your_total_profit,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "avg_daily_turnover": avg_daily_turnover,
        "my_profit": my_profit_total,  # Pass Decimal directly to preserve decimals
        "friend_profit": friend_profit_total,  # Pass Decimal directly to preserve decimals
        "company_profit": company_profit,
        "transactions": transactions,
        "weekly_labels": json.dumps(weekly_labels),
        "weekly_profit": json.dumps(weekly_profit),
        "weekly_loss": json.dumps(weekly_loss),
        "weekly_turnover": json.dumps(weekly_turnover),
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
        "client_performance": client_performance,
    }
    return render(request, "core/reports/monthly.html", context)


@login_required


def report_custom(request):


    """Custom period report."""
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
    else:
        # Default to last 30 days
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
    
    qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__gte=start_date, date__lte=end_date)
    
    # CORRECTNESS LOGIC: Turnover = Σ(|ExchangeBalanceAfter − ExchangeBalanceBefore|) for TRADE transactions only
    # Turnover measures trading activity, NOT funding or settlements
    trade_qs = qs.filter(type='TRADE').exclude(
        exchange_balance_before__isnull=True
    ).exclude(
        exchange_balance_after__isnull=True
    )
    # Calculate turnover as sum of absolute exchange balance movements from trades
    total_turnover = sum(
        abs(tx.exchange_balance_after - tx.exchange_balance_before)
        for tx in trade_qs
    ) or 0
    
    # Your Total Profit = Sum(RECORD_PAYMENT.amount) - signed sum
    payment_qs = qs.filter(type='RECORD_PAYMENT')
    your_total_profit = payment_qs.aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Income from clients = Sum of positive amounts
    your_profit = payment_qs.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Loss (paid to clients) = Absolute value of negative amounts
    your_loss = abs(payment_qs.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0))
    
    # 📘 MY PROFIT AND FRIEND PROFIT Calculation (split from Your Total Profit)
    # Calculate weighted average percentages, then split Your Total Profit
    
    my_profit_total = Decimal(0)
    friend_profit_total = Decimal(0)
    
    # Calculate weighted average percentages based on payment amounts
    total_weighted_my_own = Decimal(0)
    total_weighted_friend = Decimal(0)
    total_weighted_amount = Decimal(0)
    
    # Get payment transactions for splitting (single-table percentages).
    payment_transactions = payment_qs.select_related("client_exchange")
    
    tx_count = 0
    skipped_no_config = 0
    skipped_zero_pct = 0
    
    for tx in payment_transactions:
        tx_count += 1
        payment_amount = Decimal(str(tx.amount))  # Can be positive or negative
        account = tx.client_exchange
        my_total_pct = Decimal(str(account.my_percentage))
        
        if my_total_pct == 0:
            skipped_zero_pct += 1
            continue
        
        my_own_pct = Decimal(str(getattr(account, "my_own_percentage", 0) or 0))
        friend_pct = Decimal(str(getattr(account, "company_percentage", 0) or 0))

        # Weight by absolute payment amount
        weight = abs(payment_amount)
        weighted_my_own_contrib = weight * (my_own_pct / my_total_pct)
        weighted_friend_contrib = weight * (friend_pct / my_total_pct)
        total_weighted_my_own += weighted_my_own_contrib
        total_weighted_friend += weighted_friend_contrib
        total_weighted_amount += weight
    
    # Split Your Total Profit using weighted average percentages
    if total_weighted_amount > 0:
        # Calculate weighted average ratios
        weighted_my_own_ratio = total_weighted_my_own / total_weighted_amount
        weighted_friend_ratio = total_weighted_friend / total_weighted_amount
        
        # Split total profit proportionally (works for both positive and negative)
        my_profit_total = your_total_profit * weighted_my_own_ratio
        friend_profit_total = your_total_profit * weighted_friend_ratio
    elif your_total_profit == 0:
        # No profit/loss, so no split needed
        my_profit_total = Decimal(0)
        friend_profit_total = Decimal(0)
    else:
        # No report configs found, all goes to me
        my_profit_total = your_total_profit
        friend_profit_total = Decimal(0)
    
    company_profit = Decimal(0)
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    context = {
        "start_date": start_date,
        "end_date": end_date,
        "total_turnover": total_turnover,
        "your_total_profit": your_total_profit,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "my_profit": my_profit_total,  # Pass Decimal directly to preserve decimals
        "friend_profit": friend_profit_total,  # Pass Decimal directly to preserve decimals
        "company_profit": company_profit,
        "transactions": transactions,
    }
    return render(request, "core/reports/custom.html", context)


# Export Views
@login_required


def export_report_csv(request):


    """Export report as CSV."""
    import csv
    
    report_type = request.GET.get("type", "all")
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:

        end_date = date.fromisoformat(end_date_str)
        qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__gte=start_date, date__lte=end_date)
    else:

        qs = Transaction.objects.filter(client_exchange__client__user=request.user)

    
    if report_type == "profit":
        # Filter by profit transactions (not used in PIN-TO-PIN)
        pass
    elif report_type == "loss":
        # Filter by loss transactions (not used in PIN-TO-PIN)
        pass

    
    qs = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="report_{date.today()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(["Date", "Client", "Exchange", "Type", "Amount", "Exchange Balance After", "Note"])
    
    for tx in qs:
        writer.writerow([
            tx.date,
            tx.client_exchange.client.name,
            tx.client_exchange.exchange.name,
            tx.get_type_display(),
            tx.amount,
            tx.exchange_balance_after or 0,
            tx.notes or "",
        ])
    
    return response


# Client-specific and Exchange-specific Reports
@login_required


def report_client(request, client_pk):


    """Report for a specific client."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:

        end_date = date.fromisoformat(end_date_str)
        qs = Transaction.objects.filter(client_exchange__client=client, date__gte=start_date, date__lte=end_date)
    else:

        qs = Transaction.objects.filter(client_exchange__client=client)

    # CORRECTNESS LOGIC: Turnover = Σ(|ExchangeBalanceAfter − ExchangeBalanceBefore|) for TRADE transactions only
    # Turnover measures trading activity, NOT funding or settlements
    trade_qs = qs.filter(type='TRADE').exclude(
        exchange_balance_before__isnull=True
    ).exclude(
        exchange_balance_after__isnull=True
    )
    # Calculate turnover as sum of absolute exchange balance movements from trades
    total_turnover = sum(
        abs(tx.exchange_balance_after - tx.exchange_balance_before)
        for tx in trade_qs
    ) or 0
    
    # Your Total Profit = Sum(RECORD_PAYMENT.amount) - signed sum
    your_profit = payment_qs.aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    company_profit = Decimal(0)
    
    transactions = qs.select_related("client_exchange", "client_exchange__exchange", "client_exchange__client").order_by("-date", "-created_at")
    
    context = {
        "client": client,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "transactions": transactions,
    }
    return render(request, "core/reports/client.html", context)


@login_required


@login_required
def link_client_to_exchange(request):
    """Link a client to an exchange with percentage configuration."""
    if request.method == "POST":
        client_id = request.POST.get("client")
        exchange_id = request.POST.get("exchange")
        my_percentage = request.POST.get("my_percentage", "").strip()
        friend_percentage = request.POST.get("friend_percentage", "").strip()
        my_own_percentage = request.POST.get("my_own_percentage", "").strip()
        
        # Validation
        if not client_id or not exchange_id or not my_percentage:
            from django.contrib import messages
            messages.error(request, "Client, Exchange, and My Total % are required.")
            return render(request, "core/exchanges/link_to_client.html", {
                "clients": Client.objects.filter(user=request.user).order_by("name"),
                "exchanges": Exchange.objects.all().order_by("name"),
            })
        
        try:
            from decimal import Decimal
            client = Client.objects.get(pk=client_id, user=request.user)
            exchange = Exchange.objects.get(pk=exchange_id)
            my_pct = Decimal(str(my_percentage))
            
            # Validate percentage range
            if my_pct < 0 or my_pct > 100:
                from django.contrib import messages
                messages.error(request, "My Total % must be between 0 and 100.")
                return render(request, "core/exchanges/link_to_client.html", {
                    "clients": Client.objects.filter(user=request.user).order_by("name"),
                    "exchanges": Exchange.objects.all().order_by("name"),
                })
            
            friend_pct = Decimal(str(friend_percentage).strip()) if friend_percentage and friend_percentage.strip() else Decimal("0")
            own_pct = Decimal(str(my_own_percentage).strip()) if my_own_percentage and my_own_percentage.strip() else Decimal("0")

            # Normalize split so Company% + MyOwn% == MyTotal%
            # If user didn't fill anything, default: Company 0, MyOwn = MyTotal.
            if (not friend_percentage.strip()) and (not my_own_percentage.strip()):
                friend_pct = Decimal("0")
                own_pct = my_pct
            else:
                epsilon = Decimal("0.01")
                sum_pct = friend_pct + own_pct
                if abs(sum_pct - my_pct) >= epsilon:
                    # Prefer keeping Company% and adjust My Own %.
                    if friend_pct > my_pct:
                        friend_pct = my_pct
                        own_pct = Decimal("0")
                    else:
                        own_pct = my_pct - friend_pct

            # Create ClientExchangeAccount
            # MASKED SHARE SETTLEMENT SYSTEM: Set loss and profit share percentages
            # Default to my_percentage for both (can be changed later, but loss % becomes immutable once data exists)
            account = ClientExchangeAccount.objects.create(
                client=client,
                exchange=exchange,
                funding=0,
                exchange_balance=0,
                my_percentage=my_pct,
                company_percentage=friend_pct,
                my_own_percentage=own_pct,
                loss_share_percentage=my_pct,  # Default to my_percentage
                profit_share_percentage=my_pct,  # Default to my_percentage (can change anytime)
            )
            
            from django.contrib import messages
            messages.success(request, f"Successfully linked '{client.name}' to '{exchange.name}'.")
            return redirect(reverse("client_detail", args=[client.pk]))
            
        except (Client.DoesNotExist, Exchange.DoesNotExist):
            from django.contrib import messages
            messages.error(request, "Invalid client or exchange selected.")
        except ValueError:
            from django.contrib import messages
            messages.error(request, "Invalid percentage value. Please enter numbers only.")
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error linking client to exchange: {str(e)}")
    
    # GET request - show form
    # Check if client is pre-selected via query parameter
    selected_client_id = request.GET.get("client")
    if selected_client_id:
        # Validate that the client exists and belongs to the user
        try:
            Client.objects.get(pk=selected_client_id, user=request.user)
        except Client.DoesNotExist:
            selected_client_id = None  # Invalid client ID, don't pre-select
    
    return render(request, "core/exchanges/link_to_client.html", {
        "clients": Client.objects.filter(user=request.user).order_by("name"),
        "exchanges": Exchange.objects.all().order_by("name"),
        "selected_client_id": selected_client_id,  # Pass the string ID directly
    })


@login_required


@login_required
def exchange_account_detail_redirect_with_slug(request, pk):
    """Redirect to account detail URL that includes exchange name (e.g. .../account/13/dafa/)."""
    account = get_object_or_404(ClientExchangeAccount, pk=pk, client__user=request.user)
    slug = account.exchange.get_slug()
    return redirect(reverse("payments_exchange_account_detail", args=[account.pk, slug]))


@login_required
def exchange_account_detail_redirect_with_slug_clients(request, pk):
    """Redirect client account URL to include exchange slug (e.g. .../clients/exchanges/account/15/dafa/)."""
    account = get_object_or_404(ClientExchangeAccount, pk=pk, client__user=request.user)
    slug = account.exchange.get_slug()
    return redirect(reverse("exchange_account_detail_with_slug", args=[account.pk, slug]))


@login_required
def exchange_account_detail(request, pk, exchange_slug=None):
    """View details of a client-exchange account. For client-payments, exchange_slug is in URL (e.g. dafa, diamond)."""
    account = get_object_or_404(ClientExchangeAccount, pk=pk, client__user=request.user)
    
    # MASKED SHARE SETTLEMENT SYSTEM: Calculate values (lock share before getting remaining)
    account.lock_initial_share_if_needed()
    client_pnl = account.compute_client_pnl()
    final_share = account.compute_my_share()
    settlement_info = account.get_remaining_settlement_amount()
    remaining_amount = settlement_info['remaining']
    # Use share as fallback when remaining is 0 but there's unsettled PnL (edge case)
    pending_amount = remaining_amount if remaining_amount > 0 else (final_share if client_pnl != 0 else 0)

    # Client-payments pages need per-exchange pending split (e.g. dafa vs diamond).
    # We derive this from PendingPaymentTransaction notes when present; otherwise fall back to settlement logic above.
    pending_card_amount = pending_amount
    pending_card_direction = "settled"  # settled | client_owes_me | i_owe_client
    pending_card_source = "settlement"
    payment_transactions = None
    payments_paid = 0
    payments_received = 0
    payments_net_paid_minus_received = 0

    # Display share (personal): if My Own % exists, use it for "My%" and share display.
    # This prevents company split from being mixed into your personal view.
    from decimal import Decimal, ROUND_FLOOR
    abs_pnl_int = abs(int(client_pnl or 0))
    my_own_pct = Decimal(str(account.my_own_percentage or 0))
    my_total_pct = Decimal(str(account.my_percentage or 0))
    display_share_percentage = my_own_pct if my_own_pct > 0 else my_total_pct
    display_final_share = 0
    if abs_pnl_int > 0 and display_share_percentage > 0:
        exact = Decimal(abs_pnl_int) * (display_share_percentage / Decimal("100"))
        display_final_share = int(exact.to_integral_value(rounding=ROUND_FLOOR))
    display_remaining_settlement_amount = int(display_final_share)

    if pending_amount > 0:
        pending_card_direction = "i_owe_client" if client_pnl > 0 else "client_owes_me"

    try:
        if request.resolver_match and request.resolver_match.url_name == "payments_exchange_account_detail":
            from .models import PendingPaymentTransaction
            # Preferred: strict separation per exchange account (supports duplicate exchange names).
            payment_transactions = PendingPaymentTransaction.objects.filter(
                client_exchange=account
            ).order_by("-date", "-id")

            # Payment PnL for this exchange account (client-payments meaning):
            # net = Paid - Received
            payments_paid = (
                PendingPaymentTransaction.objects.filter(client_exchange=account, type="GIVEN")
                .aggregate(total=Sum("amount"))["total"]
                or 0
            )
            payments_received = (
                PendingPaymentTransaction.objects.filter(client_exchange=account, type="RECEIVED")
                .aggregate(total=Sum("amount"))["total"]
                or 0
            )
            payments_net_paid_minus_received = int(payments_paid) - int(payments_received)

            # Client-payments: pending is ONLY from the ledger (generated dues + real payments).
            pending_card_source = "ledger"
            pending_card_amount = abs(int(account.pending_balance))
            if account.pending_balance > 0:
                pending_card_direction = "client_owes_me"
            elif account.pending_balance < 0:
                pending_card_direction = "i_owe_client"
            else:
                pending_card_direction = "settled"

            # Backward compatibility: legacy transactions without client_exchange.
            if not payment_transactions.exists():
                identifiers = []
                if account.exchange.name:
                    identifiers.append(account.exchange.name)
                if account.exchange.code:
                    identifiers.append(account.exchange.code)

                if identifiers:
                    q = Q()
                    for ident in identifiers:
                        q |= Q(notes__icontains=ident)

                    payment_transactions = PendingPaymentTransaction.objects.filter(
                        client=account.client,
                        client_exchange__isnull=True,
                    ).filter(q).order_by("-date", "-id")
    except Exception:
        # If anything goes wrong, keep settlement-based fallback.
        pass
    
    # Backfill audit transactions for older "dues generated" settlements (so they show up in history).
    # Some earlier runs created Settlement rows without creating Transaction audit rows.
    try:
        dues_settlements = Settlement.objects.filter(
            client_exchange=account,
            notes__icontains="Dues generated",
        ).order_by("date", "id")

        for s in dues_settlements:
            linked_marker = f"Linked Settlement ID: {s.id}"
            has_audit = Transaction.objects.filter(
                client_exchange=account,
                notes__icontains=linked_marker,
            ).exists()
            if has_audit:
                continue

            # Infer loss/profit direction from the last known funding/exchange state before this settlement.
            last_state = (
                Transaction.objects.filter(
                    client_exchange=account,
                    exchange_balance_after__isnull=False,
                    funding_after__isnull=False,
                    date__lte=s.date,
                )
                .order_by("-date", "-id")
                .first()
            )

            pnl_sign = None
            if last_state:
                try:
                    pnl_sign = int(last_state.exchange_balance_after) - int(last_state.funding_after)
                except Exception:
                    pnl_sign = None

            if pnl_sign is None:
                pnl_sign = int(account.locked_initial_pnl or 0)

            is_loss_case = pnl_sign < 0
            abs_pnl = abs(int(pnl_sign)) if pnl_sign else 0

            # Best-effort masked capital (only for display/audit; balances are not recomputed from this).
            pct = int(account.loss_share_percentage or 0) if is_loss_case else int(account.profit_share_percentage or 0)
            if pct <= 0:
                try:
                    pct = int(round(float(account.my_percentage or 0)))
                except Exception:
                    pct = 0

            initial_share = int((abs_pnl * pct) // 100) if abs_pnl and pct else 0
            if initial_share <= 0:
                initial_share = int(s.amount)
            if abs_pnl <= 0:
                abs_pnl = int(s.amount)

            masked_capital = int(round((int(s.amount) * abs_pnl) / initial_share)) if initial_share else abs_pnl

            Transaction.objects.create(
                client_exchange=account,
                date=s.date,
                type="RECORD_PAYMENT",
                amount=int(s.amount) if is_loss_case else -int(s.amount),
                notes=f"Backfilled dues audit (not paid). Masked Capital: {masked_capital}. {linked_marker}",
            )

            if is_loss_case:
                Transaction.objects.create(
                    client_exchange=account,
                    date=s.date,
                    type="FUNDING_AUTO",
                    amount=int(masked_capital),
                    notes=f"Backfilled auto re-funding after dues generation (not paid). Masked Capital: {masked_capital}. {linked_marker}",
                )
    except Exception:
        pass

    # Get recent transactions for this account (Strict chronological order)
    transactions = Transaction.objects.filter(client_exchange=account).order_by("-created_at", "-id")[:20]
    
    # Get recent settlements
    settlements = Settlement.objects.filter(client_exchange=account).order_by("-date", "-created_at")[:10]
    total_settled = Settlement.objects.filter(client_exchange=account).aggregate(
        total=Sum('amount')
    )['total'] or 0
    
    return render(request, "core/exchanges/account_detail.html", {
        'account': account,
        'transactions': transactions,
        'settlements': settlements,
        'total_settled': total_settled,
        'client_pnl': client_pnl,
        'final_share': final_share,
        'remaining_amount': remaining_amount,
        'settlement_info': settlement_info,
        'display_share_percentage': display_share_percentage,
        'display_final_share': display_final_share,
        'display_remaining_settlement_amount': display_remaining_settlement_amount,
        'pending_amount': pending_amount,
        'pending_card_amount': pending_card_amount,
        'pending_card_direction': pending_card_direction,
        'pending_card_source': pending_card_source,
        'payment_transactions': payment_transactions,
        'payments_paid': payments_paid,
        'payments_received': payments_received,
        'payments_net_paid_minus_received': payments_net_paid_minus_received,
    })


@login_required
@require_http_methods(["GET", "POST"])
def pending_payment_settlement(request, pk, exchange_slug=None):
    """
    Client-payments settlement for ONE exchange account.

    Uses per-account pending ledger when available.
    The settlement amount cannot exceed the pending amount (abs).

    Sign / direction:
    - pending_display > 0: client needs to pay me (record RECEIVED)
    - pending_display < 0: I need to pay client (record GIVEN)
    """
    from django.contrib import messages
    from .models import PendingPaymentTransaction

    account = get_object_or_404(ClientExchangeAccount, pk=pk, client__user=request.user)

    # Client-payments settlement is STRICTLY against the per-account pending ledger.
    # Dues should be generated only via /clients/settlements/ -> "Generate pending dues".
    pending_display = int(account.pending_balance)  # +ve => client owes me, -ve => I owe client

    max_amount = abs(int(pending_display))

    if request.method == "POST":
        amount_str = (request.POST.get("amount") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        try:
            amount = int(amount_str)
        except Exception:
            amount = 0

        if amount <= 0:
            messages.error(request, "Amount must be greater than zero.")
        elif max_amount == 0:
            messages.info(request, "No pending amount to settle.")
        elif amount > max_amount:
            messages.error(request, f"Amount cannot be more than pending due ({max_amount}).")
        else:
            from django.db import transaction as db_transaction
            from .models import Client

            tx_type = "RECEIVED" if pending_display > 0 else "GIVEN"

            with db_transaction.atomic():
                locked_account = (
                    ClientExchangeAccount.objects.select_for_update()
                    .select_related("client")
                    .get(pk=account.pk, client__user=request.user)
                )
                locked_client = Client.objects.select_for_update().get(pk=locked_account.client_id, user=request.user)

                PendingPaymentTransaction.objects.create(
                    client=locked_client,
                    client_exchange=locked_account,
                    amount=amount,
                    type=tx_type,
                    date=timezone.now(),
                    notes=notes or f"Settlement - {locked_account.exchange.name}",
                    created_by=request.user,
                )
            messages.success(request, f"Settlement recorded: {tx_type} {amount}.")
            return redirect(reverse("payments_exchange_account_detail", args=[account.pk, account.exchange.get_slug()]))

    return render(request, "core/pending_payments/settlement.html", {
        "account": account,
        "pending_display": pending_display,
        "max_amount": max_amount,
    })


@login_required
def add_funding(request, account_id):
    """Add funding to a client-exchange account.
    
    FUNDING RULE: When money is given to client:
    - funding = funding + amount
    - exchange_balance = exchange_balance + amount
    Both must increase by the same amount simultaneously.
    """
    account = get_object_or_404(ClientExchangeAccount, pk=account_id, client__user=request.user)
    
    if request.method == "POST":
        amount_str = request.POST.get("amount", "").strip()
        notes = request.POST.get("notes", "").strip()
        
        # Strip commas and any non-digit characters (safety check)
        if amount_str:
            amount_str = amount_str.replace(',', '').replace('₹', '').strip()
        
        if not amount_str:
            from django.contrib import messages
            messages.error(request, "Amount is required.")
            return render(request, "core/exchanges/add_funding.html", {
                'account': account
            })
        
        try:
            amount = int(amount_str)
            if amount <= 0:
                from django.contrib import messages
                messages.error(request, "Amount must be greater than zero.")
                return render(request, "core/exchanges/add_funding.html", {
                    'account': account
                })
            
            # FUNDING RULE: Both funding and exchange_balance increase by the same amount
            # Manual funding closes old cycle and starts new cycle
            funding_before = account.funding
            exchange_before = account.exchange_balance
            
            account.funding += amount
            account.exchange_balance += amount
            
            # Close old cycle when manual funding is added
            account.close_cycle()
            
            account.save()
            
            # Create FUNDING_MANUAL transaction with before/after balances
            Transaction.objects.create(
                client_exchange=account,
                date=timezone.now(),
                type='FUNDING_MANUAL',
                amount=amount,
                funding_before=funding_before,
                funding_after=account.funding,
                exchange_balance_before=exchange_before,
                exchange_balance_after=account.exchange_balance,
                notes=notes or f"Manual funding added: {amount}"
            )
            
            from django.contrib import messages
            messages.success(
                request,
                f"Funding of {amount} added successfully. "
                f"Funding: {funding_before} → {account.funding}, "
                f"Balance: {exchange_before} → {account.exchange_balance}"
            )
            return redirect(reverse("exchange_account_detail", args=[account.pk]))
            
        except ValueError:
            from django.contrib import messages
            messages.error(request, "Invalid amount. Please enter a valid number.")
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error adding funding: {str(e)}")
    
    return render(request, "core/exchanges/add_funding.html", {
        'account': account
    })


@login_required
def update_exchange_balance(request, account_id):
    """Update exchange balance for a client-exchange account.

    Only exchange_balance changes. Funding remains untouched.
    Used for trades, fees, profits, losses.
    """
    account = get_object_or_404(ClientExchangeAccount, pk=account_id, client__user=request.user)
    
    if request.method == "POST":
        new_balance_str = request.POST.get("new_balance", "").strip()
        tx_type = request.POST.get("type", "TRADE")
        notes = request.POST.get("notes", "").strip()
        
        if not new_balance_str:
            from django.contrib import messages
            messages.error(request, "New balance is required.")
            return render(request, "core/exchanges/update_balance.html", {
                'account': account
            })
        
        try:
            new_balance = int(new_balance_str)
            if new_balance < 0:
                from django.contrib import messages
                messages.error(request, "Balance cannot be negative.")
                return render(request, "core/exchanges/update_balance.html", {
                    'account': account
                })
            
            exchange_before = account.exchange_balance
            funding_before = account.funding
            balance_change = new_balance - exchange_before
            
            # Only exchange_balance changes, funding stays the same (TRADE)
            account.exchange_balance = new_balance
            account.save()
            
            # Create transaction with before/after balances
            Transaction.objects.create(
                client_exchange=account,
                date=timezone.now(),
                type=tx_type,
                amount=abs(balance_change),  # Store absolute value
                funding_before=funding_before,
                funding_after=account.funding,  # Unchanged
                exchange_balance_before=exchange_before,
                exchange_balance_after=new_balance,
                notes=notes or f"{tx_type}: Balance updated {exchange_before} → {new_balance} ({balance_change:+})"
            )
            
            from django.contrib import messages
            messages.success(
                request,
                f"Balance updated successfully. "
                f"Exchange Balance: {exchange_before} → {new_balance} ({balance_change:+})"
            )
            return redirect(reverse("exchange_account_detail", args=[account.pk]))
            
        except ValueError:
            from django.contrib import messages
            messages.error(request, "Invalid balance. Please enter a valid number.")
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error updating balance: {str(e)}")
    
    return render(request, "core/exchanges/update_balance.html", {
        'account': account
    })


@login_required


@login_required
def record_payment(request, account_id):
    """
    ═══════════════════════════════════════════════════════════════════════════
    1️⃣ CORE RULE (DO NOT BREAK THIS)
    ═══════════════════════════════════════════════════════════════════════════
    Record Payment = Profit or Loss Event
    
    Who pays          Meaning                      Effect on YOU
    ──────────────────────────────────────────────────────────────────────────
    Client → You      Client loss settlement       ✅ Your PROFIT  (+X)
    You → Client      Client profit settlement     ❌ Your LOSS    (-X)
    
    SIGN CONVENTION:
      +X = Client paid YOU (Client loss)  → Your PROFIT
      -X = YOU paid client (Client profit) → Your LOSS
    ═══════════════════════════════════════════════════════════════════════════
    
    MASKED SHARE SETTLEMENT SYSTEM - Settlement Logic:
    - Uses database row locking to prevent concurrent payment race conditions
    - Calculates FinalShare using floor() rounding
    - Blocks settlement when FinalShare = 0
    - Validates against remaining settlement amount (FinalShare - SumOfSettlements)
    - Prevents negative funding/exchange_balance
    - Creates Settlement record to track payments
    - If Client_PnL < 0 (LOSS): funding = funding - MaskedCapital
    - If Client_PnL > 0 (PROFIT): exchange_balance = exchange_balance - MaskedCapital
    - Partial payments allowed
    
    Note: Ensures settlement safety at time of entry.
    Historical settlements may exceed current recalculated share by design.
    """
    # Initial load (no locking needed for GET requests)
    account = get_object_or_404(ClientExchangeAccount, pk=account_id, client__user=request.user)
    client_pnl = account.compute_client_pnl()
    redirect_to = request.GET.get('redirect_to', 'exchange_account_detail')
    
    # Lock share if needed (ensures share doesn't shrink)
    account.lock_initial_share_if_needed()
    
    # Calculate FinalShare using MASKED SHARE SETTLEMENT SYSTEM
    final_share = account.compute_my_share()
    settlement_info = account.get_remaining_settlement_amount()
    remaining_amount = settlement_info['remaining']
    overpaid_amount = settlement_info['overpaid']
    initial_final_share = settlement_info['initial_final_share']
    
    if request.method == "POST":
        paid_amount_str = request.POST.get("amount", "").strip()
        payment_date_str = request.POST.get("payment_date", "").strip()
        notes = request.POST.get("notes", "").strip()
        
        # Parse payment date (default to today if not provided)
        if payment_date_str:
            try:
                payment_date = timezone.make_aware(datetime.strptime(payment_date_str, "%Y-%m-%d"))
            except ValueError:
                from django.contrib import messages
                messages.error(request, "Invalid date format. Please use YYYY-MM-DD format.")
                display_remaining = calculate_display_remaining(client_pnl, remaining_amount)
                return render(request, "core/exchanges/record_payment.html", {
                    'account': account,
                    'client_pnl': client_pnl,
                    'final_share': final_share,
                    'remaining_amount': remaining_amount,
                    'display_remaining': display_remaining,
                    'today': date.today(),
                })
        else:
            payment_date = timezone.now()
        
        if not paid_amount_str:
            from django.contrib import messages
            messages.error(request, "Paid amount is required.")
            # Calculate display remaining
            display_remaining = calculate_display_remaining(client_pnl, remaining_amount)
            return render(request, "core/exchanges/record_payment.html", {
                'account': account,
                'client_pnl': client_pnl,
                'final_share': final_share,
                'remaining_amount': remaining_amount,
                'display_remaining': display_remaining,
            })
        
        try:
            paid_amount = int(paid_amount_str)
            if paid_amount <= 0:
                from django.contrib import messages
                messages.error(request, "Paid amount must be greater than zero.")
                # Calculate display remaining
                display_remaining = calculate_display_remaining(client_pnl, remaining_amount)
                return render(request, "core/exchanges/record_payment.html", {
                    'account': account,
                    'client_pnl': client_pnl,
                    'final_share': final_share,
                    'remaining_amount': remaining_amount,
                    'display_remaining': display_remaining,
                    'today': date.today(),
                })
            
            # CRITICAL: Use database row locking to prevent concurrent payment race conditions
            from django.db import transaction
            from django.core.exceptions import ValidationError
            
            try:
                with transaction.atomic():
                    # Lock the account row to prevent concurrent modifications
                    account = (
                        ClientExchangeAccount.objects
                        .select_for_update()
                        .get(pk=account_id, client__user=request.user)
                    )
                    
                    # ============================================================
                    # SETTLEMENT FLOW - EXACT ORDER (NON-NEGOTIABLE)
                    # ============================================================
                    # 1. Read balances (lock row) - DONE above with select_for_update
                    funding_before = account.funding
                    exchange_before = account.exchange_balance
                    
                    # 2. Compute PnL BEFORE update
                    client_pnl_before = account.compute_client_pnl()
                    
                    # 3. Lock share (if needed)
                    account.lock_initial_share_if_needed()
                    
                    # 4. Validate remaining
                    settlement_info = account.get_remaining_settlement_amount()
                    initial_final_share = settlement_info['initial_final_share']
                    remaining_amount = settlement_info['remaining']
                    overpaid_amount = settlement_info['overpaid']
                    total_settled = settlement_info['total_settled']
                    
                    # Block settlement when InitialFinalShare = 0
                    if initial_final_share == 0:
                        from django.contrib import messages
                        messages.warning(
                            request,
                            "No settlement allowed. Initial final share is zero (share percentage too small or PnL too small)."
                        )
                        if redirect_to == 'pending_summary':
                            return redirect(reverse("pending_summary"))
                        return redirect(reverse("exchange_account_detail", args=[account.pk]))
                    
                    # Validate against remaining settlement amount
                    if paid_amount > remaining_amount:
                        raise ValidationError(
                            f"Paid amount ({paid_amount}) cannot exceed remaining settlement amount ({remaining_amount}). "
                            f"Initial share: {initial_final_share}, Already settled: {total_settled}"
                        )
                    
                    # Check if PnL = 0 (trading flat, not settlement complete)
                    if client_pnl_before == 0:
                        from django.contrib import messages
                        messages.warning(request, "Account PnL is zero (trading flat). No settlement needed.")
                        if redirect_to == 'pending_summary':
                            return redirect(reverse("pending_summary"))
                        return redirect(reverse("exchange_account_detail", args=[account.pk]))
                    
                    # 5. Compute masked capital
                    masked_capital = account.compute_masked_capital(paid_amount)
                    if masked_capital == 0:
                        raise ValidationError(
                            "Cannot calculate masked capital. Initial final share is zero."
                        )
                    
                    # Get re-add capital option (LOSS CASE ONLY)
                    re_add_capital = False
                    if client_pnl_before < 0:
                        # LOSS CASE: Check if re-add capital option is enabled
                        re_add_capital_str = request.POST.get("re_add_capital", "").strip().lower()
                        re_add_capital = re_add_capital_str in ('true', '1', 'on', 'yes')
                    else:
                        # PROFIT CASE: Re-add capital is FORBIDDEN
                        re_add_capital_str = request.POST.get("re_add_capital", "").strip().lower()
                        if re_add_capital_str in ('true', '1', 'on', 'yes'):
                            raise ValidationError(
                                "Re-add capital option is not allowed for profit cases. "
                                "Funding must never increase when paying profits."
                            )
                    
                    # Decide transaction sign BEFORE balance update
                    if client_pnl_before > 0:
                        # PROFIT CASE: YOU pay client → amount is NEGATIVE (your loss)
                        transaction_amount = -paid_amount
                    elif client_pnl_before < 0:
                        # LOSS CASE: Client pays YOU → amount is POSITIVE (your profit)
                        transaction_amount = paid_amount
                    else:
                        transaction_amount = 0
                    
                    # 6. Save SETTLEMENT_SHARE transaction (BEFORE balance update)
                    # Validate that funding/exchange_balance won't go negative
                    if client_pnl_before < 0:
                        # LOSS CASE: Masked capital reduces Funding
                        if account.funding - int(masked_capital) < 0:
                            raise ValidationError(
                                f"Cannot record payment. Funding would become negative "
                                f"(Current: {account.funding}, Masked Capital: {int(masked_capital)})."
                            )
                        funding_after_settlement = account.funding - int(masked_capital)
                        exchange_after_settlement = account.exchange_balance  # Unchanged
                    else:
                        # PROFIT CASE: Masked capital reduces Exchange Balance
                        if account.exchange_balance - int(masked_capital) < 0:
                            raise ValidationError(
                                f"Cannot record payment. Exchange balance would become negative "
                                f"(Current: {account.exchange_balance}, Masked Capital: {int(masked_capital)})."
                            )
                        funding_after_settlement = account.funding  # Unchanged (CRITICAL RULE)
                        exchange_after_settlement = account.exchange_balance - int(masked_capital)
                    
                    # 7. Update balances
                    account.funding = funding_after_settlement
                    account.exchange_balance = exchange_after_settlement
                    account.save()
                    
                    # Create Settlement record
                    settlement = Settlement.objects.create(
                        client_exchange=account,
                        amount=paid_amount,
                        date=payment_date,
                        notes=notes or f"Payment recorded: {paid_amount}"
                    )
                    
                    # Create RECORD_PAYMENT transaction with before/after balances
                    # CORE RULE: This transaction type is used for profit/loss reporting
                    # +X = Client paid YOU (Client loss settlement) → Your PROFIT
                    # -X = YOU paid client (Client profit settlement) → Your LOSS
                    Transaction.objects.create(
                        client_exchange=account,
                        date=payment_date,
                        type='RECORD_PAYMENT',
                        amount=transaction_amount,
                        funding_before=funding_before,
                        funding_after=funding_after_settlement,
                        exchange_balance_before=exchange_before,
                        exchange_balance_after=exchange_after_settlement,
                        notes=notes or f"Settlement share payment: {paid_amount}. Masked Capital: {int(masked_capital)}"
                    )
                    
                    # 8. IF auto-refund enabled: Save FUNDING_AUTO transaction
                    cycle_closed = False
                    if re_add_capital and client_pnl_before < 0:
                        # Auto re-funding: Funding = Funding + MaskedCapital
                        # ExchangeBalance = ExchangeBalance + MaskedCapital
                        funding_before_refund = account.funding
                        exchange_before_refund = account.exchange_balance
                        
                        account.funding += int(masked_capital)
                        account.exchange_balance += int(masked_capital)
                        account.save()
                        
                        # Create separate FUNDING_AUTO transaction
                        Transaction.objects.create(
                            client_exchange=account,
                            date=payment_date,
                            type='FUNDING_AUTO',
                            amount=int(masked_capital),
                            funding_before=funding_before_refund,
                            funding_after=account.funding,
                            exchange_balance_before=exchange_before_refund,
                            exchange_balance_after=account.exchange_balance,
                            notes=f"Auto Re-Funding after settlement (linked to Settlement ID: {settlement.id}). "
                                  f"Amount: {int(masked_capital)} (Masked Capital)"
                        )
                        
                        # Re-fund closes old cycle and starts new cycle
                        account.close_cycle()
                        cycle_closed = True
                    
                    # Check if cycle should close (full settlement without re-fund)
                    if not cycle_closed:
                        new_settlement_info = account.get_remaining_settlement_amount()
                        new_remaining = new_settlement_info['remaining']
                        
                        if new_remaining == 0:
                            # Full settlement - close cycle
                            account.close_cycle()
                            cycle_closed = True
                    
                    # Recompute values after payment
                    new_pnl = account.compute_client_pnl()
                    new_settlement_info = account.get_remaining_settlement_amount()
                    new_remaining = new_settlement_info['remaining']
                    
                    from django.contrib import messages
                    success_msg = f"Payment of {paid_amount} recorded successfully."
                    
                    if re_add_capital and client_pnl_before < 0:
                        success_msg += f" Capital re-added: {int(masked_capital)}. New cycle started."
                    elif cycle_closed:
                        success_msg += " Settlement complete. Cycle closed."
                    elif new_remaining > 0:
                        success_msg += f" Remaining settlement amount: {new_remaining}"
                    
                    messages.success(request, success_msg)
                    
                    # Redirect based on redirect_to parameter
                    if redirect_to == 'pending_summary':
                        return redirect(reverse("pending_summary"))
                    return redirect(reverse("exchange_account_detail", args=[account.pk]))
                    
            except ValidationError as e:
                from django.contrib import messages
                messages.error(request, str(e))
                # Calculate display remaining
                display_remaining = calculate_display_remaining(client_pnl, remaining_amount)
                return render(request, "core/exchanges/record_payment.html", {
                    'account': account,
                    'client_pnl': client_pnl,
                    'final_share': final_share,
                    'remaining_amount': remaining_amount,
                    'display_remaining': display_remaining,
                    'today': date.today(),
                })
            
        except ValueError:
            from django.contrib import messages
            messages.error(request, "Invalid amount. Please enter a valid number.")
            # Calculate display remaining
            if client_pnl > 0:
                display_remaining = -remaining_amount
            else:
                display_remaining = remaining_amount
            return render(request, "core/exchanges/record_payment.html", {
                'account': account,
                'client_pnl': client_pnl,
                'final_share': final_share,
                'remaining_amount': remaining_amount,
                'display_remaining': display_remaining,
            })
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error recording payment: {str(e)}")
            # Calculate display remaining
            if client_pnl > 0:
                display_remaining = -remaining_amount
            else:
                display_remaining = remaining_amount
            return render(request, "core/exchanges/record_payment.html", {
                'account': account,
                'client_pnl': client_pnl,
                'final_share': final_share,
                'remaining_amount': remaining_amount,
                'display_remaining': display_remaining,
            })
    
    # GET request - show form
    # CORRECTNESS LOGIC: Display remaining with sign based on PnL direction
    # Step 1: Core Remaining (ALWAYS POSITIVE) - Raw value from get_remaining_settlement_amount()
    core_remaining = remaining_amount
    # Step 2: Display Sign (BASED ON Client_PnL direction)
    # Formula: DisplayRemaining = sign(Client_PnL) × RemainingRaw
    # IF Client_PnL < 0 (LOSS): DisplayRemaining = +RemainingRaw (client owes you)
    # IF Client_PnL > 0 (PROFIT): DisplayRemaining = -RemainingRaw (you owe client)
    if client_pnl > 0:
        display_remaining = -core_remaining  # You owe client (negative)
    else:
        display_remaining = core_remaining  # Client owes you (positive)
    
    return render(request, "core/exchanges/record_payment.html", {
        'account': account,
        'client_pnl': client_pnl,
        'final_share': final_share,
        'remaining_amount': remaining_amount,  # Keep positive for max validation
        'display_remaining': display_remaining,  # Signed for display
        'today': date.today(),
    })


@login_required


def report_time_travel(request):


    """Time travel report view."""
    date_str = request.GET.get('date', '')
    # TODO: Add time travel report calculation logic here
    context = {
        'date': date_str,
    }
    return render(request, "core/reports/time_travel.html", context)


@login_required


def report_exchange(request, exchange_pk):


    """Report for a specific exchange with graphs and analysis."""
    from datetime import timedelta
    
    exchange = get_object_or_404(Exchange, pk=exchange_pk)
    today = date.today()
    report_type = request.GET.get("report_type", "weekly")  # daily, weekly, monthly
    
    # Calculate date range based on report type
    if report_type == "daily":

        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    elif report_type == "weekly":
        # Weekly: from last same weekday to this same weekday (7 days)
        start_date = today - timedelta(days=7)
        end_date = today
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        today_weekday = today.weekday()
        date_range_label = f"Weekly ({weekday_names[today_weekday]} to {weekday_names[today_weekday]}): {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    elif report_type == "monthly":
        day_of_month = today.day
        if today.month == 1:
            pass
        else:
            last_month = today.month - 1
            last_month_days = (date(today.year, today.month, 1) - timedelta(days=1)).day
            start_date = date(today.year, last_month, min(day_of_month, last_month_days))
        
        end_date = today
        date_range_label = f"Monthly ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')})"
    else:
        # Default to daily
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    
    # Get date parameter for custom date range (optional override)
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        date_range_label = f"Custom: {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    
    qs = Transaction.objects.filter(
        client_exchange__client__user=request.user,
        client_exchange__exchange=exchange, 
        date__gte=start_date, 
        date__lte=end_date
    )
    
    # CORRECTNESS LOGIC: Turnover = Σ(|ExchangeBalanceAfter − ExchangeBalanceBefore|) for TRADE transactions only
    # Turnover measures trading activity, NOT funding or settlements
    trade_qs = qs.filter(type='TRADE').exclude(
        exchange_balance_before__isnull=True
    ).exclude(
        exchange_balance_after__isnull=True
    )
    # Calculate turnover as sum of absolute exchange balance movements from trades
    total_turnover = sum(
        abs(tx.exchange_balance_after - tx.exchange_balance_before)
        for tx in trade_qs
    ) or 0
    
    # Your Total Profit = Sum(RECORD_PAYMENT.amount) - signed sum
    payment_qs = qs.filter(type='RECORD_PAYMENT')
    your_total_profit = payment_qs.aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Income from clients = Sum of positive amounts
    your_profit = payment_qs.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Loss (paid to clients) = Absolute value of negative amounts
    your_loss = abs(payment_qs.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0))
    
    company_profit = Decimal(0)
    
    transactions = qs.select_related(
        "client_exchange", 
        "client_exchange__client", 
        "client_exchange__exchange"
    ).order_by("-date", "-created_at")
    
    # Transaction type breakdown
    type_data = qs.values("type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        'FUNDING': ("Funding", "#4b5563"),
        'TRADE': ("Trade", "#6b7280"),
        'FEE': ("Fee", "#9ca3af"),
        'ADJUSTMENT': ("Adjustment", "#6b7280"),
        'RECORD_PAYMENT': ("Record Payment", "#10b981"),
    }
    for item in type_data:
        tx_type = item["type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)

    
    # Client-wise breakdown
    # Profit from RECORD_PAYMENT transactions
    client_payment_data = payment_qs.values("client_exchange__client__name").annotate(
        profit=Sum("amount", filter=Q(amount__gt=0))
    )
    
    # Turnover from TRADE transactions (exchange balance movement) per client
    client_trade_qs = trade_qs.values("client_exchange__client__name")
    client_turnover_map = {}
    for client_name in client_trade_qs.values_list("client_exchange__client__name", flat=True).distinct():
        client_trades = trade_qs.filter(client_exchange__client__name=client_name)
        client_turnover = sum(
            abs(tx.exchange_balance_after - tx.exchange_balance_before)
            for tx in client_trades
        ) or 0
        client_turnover_map[client_name] = client_turnover
    
    # Combine profit and turnover data
    client_data = []
    for item in client_payment_data:
        client_name = item["client_exchange__client__name"]
        client_data.append({
            "client_exchange__client__name": client_name,
            "profit": item["profit"] or 0,
            "turnover": client_turnover_map.get(client_name, 0)
        })
    
    # Sort by profit and limit to top 10
    client_data = sorted(client_data, key=lambda x: x["profit"] or 0, reverse=True)[:10]
    
    client_labels = [item["client_exchange__client__name"] for item in client_data]
    client_profits = [float(item["profit"] or 0) for item in client_data]
    
    # Analysis
    net_profit = float(your_total_profit)  # Net profit = signed sum
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    
    # Check if we have data for charts
    has_type_data = len(type_labels) > 0
    has_client_data = len(client_labels) > 0
    
    context = {
        "exchange": exchange,
        "start_date": start_date_str if start_date_str else start_date.strftime('%Y-%m-%d'),
        "end_date": end_date_str if end_date_str else end_date.strftime('%Y-%m-%d'),
        "report_type": report_type,
        "date_range_label": date_range_label,
        "total_turnover": total_turnover,
        "your_total_profit": your_total_profit,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "company_profit": company_profit,
        "transactions": transactions,
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
        "has_type_data": has_type_data,
        "has_client_data": has_client_data,
    }
    return render(request, "core/reports/exchange.html", context)


# Settings View
@login_required


def settings_view(request):


    """System settings page for configuring weekly reports and other options."""
    # TODO: SystemSettings model removed - add back if needed
    settings = None  # Placeholder
    
    if request.method == "POST":

        settings.auto_generate_weekly_reports = request.POST.get("auto_generate_weekly_reports") == "on"
        
        settings.save()
        return redirect(reverse("settings"))
    
    return render(request, "core/settings.html", {"settings": settings})


# Balance Tracking
@login_required


def client_balance(request, client_pk):


    """Show balance summary for a specific client."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    
    # Handle daily balance recording/editing
    if request.method == "POST" and request.POST.get("action") == "record_balance":

        client_exchange_id = request.POST.get("client_exchange")
        balance_date = request.POST.get("balance_date")
        remaining_balance = Decimal(request.POST.get("remaining_balance", 0))
        extra_adjustment = Decimal(request.POST.get("extra_adjustment", 0) or 0)
        note = request.POST.get("note", "")
        balance_id = request.POST.get("balance_id")
        
        if balance_date and client_exchange_id and remaining_balance >= 0:
            client_exchange = get_object_or_404(ClientExchangeAccount, pk=client_exchange_id, client=client)

            
            if balance_id:
                # Edit existing balance
                balance = get_object_or_404(ClientDailyBalance, pk=balance_id, client_exchange__client=client)

                balance_record_date_obj = date.fromisoformat(balance_date)

                
                # Get old balance based on client type
                # All clients are now my clients
                    # My Clients: Old Balance = balance after last settlement
                    # For BOTH MY CLIENTS and COMPANY CLIENTS: Use the same logic
                    # Old Balance = SUM of FUNDING (or balance after settlement + funding after)
                    # NEVER use BALANCE_RECORD for Old Balance
                    
                
                balance.date = balance_record_date_obj

                balance.client_exchange = client_exchange

                balance.remaining_balance = remaining_balance

                balance.extra_adjustment = extra_adjustment

                balance.note = note

                balance.save()

                
                # Calculate new balance
                new_balance = remaining_balance + extra_adjustment

                
                # Always create a new transaction for this balance record update
                # Each update creates a separate transaction entry (no updates to existing transactions)
                from datetime import datetime

                balance_note = note or f"Balance Record: ₹{remaining_balance}"

                if extra_adjustment:
                    balance_note += f" + Adjustment: ₹{extra_adjustment}"

                balance_note += f" (Updated at {datetime.now().strftime('%H:%M:%S')})"

                # Create ADJUSTMENT transaction with before/after balances
                funding_before = client_exchange.funding
                exchange_before = old_balance
                
                Transaction.objects.create(
                    client_exchange=client_exchange,
                    date=balance_record_date_obj,
                    type='ADJUSTMENT',  # Balance updates are adjustments
                    amount=new_balance,
                    funding_before=funding_before,
                    funding_after=client_exchange.funding,  # Unchanged
                    exchange_balance_before=exchange_before,
                    exchange_balance_after=new_balance,
                    notes=balance_note,
                )

                
                # Create LOSS or PROFIT transactions based on balance movement
                # This will automatically create the appropriate transaction and update tally/outstanding
                create_loss_profit_from_balance_change(

                    client_exchange, 

                    old_balance, 

                    new_balance, 

                    balance_record_date_obj,

                    note_suffix=" Updated"

                )

                
                # Update tally/outstanding if balance changed
                if new_balance != old_balance:
                        # My Clients: Use outstanding (netted system) with new logic
                        update_outstanding_from_balance_change(

                            client_exchange, 

                            old_balance, 

                            new_balance, 

                            balance_date=balance_record_date_obj

                        )
            else:
                # Create new balance
                balance_record_date_obj = date.fromisoformat(balance_date)
                
                # Get old balance
                # Old Balance = SUM of FUNDING (or balance after settlement + funding after)
                # NEVER use BALANCE_RECORD for Old Balance
                
                new_balance = remaining_balance + extra_adjustment

                # TODO: ClientDailyBalance model removed - add back if needed
                balance, created = None, False  # ClientDailyBalance.objects.update_or_create(
                #     client_exchange=client_exchange,
                #     date=balance_record_date_obj,
                #     defaults={
                #         "remaining_balance": remaining_balance,
                #         "extra_adjustment": extra_adjustment,
                #         "note": note,
                #     }
                # )
                
                # Always create a new transaction for this balance record
                # Each recording creates a separate transaction entry (no updates to existing transactions)
                from datetime import datetime
                
                balance_note = note or f"Balance Record: ₹{remaining_balance}"
                
                if extra_adjustment:
                    balance_note += f" (Extra: ₹{extra_adjustment})"
                
                balance_note += f" (Recorded at {datetime.now().strftime('%H:%M:%S')})"
                
                # Create ADJUSTMENT transaction with before/after balances
                funding_before = client_exchange.funding
                exchange_before = old_balance
                
                Transaction.objects.create(
                    client_exchange=client_exchange,
                    date=balance_record_date_obj,
                    type='ADJUSTMENT',
                    amount=new_balance,
                    funding_before=funding_before,
                    funding_after=client_exchange.funding,  # Unchanged
                    exchange_balance_before=exchange_before,
                    exchange_balance_after=new_balance,
                    notes=balance_note,
                )
                
                # Note: create_loss_profit_from_balance_change is deprecated in PIN-TO-PIN
                # Profit/loss is computed from accounts, not transactions
                
                # Update exchange balance if balance changed
                if new_balance != old_balance:
                    client_exchange.exchange_balance = new_balance
                    client_exchange.save()
        
        # Redirect to client detail
    from django.shortcuts import redirect
    from django.urls import reverse
    return redirect("client_detail", pk=client.pk)

    
    # Check if editing a balance
    edit_balance_id = request.GET.get("edit_balance")
    edit_balance = None
    if edit_balance_id:
        try:
            # ClientDailyBalance model removed in PIN-TO-PIN
            edit_balance = None
        except Exception:
            pass


    
    # Get filter for exchange
    selected_exchange_id = request.GET.get("exchange")
    selected_exchange = None
    if selected_exchange_id:
        try:
            selected_exchange = ClientExchangeAccount.objects.get(pk=selected_exchange_id, client=client)
        except ClientExchangeAccount.DoesNotExist:
            pass


    
    # Calculate balances per client-exchange
    client_exchanges = client.exchange_accounts.select_related("exchange").all()
    
    # Filter by selected exchange if provided
    if selected_exchange:

    
        pass
    # Get system settings for calculations
    # TODO: SystemSettings model removed - add back if needed
    settings = None  # Placeholder
    
    exchange_balances = []
    
    for client_exchange in client_exchanges:

        
        # Transactions are audit-only - use account balances instead
        # Calculate from account directly
        total_funding = client_exchange.funding
        # Turnover from TRADE transactions (exchange balance movement)
        account_trades = transactions.filter(type='TRADE').exclude(
            exchange_balance_before__isnull=True
        ).exclude(
            exchange_balance_after__isnull=True
        )
        total_turnover = sum(
            abs(tx.exchange_balance_after - tx.exchange_balance_before)
            for tx in account_trades
        ) or 0
        
        # Profit/loss calculated from account balances
        client_pnl = client_exchange.compute_client_pnl()
        if client_pnl > 0:
            total_profit = client_pnl
            total_loss = 0
        else:
            total_profit = 0
            total_loss = abs(client_pnl)
        
        client_net = client_exchange.exchange_balance
        you_net = client_exchange.compute_my_share() if client_pnl < 0 else -client_exchange.compute_my_share()
        
        # TODO: ClientDailyBalance model removed - add back if needed
        # Get daily balance records for this exchange
        daily_balances = []  # ClientDailyBalance.objects.filter(
        #     client_exchange=client_exchange
        # ).order_by("-date")[:10]  # Last 10 records per exchange
        
        # Get latest daily balance record (most recent)
        latest_balance_record = None  # ClientDailyBalance.objects.filter(
        #     client_exchange=client_exchange
        # ).order_by("-date").first()
        
        # Calculate profit/loss using new logic
        profit_loss_data = calculate_client_profit_loss(client_exchange)
        
        # Use client-specific my_share_pct from ClientExchangeAccount configuration
        # This is the percentage configured on the client detail page
        admin_profit_share_pct = client_exchange.my_share_pct
        
        # Calculate admin profit/loss - pass client_exchange for correct company share calculation
        admin_data = calculate_admin_profit_loss(profit_loss_data["client_profit_loss"], settings, admin_profit_share_pct, client_exchange)
        
        # Total balance in exchange account (recorded + extra adjustment)
        if latest_balance_record:


            pass
        else:

            total_balance_in_exchange = client_net


        
        # Calculate pending from account using proper settlement system
        settlement_info = client_exchange.get_remaining_settlement_amount()
        if client_pnl > 0:
            pending_you_owe = settlement_info['remaining']
        else:
            pending_you_owe = Decimal(0)
        
        # 🔹 Calculate Your Net Profit from this Client (till now)
        # Formula: (Current Balance - Old Balance) × My Share %
        # This is YOUR money (plus or minus) from this client
        
        current_balance = total_balance_in_exchange
        net_change = current_balance - old_balance
        my_share_pct = client_exchange.my_share_pct
        your_net_profit_raw = (net_change * my_share_pct) / Decimal(100)
        your_net_profit = round_share(your_net_profit_raw)  # Share-space: round DOWN
        
        exchange_balances.append({
            "client_exchange": client_exchange,

            "exchange": client_exchange.exchange,

            "total_funding": total_funding,

            "total_profit": total_profit,

            "total_loss": total_loss,

            "total_turnover": total_turnover,

            "client_net": client_net,

            "you_net": you_net,

            # Pending amounts removed - no longer using PendingAmount model
            "pending_client_owes": Decimal(0),

            # You owe client = client profit share minus settlements where admin paid
            "pending_you_owe": pending_you_owe,

            "daily_balances": daily_balances,

            "latest_balance_record": latest_balance_record,

            "total_balance_in_exchange": total_balance_in_exchange,

            # New profit/loss calculations
            "client_profit_loss": profit_loss_data["client_profit_loss"],

            "is_profit": profit_loss_data["is_profit"],

            "admin_profit": admin_data["admin_profit"],

            "admin_loss": admin_data["admin_loss"],

            "company_share_profit": admin_data["company_share_profit"],

            "company_share_loss": admin_data["company_share_loss"],

            "admin_net": admin_data["admin_net"],

            "admin_bears": admin_data.get("admin_bears", Decimal(0)),

            "admin_profit_share_pct_used": admin_data.get("admin_profit_share_pct_used", settings.admin_profit_share_pct),

            "admin_earns": admin_data.get("admin_earns", Decimal(0)),

            "admin_pays": admin_data.get("admin_pays", Decimal(0)),

            "company_earns": admin_data.get("company_earns", Decimal(0)),

            "company_pays": admin_data.get("company_pays", Decimal(0)),

            "company_share_pct": client_exchange.company_share_pct if False else Decimal(0),

            "my_share_pct": client_exchange.my_share_pct,

            "your_net_profit": your_net_profit,  # Your Net Profit from this Client (till now)

            "old_balance": old_balance,  # For reference/debugging

            "current_balance": current_balance,  # For reference/debugging

        })
    
    # TODO: ClientDailyBalance model removed - add back if needed
    # Get all daily balances for the client (for summary view)
    daily_balance_qs = []  # ClientDailyBalance.objects.filter(
    #     client_exchange__client=client
    # ).select_related("client_exchange", "client_exchange__exchange")
    
    # Filter daily balances by selected exchange if provided
    # if selected_exchange:
    #     daily_balance_qs = daily_balance_qs.filter(client_exchange=selected_exchange)
    
    all_daily_balances = []  # daily_balance_qs.order_by("-date")[:30]
    
    # Get all transactions for the selected exchange (or all exchanges if none selected)
    if selected_exchange:
        all_transactions = Transaction.objects.filter(
            client_exchange=selected_exchange
        ).select_related("client_exchange", "client_exchange__exchange").order_by("-date", "-created_at")
    else:
        all_transactions = Transaction.objects.filter(
            client_exchange__client=client

        ).select_related("client_exchange", "client_exchange__exchange").order_by("-date", "-created_at")
    
    # Annotate transactions with recorded balances for their dates
    transactions_with_balances = []
    for tx in all_transactions:
        if tx.type == 'ADJUSTMENT':  # Balance records are now ADJUSTMENT type
            class MockBalance:
                def __init__(self, amount):
                    self.remaining_balance = amount
                    self.extra_adjustment = Decimal(0)
            
            tx.recorded_balance = MockBalance(tx.amount)
        else:
            # TODO: ClientDailyBalance model removed - add back if needed
            # For other transactions, find the balance record created closest to (but before or at) this transaction's time
            # First, try to find balance records on the same date, created before or at this transaction's time
            recorded_balance = None  # ClientDailyBalance.objects.filter(
    #     client_exchange=tx.client_exchange,
    #     date=tx.date,
    #     created_at__lte=tx.created_at
    # ).order_by('-created_at').first()
            
            # If no balance on same date before this transaction, get the most recent balance before this date
            if not recorded_balance:
                # ClientDailyBalance model removed - use exchange_balance from account
                recorded_balance = None
            
            # If still no balance record found, calculate from transactions
            if not recorded_balance:
                # Calculate balance from transactions up to this point
                balance_amount = get_exchange_balance(tx.client_exchange, as_of_date=tx.date)

                class MockBalance:

                    def __init__(self, amount):

                        self.remaining_balance = amount


                        self.extra_adjustment = Decimal(0)

                tx.recorded_balance = MockBalance(balance_amount)

                tx.recorded_balance = recorded_balance

        
        transactions_with_balances.append(tx)
    
    all_transactions = transactions_with_balances
    
    # Calculate total balance across all exchanges (or selected exchange)
    total_balance_all_exchanges = Decimal(0)
    for bal in exchange_balances:
        total_balance_all_exchanges += bal.get('balance', 0)
    
    # Get all client exchanges for the dropdown (not filtered)
    all_client_exchanges = client.exchange_accounts.select_related("exchange").all()
    
    # Get selected exchange name for display
    selected_exchange_name = None
    if selected_exchange and exchange_balances:

    
        pass
    # Determine client type for URL namespace
    client_type = "company" if False else "my"
    
    context = {
        "client": client,
        "exchange_balances": exchange_balances,
        "all_daily_balances": all_daily_balances,
        "total_balance_all_exchanges": total_balance_all_exchanges,
        "today": date.today(),
        "edit_balance": edit_balance,
        "edit_balance_id": edit_balance_id,
        "client_exchanges": client_exchanges,  # Filtered exchanges for display
        "all_client_exchanges": all_client_exchanges,  # All exchanges for dropdown
        "selected_exchange_id": int(selected_exchange_id) if selected_exchange_id else None,
        "selected_exchange_name": selected_exchange_name,
        "settings": settings,
        "client_type": client_type,
        "all_transactions": all_transactions,
    }
    return render(request, "core/clients/balance.html", context)


@login_required
def build_apk(request):
    """Build APK using Gradle and copy to static directory."""
    import os
    import subprocess
    import shutil
    from django.http import JsonResponse
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.conf import settings
    from django.urls import reverse

    try:
        # Paths
        base_dir = settings.BASE_DIR
        android_app_dir = os.path.join(base_dir, 'android_app')
        gradle_wrapper = os.path.join(android_app_dir, 'gradlew')
        apk_source = os.path.join(android_app_dir, 'app', 'build', 'outputs', 'apk', 'debug', 'app-debug.apk')
        apk_dest_dir = os.path.join(base_dir, 'static', 'apk')
        apk_dest = os.path.join(apk_dest_dir, 'app-debug.apk')

        # Check if Android app directory exists
        if not os.path.exists(android_app_dir):
            messages.error(request, "Android app directory not found. Expected at: " + android_app_dir)
            return redirect(reverse('dashboard'))

        # Make gradlew executable
        if os.path.exists(gradle_wrapper):
            os.chmod(gradle_wrapper, 0o755)

        # Build APK using Gradle
        build_command = ['./gradlew', 'assembleDebug'] if os.path.exists(gradle_wrapper) else ['gradle', 'assembleDebug']
        
        messages.info(request, "Building APK... This may take 1-2 minutes.")
        
        process = subprocess.Popen(
            build_command,
            cwd=android_app_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout
        
        if process.returncode != 0:
            error_msg = stderr or stdout or "Build failed with unknown error"
            messages.error(request, f"APK build failed: {error_msg[:200]}")
            return redirect(reverse('dashboard'))

        # Check if APK was created
        if not os.path.exists(apk_source):
            messages.error(request, "APK build completed but file not found at: " + apk_source)
            return redirect(reverse('dashboard'))

        # Ensure destination directory exists
        os.makedirs(apk_dest_dir, exist_ok=True)

        # Copy APK to static directory
        shutil.copy2(apk_source, apk_dest)
        
        file_size = os.path.getsize(apk_dest) / (1024 * 1024)  # Size in MB
        messages.success(request, f"APK built successfully! File size: {file_size:.2f} MB")
        
        return redirect(reverse('download_apk'))
        
    except subprocess.TimeoutExpired:
        messages.error(request, "APK build timed out. Please build manually using Android Studio.")
        return redirect(reverse('dashboard'))
    except FileNotFoundError:
        messages.error(request, "Gradle not found. Please install Android Studio or Gradle.")
        return redirect(reverse('dashboard'))
    except Exception as e:
        messages.error(request, f"Error building APK: {str(e)}")
        return redirect(reverse('dashboard'))


def download_apk(request):
    """Serve APK file for download."""
    import os
    from django.http import HttpResponse, Http404
    from django.conf import settings

    # Path to the APK file
    apk_path = os.path.join(settings.BASE_DIR, 'static', 'apk', 'app-debug.apk')

    # Check if file exists
    if not os.path.exists(apk_path):
        from django.contrib import messages
        from django.shortcuts import redirect
        from django.urls import reverse
        messages.warning(request, "APK file not found. Please build the APK first.")
        return redirect(reverse('dashboard'))

    # Open and serve the file
    with open(apk_path, 'rb') as apk_file:
        response = HttpResponse(apk_file.read(), content_type='application/vnd.android.package-archive')
        response['Content-Disposition'] = 'attachment; filename="chip_trading_app.apk"'
        return response


@login_required
@login_required
def logs_dashboard(request):
    """Logs dashboard to view application logs and debug errors."""
    # Restrict access to only user 'muktesh' - admin and all other users are blocked
    if request.user.username != 'muktesh':
        return HttpResponseForbidden("You don't have permission to access this page.")
    
    from django.contrib import messages
    import re
    
    def simplify_log_message(message, source):
        """Simplifies raw log messages into common English."""
        msg = message.strip()
        
        if source == 'Django':
            # Security/Auth logs
            if 'Invalid password for user' in msg:
                user_match = re.search(r'user (.*)', msg)
                username = user_match.group(1) if user_match else "someone"
                return f"Failed login attempt for user '{username}' (Wrong password)"
            if 'Login success for user' in msg:
                user_match = re.search(r'user (.*)', msg)
                username = user_match.group(1) if user_match else "someone"
                return f"User '{username}' logged in successfully"
            if 'Logout success for user' in msg:
                user_match = re.search(r'user (.*)', msg)
                username = user_match.group(1) if user_match else "someone"
                return f"User '{username}' logged out"
        
        elif source == 'Gunicorn':
            # Server/Request logs
            if 'GET /' in msg:
                path_match = re.search(r'GET ([^ ]*)', msg)
                path = path_match.group(1) if path_match else "/"
                status_match = re.search(r'HTTP/1.1" (\d+)', msg)
                status = status_match.group(1) if status_match else ""
                if status == '200':
                    return f"Someone viewed page: {path}"
                elif status == '404':
                    return f"Page not found: {path}"
                elif status == '500':
                    return f"System error on page: {path}"
            if 'POST /' in msg:
                path_match = re.search(r'POST ([^ ]*)', msg)
                path = path_match.group(1) if path_match else "/"
                return f"Form submitted on page: {path}"
            if 'Worker exiting' in msg:
                return "Server worker is restarting"
            if 'Booting worker' in msg:
                return "Server worker started"
        
        elif source == 'Nginx':
            # Web server errors
            if 'directory index of' in msg and 'is forbidden' in msg:
                return "Blocked attempt to list folder files"
            if 'client intended to send too large body' in msg:
                return "File upload too large"
            if 'upstream timed out' in msg:
                return "System took too long to respond (Timeout)"
            if 'no such file or directory' in msg:
                file_match = re.search(r'open\(\) "(.*)" failed', msg)
                filename = file_match.group(1).split('/')[-1] if file_match else "file"
                return f"Missing file: {filename}"
        
        elif source == 'Mobile App':
            # Mobile app specific
            if 'Sync started' in msg:
                return "Mobile app started syncing data"
            if 'Sync completed' in msg:
                return "Mobile app finished syncing data"
            if 'Network error' in msg:
                return "Mobile app had a connection problem"
            if 'User clicked' in msg:
                btn_match = re.search(r'clicked (.*)', msg)
                btn = btn_match.group(1) if btn_match else "button"
                return f"User tapped on '{btn}'"

        # If no simplification rule matches, return original or cleaned up message
        return msg[:200] + '...' if len(msg) > 200 else msg

    # Handle clear logs POST request
    if request.method == 'POST' and 'clear_logs' in request.POST:
        cleared_sources = []
        
        # Clear Django security log
        security_log_path = Path(settings.BASE_DIR) / 'security.log'
        if security_log_path.exists():
            try:
                with open(security_log_path, 'w') as f:
                    f.write('')  # Clear the file
                cleared_sources.append('Django Security Log')
            except Exception as e:
                messages.error(request, f'Error clearing Django log: {str(e)}')
        
        # Clear Mobile App logs from database
        try:
            deleted_count = MobileLog.objects.all().delete()[0]
            if deleted_count > 0:
                cleared_sources.append(f'Mobile App Logs ({deleted_count} entries)')
        except Exception as e:
            messages.error(request, f'Error clearing mobile logs: {str(e)}')
        
        # Note: Gunicorn logs are in journalctl and require system-level access
        # We can't easily clear them from Django, but we can note it
        
        # Clear Nginx error logs if accessible
        nginx_error_log_paths = [
            '/var/log/nginx/error.log',
            '/etc/nginx/logs/error.log',
        ]
        for nginx_path in nginx_error_log_paths:
            if os.path.exists(nginx_path) and os.access(nginx_path, os.W_OK):
                try:
                    with open(nginx_path, 'w') as f:
                        f.write('')  # Clear the file
                    cleared_sources.append('Nginx Error Log')
                    break
                except Exception as e:
                    pass  # Silently fail if we can't write
        
        if cleared_sources:
            success_msg = f'Successfully cleared: {", ".join(cleared_sources)}'
            # Note about Gunicorn logs
            if 'Gunicorn' not in ', '.join(cleared_sources):
                success_msg += '\n\nNote: Gunicorn logs are managed by systemd (journalctl) and cannot be cleared from here. To clear Gunicorn logs, use: sudo journalctl --vacuum-time=1d'
            messages.success(request, success_msg)
        else:
            messages.warning(request, 'No logs were cleared. Log files may not be accessible or writable.')
        
        # Redirect to logs dashboard to show updated (empty) logs
        return redirect('logs_dashboard')
    
    log_sources = []
    errors_count = 0
    warnings_count = 0
    
    # Get filter parameters
    log_type = request.GET.get('type', 'all')  # django, gunicorn, nginx, mobile, all
    log_level = request.GET.get('level', 'all')  # error, warning, info, all
    search_query = request.GET.get('search', '').strip()
    lines_limit = int(request.GET.get('lines', 1000))  # Increased default to 1000
    
    # 1. Django Security & App Logs
    django_logs = []
    security_log_path = Path(settings.BASE_DIR) / 'security.log'
    if security_log_path.exists():
        try:
            with open(security_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # Get last N lines
                recent_lines = lines[-lines_limit:] if len(lines) > lines_limit else lines
                
                for line in recent_lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    log_entry = {
                        'source': 'Django',
                        'timestamp': '',
                        'level': 'INFO',
                        'message': line,
                        'simple_message': simplify_log_message(line, 'Django'),
                        'raw': line
                    }
                    
                    # Try to parse log format: LEVELNAME YYYY-MM-DD HH:MM:SS,mmm module message
                    parts = line.split(' ', 3)
                    if len(parts) >= 4:
                        try:
                            log_entry['level'] = parts[0]
                            log_entry['timestamp'] = f"{parts[1]} {parts[2]}"
                            log_entry['message'] = parts[3] if len(parts) > 3 else line
                            log_entry['simple_message'] = simplify_log_message(log_entry['message'], 'Django')
                        except:
                            pass
                    
                    # Count errors and warnings
                    if 'ERROR' in line.upper() or '500 ERROR' in line.upper() or 'CRITICAL' in line.upper():
                        log_entry['level'] = 'ERROR'
                        errors_count += 1
                    elif 'WARNING' in line.upper() or 'WARN' in line.upper():
                        log_entry['level'] = 'WARNING'
                        warnings_count += 1
                    
                    # Apply filters
                    if log_type not in ['all', 'django']:
                        continue
                    if log_level != 'all' and log_level.upper() not in log_entry['level']:
                        continue
                    if search_query and search_query.lower() not in line.lower():
                        continue
                    
                    django_logs.append(log_entry)
        except Exception as e:
            django_logs.append({
                'source': 'Django',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'ERROR',
                'message': f'Error reading Django log: {str(e)}',
                'simple_message': f'Error reading Django log: {str(e)}',
                'raw': f'Error reading Django log: {str(e)}'
            })
    
    log_sources.append({
        'name': 'Django App & Security Logs',
        'type': 'django',
        'logs': django_logs,
        'count': len(django_logs)
    })
    
    # 2. Gunicorn Logs (via journalctl - checks multiple services)
    gunicorn_logs = []
    if os.path.exists('/usr/bin/journalctl') or os.path.exists('/bin/journalctl'):
        # List of possible Gunicorn services to check
        services = ['chip-broker.service', 'broker_portal.service']
        
        for service in services:
            try:
                # Try to get Gunicorn logs from systemd journal
                result = subprocess.run(
                    ['journalctl', '-u', service, '-n', str(lines_limit), '--no-pager'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    errors='ignore'
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    lines = result.stdout.split('\n')
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        log_entry = {
                            'source': 'Gunicorn',
                            'timestamp': '',
                            'level': 'INFO',
                            'message': line,
                            'simple_message': simplify_log_message(line, 'Gunicorn'),
                            'raw': line
                        }
                        
                        # Parse journalctl format: MMM DD HH:MM:SS hostname service[pid]: message
                        parts = line.split(' ', 5)
                        if len(parts) >= 6:
                            try:
                                log_entry['timestamp'] = ' '.join(parts[:3])
                                log_entry['message'] = parts[5] if len(parts) > 5 else line
                                log_entry['simple_message'] = simplify_log_message(log_entry['message'], 'Gunicorn')
                            except:
                                pass
                        
                        # Detect error/warning levels
                        if 'ERROR' in line.upper() or '500 ERROR' in line.upper() or 'Traceback' in line:
                            log_entry['level'] = 'ERROR'
                            errors_count += 1
                        elif 'WARNING' in line.upper() or 'WARN' in line.upper():
                            log_entry['level'] = 'WARNING'
                            warnings_count += 1
                        
                        # Apply filters
                        if log_type not in ['all', 'gunicorn']:
                            continue
                        if log_level != 'all' and log_level.upper() not in log_entry['level']:
                            continue
                        if search_query and search_query.lower() not in line.lower():
                            continue
                        
                        gunicorn_logs.append(log_entry)
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
                # journalctl not available or service not found
                pass
            except Exception as e:
                gunicorn_logs.append({
                    'source': 'Gunicorn',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'level': 'ERROR',
                    'message': f'Error reading Gunicorn logs ({service}): {str(e)}',
                    'simple_message': f'Error reading Gunicorn logs ({service}): {str(e)}',
                    'raw': f'Error reading Gunicorn logs ({service}): {str(e)}'
                })
    
    log_sources.append({
        'name': 'Gunicorn Service Logs',
        'type': 'gunicorn',
        'logs': gunicorn_logs,
        'count': len(gunicorn_logs)
    })
    
    # 3. Nginx Error Logs (if accessible)
    nginx_logs = []
    nginx_error_log_paths = [
        '/var/log/nginx/error.log',
        '/etc/nginx/logs/error.log',
    ]
    
    for nginx_path in nginx_error_log_paths:
        if os.path.exists(nginx_path) and os.access(nginx_path, os.R_OK):
            try:
                with open(nginx_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    recent_lines = lines[-lines_limit:] if len(lines) > lines_limit else lines
                    
                    for line in recent_lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        log_entry = {
                            'source': 'Nginx',
                            'timestamp': '',
                            'level': 'INFO',
                            'message': line,
                            'simple_message': simplify_log_message(line, 'Nginx'),
                            'raw': line
                        }
                        
                        # Parse nginx log format
                        if 'error' in line.lower():
                            log_entry['level'] = 'ERROR'
                            errors_count += 1
                        elif 'warn' in line.lower():
                            log_entry['level'] = 'WARNING'
                            warnings_count += 1
                        
                        # Apply filters
                        if log_type not in ['all', 'nginx']:
                            continue
                        if log_level != 'all' and log_level.upper() not in log_entry['level']:
                            continue
                        if search_query and search_query.lower() not in line.lower():
                            continue
                        
                        nginx_logs.append(log_entry)
                    
                    break  # Only read first accessible log
            except Exception as e:
                pass
    
    log_sources.append({
        'name': 'Nginx Error Logs',
        'type': 'nginx',
        'logs': nginx_logs,
        'count': len(nginx_logs)
    })
    
    # 4. Mobile App Logs (from database)
    mobile_logs = []
    try:
        # Get mobile logs from database (limit to recent entries)
        mobile_logs_qs = MobileLog.objects.all().order_by('-created_at')[:lines_limit]
        
        for log in mobile_logs_qs:
            log_entry = {
                'source': 'Mobile App',
                'timestamp': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'level': log.level,
                'message': f"[{log.tag}] {log.message}" if log.tag else log.message,
                'simple_message': simplify_log_message(log.message, 'Mobile App'),
                'raw': f"[{log.tag}] {log.message}" if log.tag else log.message,
                'user': log.user.username if log.user else 'Unknown',
                'device_info': log.device_info,
                'app_version': log.app_version,
                'stack_trace': log.stack_trace,
            }
            
            # Count errors and warnings
            if log.level in ['ERROR', 'CRITICAL']:
                errors_count += 1
            elif log.level == 'WARNING':
                warnings_count += 1
            
            # Apply filters
            if log_type not in ['all', 'mobile']:
                continue
            if log_level != 'all' and log_level.upper() not in log_entry['level']:
                continue
            if search_query and search_query.lower() not in log_entry['message'].lower():
                continue
            
            mobile_logs.append(log_entry)
    except Exception as e:
        mobile_logs.append({
            'source': 'Mobile App',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': 'ERROR',
            'message': f'Error reading mobile logs: {str(e)}',
            'raw': f'Error reading mobile logs: {str(e)}'
        })
    
    log_sources.append({
        'name': 'Mobile App Logs',
        'type': 'mobile',
        'logs': mobile_logs,
        'count': len(mobile_logs)
    })
    
    # Combine all logs and sort by timestamp (newest first)
    all_logs = []
    for source in log_sources:
        all_logs.extend(source['logs'])
    
    # Sort by timestamp if available, otherwise keep original order
    all_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    context = {
        'log_sources': log_sources,
        'all_logs': all_logs,
        'errors_count': errors_count,
        'warnings_count': warnings_count,
        'total_logs': len(all_logs),
        'log_type': log_type,
        'log_level': log_level,
        'search_query': search_query,
        'lines_limit': lines_limit,
    }
    
    return render(request, 'core/logs/dashboard.html', context)
@login_required
def pending_payments_list(request):
    """List all clients and their pending balances."""
    from .models import Client, PendingPaymentTransaction, ClientExchangeAccount
    from django.db.models import BigIntegerField, F, OuterRef, Subquery, Sum, Value
    from django.db.models.functions import Coalesce

    # Get filter parameter
    balance_filter = request.GET.get('balance', 'all')  # 'all', 'owe_me', 'i_owe'

    # IMPORTANT:
    # Client.pending_balance can be stale if account.pending_balance is updated directly
    # (e.g. "generate pending dues" / recalculation flows).
    # So we compute a live balance per client:
    #   computed = sum(account.pending_balance) + legacy_given - legacy_received
    # where legacy_* are PendingPaymentTransaction rows without client_exchange linkage.
    accounts_pending_subq = (
        ClientExchangeAccount.objects.filter(client=OuterRef("pk"))
        .values("client")
        .annotate(s=Coalesce(Sum("pending_balance"), Value(0)))
        .values("s")
    )
    legacy_given_subq = (
        PendingPaymentTransaction.objects.filter(
            client=OuterRef("pk"), client_exchange__isnull=True, type="GIVEN"
        )
        .values("client")
        .annotate(s=Coalesce(Sum("amount"), Value(0)))
        .values("s")
    )
    legacy_received_subq = (
        PendingPaymentTransaction.objects.filter(
            client=OuterRef("pk"), client_exchange__isnull=True, type="RECEIVED"
        )
        .values("client")
        .annotate(s=Coalesce(Sum("amount"), Value(0)))
        .values("s")
    )

    base_clients = (
        Client.objects.filter(user=request.user)
        .annotate(
            _accounts_pending=Coalesce(
                Subquery(accounts_pending_subq, output_field=BigIntegerField()), Value(0)
            ),
            _legacy_given=Coalesce(
                Subquery(legacy_given_subq, output_field=BigIntegerField()), Value(0)
            ),
            _legacy_received=Coalesce(
                Subquery(legacy_received_subq, output_field=BigIntegerField()), Value(0)
            ),
        )
        .annotate(
            computed_pending_balance=F("_accounts_pending") + F("_legacy_given") - F("_legacy_received")
        )
        .order_by("name")
    )

    clients = base_clients

    # Apply balance filtering
    # Convention:
    # +pending_balance => client needs to pay me
    # -pending_balance => I need to pay client
    if balance_filter == 'owe_me':
        clients = clients.filter(computed_pending_balance__gt=0)
    elif balance_filter == 'i_owe':
        clients = clients.filter(computed_pending_balance__lt=0)

    recent_transactions = (
        PendingPaymentTransaction.objects.filter(client__user=request.user)
        .select_related("client", "client_exchange", "client_exchange__exchange")
        .order_by("-date", "-id")[:20]
    )

    # Calculate totals: receivable = sum(+), payable = abs(sum(-))
    if balance_filter == 'owe_me':
        total_receivable = (
            base_clients.filter(computed_pending_balance__gt=0).aggregate(
                s=Coalesce(Sum("computed_pending_balance"), Value(0))
            )["s"]
            or 0
        )
        total_payable = 0
    elif balance_filter == 'i_owe':
        total_receivable = 0
        total_payable = abs(
            (
                base_clients.filter(computed_pending_balance__lt=0).aggregate(
                    s=Coalesce(Sum("computed_pending_balance"), Value(0))
                )["s"]
                or 0
            )
        )
    else:
        total_receivable = (
            base_clients.filter(computed_pending_balance__gt=0).aggregate(
                s=Coalesce(Sum("computed_pending_balance"), Value(0))
            )["s"]
            or 0
        )
        total_payable = abs(
            (
                base_clients.filter(computed_pending_balance__lt=0).aggregate(
                    s=Coalesce(Sum("computed_pending_balance"), Value(0))
                )["s"]
                or 0
            )
        )

    return render(request, 'core/pending_payments/list.html', {
        'clients': clients,
        'recent_transactions': recent_transactions,
        'total_receivable': total_receivable,
        'total_payable': total_payable,
        'balance_filter': balance_filter,
    })

@login_required
def pending_payment_transactions_list(request):
    """List all pending payment transactions."""
    from .models import PendingPaymentTransaction

    # Get search parameters
    search_name = request.GET.get('name', '').strip()
    search_usercode = request.GET.get('usercode', '').strip()
    search_exchange = request.GET.get('exchange', '').strip()
    search_version = request.GET.get('version', '').strip()

    # Base queryset
    transactions = (
        PendingPaymentTransaction.objects.filter(client__user=request.user)
        .select_related('client', 'client_exchange', 'client_exchange__exchange')
        .prefetch_related('client__exchange_accounts__exchange')
        .order_by('-date', '-id')
    )

    # Apply filters
    if search_name:
        transactions = transactions.filter(client__name__icontains=search_name)

    if search_usercode:
        transactions = transactions.filter(client__code__icontains=search_usercode)

    if search_exchange:
        # Filter transactions where client has exchange accounts with matching exchange name
        client_ids_with_exchange = Client.objects.filter(
            user=request.user,
            exchange_accounts__exchange__name__icontains=search_exchange
        ).values_list('id', flat=True).distinct()
        transactions = transactions.filter(client_id__in=client_ids_with_exchange)

    if search_version:
        # Filter transactions where client has exchange accounts with matching version
        client_ids_with_version = Client.objects.filter(
            user=request.user,
            exchange_accounts__exchange__version_name__icontains=search_version
        ).values_list('id', flat=True).distinct()
        transactions = transactions.filter(client_id__in=client_ids_with_version)

    return render(request, 'core/pending_payments/transactions.html', {
        'transactions': transactions,
        'search_name': search_name,
        'search_usercode': search_usercode,
        'search_exchange': search_exchange,
        'search_version': search_version,
    })

@login_required
def pending_payment_create(request):
    """Add a new GIVEN or RECEIVED transaction."""
    from django.http import Http404
    raise Http404()

    from .models import Client, PendingPaymentTransaction
    from django.contrib import messages
    
    if request.method == 'POST':
        client_id = request.POST.get('client')
        amount = int(request.POST.get('amount', 0))
        type = request.POST.get('type')
        date_str = request.POST.get('date')
        notes = request.POST.get('notes', '')

        client = get_object_or_404(Client, pk=client_id, user=request.user)

        # Convert date string to datetime (set time to noon)
        from datetime import datetime, time
        if date_str:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            # Combine with noon time
            date_datetime = datetime.combine(date_obj, time(12, 0))
        else:
            date_datetime = timezone.now()

        PendingPaymentTransaction.objects.create(
            client=client,
            amount=amount,
            type=type,
            date=date_datetime,
            notes=notes,
            created_by=request.user
        )

        messages.success(request, f"Transaction recorded for {client.name}")
        return redirect('pending_payments_list')
    
    clients = Client.objects.filter(user=request.user).order_by('name')
    selected_client_id = request.GET.get('client')
    selected_type = request.GET.get('type')

    # Get selected client details if any
    selected_client = None
    client_exchanges = []
    if selected_client_id:
        try:
            selected_client = Client.objects.get(pk=int(selected_client_id), user=request.user)
            client_exchanges = selected_client.exchange_accounts.select_related('exchange').all()
        except (ValueError, Client.DoesNotExist):
            selected_client = None

    return render(request, 'core/pending_payments/form.html', {
        'clients': clients,
        'selected_client_id': int(selected_client_id) if selected_client_id else None,
        'selected_client': selected_client,
        'client_exchanges': client_exchanges,
        'selected_type': selected_type,
        'today': timezone.now().strftime('%Y-%m-%d'),
    })

@login_required
def pending_payment_edit(request, pk):
    """Edit an existing pending payment transaction."""
    from .models import PendingPaymentTransaction
    from django.contrib import messages
    
    transaction = get_object_or_404(PendingPaymentTransaction, pk=pk, client__user=request.user)
    
    if request.method == 'POST':
        transaction.amount = int(request.POST.get('amount', 0))
        transaction.type = request.POST.get('type')
        transaction.date = request.POST.get('date')
        transaction.notes = request.POST.get('notes', '')
        transaction.save()
        
        messages.success(request, "Transaction updated successfully")
        return redirect('pending_payments_list')
    
    return render(request, 'core/pending_payments/form.html', {
        'transaction': transaction,
        'clients': [transaction.client],
        'is_edit': True,
    })

@login_required
def pending_payment_delete(request, pk):
    """Delete a pending payment transaction."""
    from .models import PendingPaymentTransaction
    from django.contrib import messages
    from django.utils.http import url_has_allowed_host_and_scheme
    
    transaction = get_object_or_404(PendingPaymentTransaction, pk=pk, client__user=request.user)
    
    if request.method == 'POST':
        next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
        transaction.delete()
        messages.success(request, "Transaction deleted successfully")

        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        
    return redirect('pending_payments_list')
