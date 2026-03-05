from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.reverse import reverse
from django.contrib.auth import authenticate
from django.db.models import Sum, Q
from django.utils import timezone
from django.http import HttpResponse
from decimal import Decimal
from datetime import date, timedelta
import csv
from .models import Client, Exchange, ClientExchangeAccount, Transaction, MobileLog
from .serializers import (
    ClientSerializer, ExchangeSerializer,
    ClientExchangeAccountSerializer, TransactionSerializer
)
from .views import calculate_display_remaining

@api_view(['GET'])
@permission_classes([])  # Allow unauthenticated access to API root
def api_root(request):
    """API root endpoint - lists available API endpoints"""
    return Response({
        'clients': reverse('api-client-list', request=request),
        'exchanges': reverse('api-exchange-list', request=request),
        'accounts': reverse('api-account-list', request=request),
        'transactions': reverse('api-transaction-list', request=request),
        'login': reverse('api-login', request=request),
        'mobile-dashboard': reverse('api-mobile-dashboard', request=request),
        'pending-payments': reverse('api-pending-payments', request=request),
        'mobile-logs': reverse('api-submit-mobile-log', request=request),
        'message': 'API endpoints require authentication. Use /api/login/ to obtain a token.',
    })

@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def api_account_report_config(request, account_id):
    try:
        account = ClientExchangeAccount.objects.get(id=account_id, client__user=request.user)
        
        if request.method == 'POST':
            friend_pct_raw = request.data.get("friend_percentage", None)
            my_own_pct_raw = request.data.get("my_own_percentage", None)

            my_total = Decimal(str(account.my_percentage or 0))
            friend_pct = Decimal(str(friend_pct_raw)) if friend_pct_raw is not None and str(friend_pct_raw).strip() != "" else Decimal(str(account.company_percentage or 0))
            my_own_pct = Decimal(str(my_own_pct_raw)) if my_own_pct_raw is not None and str(my_own_pct_raw).strip() != "" else Decimal(str(account.my_own_percentage or 0))

            # Normalize so Company% + MyOwn% == MyTotal%
            epsilon = Decimal("0.01")
            if my_total > 0 and abs((friend_pct + my_own_pct) - my_total) >= epsilon:
                if friend_pct > my_total:
                    friend_pct = my_total
                    my_own_pct = Decimal("0")
                else:
                    my_own_pct = my_total - friend_pct

            account.company_percentage = friend_pct
            account.my_own_percentage = my_own_pct
            account.save(update_fields=["company_percentage", "my_own_percentage"])
            return Response({'status': 'success'})
            
        return Response({
            'friend_percentage': float(account.company_percentage or 0),
            'my_own_percentage': float(account.my_own_percentage or 0),
            'my_total_percentage': float(account.my_percentage or 0)
        })
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([])  # Allow unauthenticated access for login
def api_login(request):
    """API endpoint for mobile app login"""
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response(
            {'error': 'Username and password required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    user = authenticate(username=username, password=password)
    if user:
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username
        })
    else:
        return Response(
            {'error': 'Invalid credentials'}, 
            status=status.HTTP_401_UNAUTHORIZED
        )

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def mobile_dashboard_summary(request):
    accounts = ClientExchangeAccount.objects.filter(client__user=request.user)
    
    total_funding = accounts.aggregate(Sum('funding'))['funding__sum'] or 0
    total_balance = accounts.aggregate(Sum('exchange_balance'))['exchange_balance__sum'] or 0
    
    # Calculate PnL and share
    total_pnl = 0
    total_my_share = 0
    for account in accounts:
        total_pnl += account.compute_client_pnl()
        total_my_share += account.compute_my_share()
    
    return Response({
        "total_clients": Client.objects.filter(user=request.user).count(),
        "total_exchanges": Exchange.objects.count(),
        "total_accounts": accounts.count(),
        "total_funding": total_funding,
        "total_balance": total_balance,
        "total_pnl": total_pnl,
        "total_my_share": total_my_share,
        "currency": "INR"
    })

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def api_pending_payments(request):
    """API endpoint for pending payments - must match website logic exactly"""
    accounts = ClientExchangeAccount.objects.filter(client__user=request.user).select_related('client', 'exchange')

    clients_owe_list = []
    you_owe_list = []
    total_to_receive = 0
    total_to_pay = 0

    for client_exchange in accounts:
        # Compute PnL BEFORE any updates
        client_pnl = client_exchange.compute_client_pnl()

        # Skip accounts with zero PnL
        if client_pnl == 0:
            continue

        # Determine case
        is_loss_case = client_pnl < 0  # Client owes you (loss)
        is_profit_case = client_pnl > 0  # You owe client (profit)

        # Lock share and get settlement info (CRITICAL for MASKED SHARE SETTLEMENT SYSTEM)
        client_exchange.lock_initial_share_if_needed()
        settlement_info = client_exchange.get_remaining_settlement_amount()
        initial_final_share = settlement_info['initial_final_share']
        remaining_amount = settlement_info['remaining']

        # Use initial locked share for display
        final_share = initial_final_share if initial_final_share > 0 else client_exchange.compute_my_share()

        # Get share percentage using helper method
        share_pct = client_exchange.get_share_percentage(client_pnl)

        # Calculate opening and available points for display
        funding = Decimal(client_exchange.funding)
        exchange_balance = Decimal(client_exchange.exchange_balance)

        if is_loss_case:
            # Client owes you (loss case)
            total_loss = abs(client_pnl)
            opening_points = total_loss
            available_points = total_loss

            # Calculate display remaining using website logic
            display_remaining = calculate_display_remaining(client_pnl, remaining_amount)
            remaining_display = abs(display_remaining) if display_remaining else 0

            item = {
                'account_id': client_exchange.id,
                'client_name': client_exchange.client.name,
                'client_code': client_exchange.client.code,
                'exchange_name': client_exchange.exchange.name,
                'funding': client_exchange.funding,
                'exchange_balance': client_exchange.exchange_balance,
                'pnl': client_pnl,
                'my_share': final_share,
                'type': 'RECEIVE',
                'opening_points': opening_points,
                'available_points': available_points,
                'share_percentage': float(share_pct),
                'remaining_amount': remaining_display,
                'show_na': (final_share == 0)
            }

            clients_owe_list.append(item)
            total_to_receive += remaining_display

        elif is_profit_case:
            # You owe client (profit case)
            unpaid_profit = client_pnl
            opening_points = unpaid_profit
            available_points = unpaid_profit

            # Calculate display remaining using website logic
            display_remaining = calculate_display_remaining(client_pnl, remaining_amount)
            remaining_display = abs(display_remaining) if display_remaining else 0

            item = {
                'account_id': client_exchange.id,
                'client_name': client_exchange.client.name,
                'client_code': client_exchange.client.code,
                'exchange_name': client_exchange.exchange.name,
                'funding': client_exchange.funding,
                'exchange_balance': client_exchange.exchange_balance,
                'pnl': client_pnl,
                'my_share': final_share,
                'type': 'PAY',
                'opening_points': opening_points,
                'available_points': available_points,
                'share_percentage': float(share_pct),
                'remaining_amount': remaining_display,
                'show_na': (final_share == 0)
            }

            you_owe_list.append(item)
            total_to_pay += remaining_display

    # Combine lists for API response (filter out N.A items)
    pending_list = [item for item in clients_owe_list + you_owe_list if not item.get('show_na', False)]

    return Response({
        'pending_payments': pending_list,
        'total_to_receive': total_to_receive,
        'total_to_pay': total_to_pay,
        'currency': 'INR'
    })

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def api_export_pending_csv(request):
    """
    Export pending payments report as CSV for mobile app.
    Mirrors the website's export_pending_csv exactly.
    """
    # Get all client exchanges for the user
    client_exchanges = ClientExchangeAccount.objects.filter(
        client__user=request.user
    ).select_related("client", "exchange")
    
    clients_owe_list = []
    you_owe_list = []
    
    for client_exchange in client_exchanges:
        client_pnl = client_exchange.compute_client_pnl()
        
        # Determine cases
        is_neutral_case = client_pnl == 0
        is_loss_case = client_pnl < 0
        is_profit_case = client_pnl > 0
        
        # Lock share if needed
        client_exchange.lock_initial_share_if_needed()
        settlement_info = client_exchange.get_remaining_settlement_amount()
        initial_final_share = settlement_info['initial_final_share']
        remaining_amount = settlement_info['remaining']
        
        # Use initial locked share for display
        final_share = initial_final_share if initial_final_share > 0 else client_exchange.compute_my_share()
        share_pct = client_exchange.get_share_percentage(client_pnl)
        
        if is_neutral_case:
            clients_owe_list.append({
                "client": client_exchange.client,
                "exchange": client_exchange.exchange,
                "account": client_exchange,
                "client_pnl": client_pnl,
                "remaining_amount": 0,
                "share_percentage": share_pct,
                "show_na": True,
            })
            continue
            
        # Calculate display remaining using website logic
        display_remaining = calculate_display_remaining(client_pnl, remaining_amount)
        remaining_display = abs(display_remaining) if display_remaining else 0
        
        item_data = {
            "client": client_exchange.client,
            "exchange": client_exchange.exchange,
            "account": client_exchange,
            "client_pnl": client_pnl,
            "remaining_amount": remaining_display,
            "final_share": final_share,
            "share_percentage": share_pct,
            "show_na": (final_share == 0),
        }
        
        if is_loss_case:
            clients_owe_list.append(item_data)
        elif is_profit_case:
            you_owe_list.append(item_data)

    # Sort lists by amount (descending) - Matching website logic
    def get_csv_sort_key(item):
        if item.get("show_na", False): return 0
        return abs(item.get("final_share", 0))

    clients_owe_list.sort(key=get_csv_sort_key, reverse=True)
    you_owe_list.sort(key=get_csv_sort_key, reverse=True)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    filename = f"settlements_{date.today().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    # Write header row - Same as website
    headers = [
        'Client',
        'U_CODE',
        'Master',
        'OPENING POINTS',
        'AVL.POINTS(CLOSING POINTS)',
        'PROFIT(+)/LOSS(-)',
        'MY SHARE',
        'MY%'
    ]
    writer.writerow(headers)
    
    # Write rows
    for item in clients_owe_list + you_owe_list:
        row_data = [
            item["client"].name or '',
            item["client"].code or '',
            item["exchange"].name or '',
            int(item["account"].funding),
            int(item["account"].exchange_balance),
            'N.A' if item.get("show_na", False) else int(item["client_pnl"]),
            'N.A' if item.get("show_na", False) else int(item["remaining_amount"]),
            item.get("share_percentage", item["account"].my_percentage)
        ]
        writer.writerow(row_data)
        
    return response

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def api_add_funding(request, account_id):
    try:
        account = ClientExchangeAccount.objects.get(id=account_id, client__user=request.user)
        amount_raw = str(request.data.get('amount', '0'))
        amount = int(Decimal(amount_raw.replace(',', '')))
        notes = request.data.get('notes', '')
        
        account.funding += amount
        account.exchange_balance += amount
        account.save()
        
        Transaction.objects.create(
            client_exchange=account,
            date=timezone.now(),
            type='FUNDING',
            amount=amount,
            funding_after=account.funding,
            exchange_balance_after=account.exchange_balance,
            notes=notes
        )
        return Response({'status': 'success', 'new_balance': account.exchange_balance})
    except Exception as e:
        print(f"DEBUG API FUNDING ERROR: {str(e)}")
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def api_update_balance(request, account_id):
    try:
        account = ClientExchangeAccount.objects.get(id=account_id, client__user=request.user)
        amount_raw = str(request.data.get('amount', '0'))
        new_balance = int(Decimal(amount_raw.replace(',', '')))
        notes = request.data.get('notes', '')
        
        exchange_before = account.exchange_balance
        account.exchange_balance = new_balance
        account.save()
        
        Transaction.objects.create(
            client_exchange=account,
            date=timezone.now(),
            type='UPDATE_BALANCE',
            amount=abs(int(new_balance) - int(exchange_before)),
            funding_after=account.funding,
            exchange_balance_after=account.exchange_balance,
            notes=notes
        )
        return Response({'status': 'success'})
    except Exception as e:
        print(f"DEBUG API BALANCE ERROR: {str(e)}")
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def api_record_payment(request, account_id):
    """
    API version of record_payment view - MUST follow EXACT same rules as website
    Implements the complete MASKED SHARE SETTLEMENT SYSTEM
    """
    try:
        from django.db import transaction
        from django.core.exceptions import ValidationError
        from core.models import Settlement

        # Debug logging
        print(f"DEBUG API RECORD PAYMENT: account_id={account_id}")
        print(f"DEBUG API RECORD PAYMENT DATA: {dict(request.data)}")

        # Parse request data - handle both snake_case and camelCase
        paid_amount_str = str(request.data.get('amount', '0')).strip()
        paid_amount = int(Decimal(paid_amount_str.replace(',', '')))
        payment_direction = request.data.get('payment_direction', request.data.get('paymentDirection', 'FROM_CLIENT'))
        notes = request.data.get('notes', '').strip()

        # Handle nullable boolean fields properly - check both snake_case and camelCase
        update_exchange_balance = request.data.get('update_exchange_balance', request.data.get('updateExchangeBalance'))
        if update_exchange_balance is not None:
            update_exchange_balance = bool(update_exchange_balance)
        else:
            update_exchange_balance = False

        new_exchange_balance = request.data.get('new_exchange_balance', request.data.get('newExchangeBalance'))

        re_add_capital = request.data.get('re_add_capital', request.data.get('reAddCapital'))
        if re_add_capital is not None:
            re_add_capital = bool(re_add_capital)
        else:
            re_add_capital = False

        print(f"DEBUG PARSED: amount={paid_amount}, direction={payment_direction}, update_balance={update_exchange_balance}, new_balance={new_exchange_balance}, re_add={re_add_capital}")

        if paid_amount <= 0:
            return Response({'error': 'Paid amount must be greater than zero'}, status=400)

        # Use database row locking to prevent concurrent payment race conditions
        with transaction.atomic():
            # Lock the account row to prevent concurrent modifications
            account = ClientExchangeAccount.objects.select_for_update().get(id=account_id, client__user=request.user)

            # ============================================================
            # SETTLEMENT FLOW - EXACT ORDER (NON-NEGOTIABLE) - SAME AS WEBSITE
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

            # If InitialFinalShare = 0, this is NOT a settlement - just record as regular payment
            is_settlement = (initial_final_share > 0)

            # Initialize variables that need to be accessible in return statement
            cycle_closed = False
            masked_capital = 0
            transaction_amount = paid_amount
            remaining_amount = settlement_info['remaining']  # Always available from settlement_info

            if is_settlement:
                # Full settlement logic for accounts with share > 0
                print(f"DEBUG: Settlement payment (share={initial_final_share})")

                # Validate against remaining settlement amount
                if paid_amount > remaining_amount:
                    return Response({
                        'error': f'Paid amount ({paid_amount}) cannot exceed remaining settlement amount ({remaining_amount}). Initial share: {initial_final_share}, Already settled: {total_settled}'
                    }, status=400)

                # Check if PnL = 0 (trading flat, not settlement complete)
                if client_pnl_before == 0:
                    return Response({'error': 'Account PnL is zero (trading flat). No settlement needed'}, status=400)

                # 5. Compute masked capital
                masked_capital = account.compute_masked_capital(paid_amount)
                if masked_capital == 0:
                    return Response({'error': 'Cannot calculate masked capital. Initial final share is zero'}, status=400)

            # Decide transaction sign BEFORE balance update - CRITICAL SAME AS WEBSITE
            if client_pnl_before > 0:
                # PROFIT CASE: YOU pay client → amount is NEGATIVE (your loss)
                transaction_amount = -paid_amount
            elif client_pnl_before < 0:
                # LOSS CASE: Client pays YOU → amount is POSITIVE (your profit)
                transaction_amount = paid_amount
            else:
                transaction_amount = 0

            # 6. Validate and compute balance updates - SAME AS WEBSITE
            if client_pnl_before < 0:
                # LOSS CASE: Masked capital reduces Funding
                if account.funding - int(masked_capital) < 0:
                    return Response({
                        'error': f'Cannot record payment. Funding would become negative (Current: {account.funding}, Masked Capital: {int(masked_capital)})'
                    }, status=400)
                funding_after_settlement = account.funding - int(masked_capital)
                exchange_after_settlement = account.exchange_balance  # Unchanged
            else:
                # PROFIT CASE: Masked capital reduces Exchange Balance
                if account.exchange_balance - int(masked_capital) < 0:
                    return Response({
                        'error': f'Cannot record payment. Exchange balance would become negative (Current: {account.exchange_balance}, Masked Capital: {int(masked_capital)})'
                    }, status=400)
                funding_after_settlement = account.funding  # Unchanged (CRITICAL RULE)
                exchange_after_settlement = account.exchange_balance - int(masked_capital)

            # Handle exchange balance update if specified (settlement payment)
            if update_exchange_balance and new_exchange_balance is not None:
                try:
                    new_balance_str = str(new_exchange_balance).replace(',', '')
                    new_balance = int(Decimal(new_balance_str))
                    exchange_after_settlement = new_balance
                except (ValueError, TypeError):
                    return Response({'error': 'Invalid new exchange balance'}, status=400)

            # 7. Update balances
            account.funding = funding_after_settlement
            account.exchange_balance = exchange_after_settlement
            account.save()

            # Create Settlement record - SAME AS WEBSITE
            settlement = Settlement.objects.create(
                client_exchange=account,
                amount=paid_amount,
                date=timezone.now(),
                notes=notes or f"Payment recorded: {paid_amount}"
            )

            # Create RECORD_PAYMENT transaction with before/after balances - SAME AS WEBSITE
            Transaction.objects.create(
                client_exchange=account,
                date=timezone.now(),
                type='RECORD_PAYMENT',
                amount=transaction_amount,  # CRITICAL: Signed amount for profit/loss reporting
                funding_before=funding_before,
                funding_after=funding_after_settlement,
                exchange_balance_before=exchange_before,
                exchange_balance_after=exchange_after_settlement,
                notes=notes or f"Settlement share payment: {paid_amount}. Masked Capital: {int(masked_capital)}"
            )

            # 8. IF auto-refund enabled: Save FUNDING_AUTO transaction - SAME AS WEBSITE
            cycle_closed = False
            if is_settlement:
                if re_add_capital and client_pnl_before < 0:
                    # Auto re-funding: Funding = Funding + MaskedCapital
                    funding_before_refund = account.funding
                    exchange_before_refund = account.exchange_balance

                    account.funding += int(masked_capital)
                    account.exchange_balance += int(masked_capital)
                    account.save()

                    # Create FUNDING_AUTO transaction
                    Transaction.objects.create(
                        client_exchange=account,
                        date=timezone.now(),
                        type='FUNDING_AUTO',
                        amount=int(masked_capital),
                        funding_before=funding_before_refund,
                        funding_after=account.funding,
                        exchange_balance_before=exchange_before_refund,
                        exchange_balance_after=account.exchange_balance,
                        notes=f"Auto-refund after settlement: {int(masked_capital)}"
                    )
                    cycle_closed = True
            else:
                # Simple payment recording for accounts with share = 0
                print(f"DEBUG: Regular payment recording (share=0)")

                # For non-settlement payments, just update exchange balance based on payment direction
                if payment_direction == 'FROM_CLIENT':
                    # Client pays you - increase exchange balance
                    account.exchange_balance += paid_amount
                elif payment_direction == 'TO_CLIENT':
                    # You pay client - decrease exchange balance
                    if account.exchange_balance - paid_amount < 0:
                        return Response({
                            'error': f'Cannot record payment. Exchange balance would become negative (Current: {account.exchange_balance}, Payment: {paid_amount})'
                        }, status=400)
                    account.exchange_balance -= paid_amount

                # Handle exchange balance update if specified
                if update_exchange_balance and new_exchange_balance is not None:
                    try:
                        new_balance_str = str(new_exchange_balance).replace(',', '')
                        new_balance = int(Decimal(new_balance_str))
                        account.exchange_balance = new_balance
                    except (ValueError, TypeError):
                        return Response({'error': 'Invalid new exchange balance'}, status=400)

                account.save()

                # Create simple transaction record
                transaction_amount = paid_amount if payment_direction == 'FROM_CLIENT' else -paid_amount
                Transaction.objects.create(
                    client_exchange=account,
                    date=timezone.now(),
                    type='RECORD_PAYMENT',
                    amount=transaction_amount,
                    funding_before=funding_before,
                    funding_after=account.funding,
                    exchange_balance_before=exchange_before,
                    exchange_balance_after=account.exchange_balance,
                    notes=notes or f"Payment recorded: {paid_amount}"
                )
                cycle_closed = False

        return Response({
            'status': 'success',
            'settlement_completed': is_settlement and (paid_amount >= remaining_amount if is_settlement else False),
            'cycle_closed': cycle_closed,
            'remaining_amount': max(0, remaining_amount - paid_amount) if is_settlement else 0
        })

    except ClientExchangeAccount.DoesNotExist:
        return Response({'error': 'Account not found'}, status=404)
    except ValidationError as e:
        return Response({'error': str(e)}, status=400)
    except Exception as e:
        print(f"DEBUG API RECORD PAYMENT ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=400)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def api_reports_summary(request):
    """Real business reports for mobile with period filtering"""
    period = request.query_params.get('period', 'DAILY')
    accounts = ClientExchangeAccount.objects.filter(client__user=request.user)
    today = timezone.now().date()
    
    start_date = today
    if period == 'WEEKLY':
        start_date = today - timedelta(days=7)
    elif period == 'MONTHLY':
        start_date = today - timedelta(days=30)
    
    # Filter transactions for stats if needed, or just return overview
    total_funding = accounts.aggregate(Sum('funding'))['funding__sum'] or 0
    total_balance = accounts.aggregate(Sum('exchange_balance'))['exchange_balance__sum'] or 0
    total_pnl = sum(acc.compute_client_pnl() for acc in accounts)
    total_my_share = sum(acc.compute_my_share() for acc in accounts)
    
    # NEW: Split of My Share (My Own vs Friend/Student)
    my_own_total_share = 0
    friend_total_share = 0
    
    for acc in accounts:
        acc_my_share = acc.compute_my_share()
        if acc_my_share <= 0:
            continue
        my_total = Decimal(str(acc.my_percentage or 0))
        if my_total <= 0:
            my_own_total_share += acc_my_share
            continue
        my_own_pct = Decimal(str(acc.my_own_percentage or 0))
        friend_pct = Decimal(str(acc.company_percentage or 0))
        my_own_total_share += int((Decimal(acc_my_share) * (my_own_pct / my_total)))
        friend_total_share += int((Decimal(acc_my_share) * (friend_pct / my_total)))

    # Recent Daily Performance (last 7 days)
    daily_stats = []
    for i in range(7):
        day = today - timedelta(days=i)
        day_txns = Transaction.objects.filter(
            client_exchange__client__user=request.user,
            date__date=day
        )
        
        day_pnl = 0
        for tx in day_txns:
            if tx.type == 'TRADE':
                if tx.exchange_balance_before is not None and tx.exchange_balance_after is not None:
                    day_pnl += (tx.exchange_balance_after - tx.exchange_balance_before)
            elif tx.type == 'SETTLEMENT_SHARE' or tx.type == 'RECORD_PAYMENT':
                # These are payments, not trading PnL
                pass
        
        if day_txns.exists():
            daily_stats.append({
                'date': day.strftime('%Y-%m-%d'),
                'pnl': day_pnl,
                'tx_count': day_txns.count()
            })

    # NEW: Client Performance for the selected period
    client_performance = []
    period_txns = Transaction.objects.filter(
        client_exchange__client__user=request.user,
        date__date__gte=start_date,
        date__date__lte=today
    )
    
    client_ids = accounts.values_list('client_id', flat=True).distinct()
    for cid in client_ids:
        client = Client.objects.get(id=cid)
        client_txns = period_txns.filter(client_exchange__client_id=cid)
        
        # Calculate PnL (trading activity) and Settlements (your profit/loss)
        client_pnl = 0
        client_settlements = 0
        
        for tx in client_txns:
            if tx.type == 'TRADE':
                if tx.exchange_balance_before is not None and tx.exchange_balance_after is not None:
                    client_pnl += (tx.exchange_balance_after - tx.exchange_balance_before)
            elif tx.type in ['SETTLEMENT_SHARE', 'RECORD_PAYMENT']:
                client_settlements += tx.amount
        
        if client_txns.exists():
            client_performance.append({
                'client_name': client.name,
                'client_code': client.code,
                'pnl': client_pnl,
                'settlements': client_settlements, # Your actual profit/loss
                'tx_count': client_txns.count()
            })

    return Response({
        'overview': {
            'total_funding': total_funding,
            'total_balance': total_balance,
            'total_pnl': total_pnl,
            'total_my_share': total_my_share,
            'my_own_share': my_own_total_share,
            'friend_share': friend_total_share,
        },
        'daily_performance': daily_stats,
        'client_performance': client_performance,
        'period': period,
        'start_date': start_date
    })

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def api_export_reports_csv(request):
    """Export general reports (daily, weekly, monthly) as CSV for mobile app."""
    period = request.query_params.get('period', 'DAILY')
    accounts = ClientExchangeAccount.objects.filter(client__user=request.user)
    today = timezone.now().date()

    start_date = today
    if period == 'WEEKLY':
        start_date = today - timedelta(days=7)
    elif period == 'MONTHLY':
        start_date = today - timedelta(days=30)
    
    response = HttpResponse(content_type='text/csv')
    filename = f"report_{period.lower()}_{date.today().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)

    # Write overview data
    writer.writerow(['Report Period', period])
    writer.writerow(['Report Date', date.today().isoformat()])
    writer.writerow([])

    total_funding = accounts.aggregate(Sum('funding'))['funding__sum'] or 0
    total_balance = accounts.aggregate(Sum('exchange_balance'))['exchange_balance__sum'] or 0
    total_pnl = sum(acc.compute_client_pnl() for acc in accounts)
    total_my_share = sum(acc.compute_my_share() for acc in accounts)
    
    my_own_total_share = 0
    friend_total_share = 0
    
    for acc in accounts:
        acc_my_share = acc.compute_my_share()
        if acc_my_share <= 0:
            continue
        my_total = Decimal(str(acc.my_percentage or 0))
        if my_total <= 0:
            my_own_total_share += acc_my_share
            continue
        my_own_pct = Decimal(str(acc.my_own_percentage or 0))
        friend_pct = Decimal(str(acc.company_percentage or 0))
        my_own_total_share += int((Decimal(acc_my_share) * (my_own_pct / my_total)))
        friend_total_share += int((Decimal(acc_my_share) * (friend_pct / my_total)))

    writer.writerow(['Overview'])
    writer.writerow(['Total Funding', total_funding])
    writer.writerow(['Total Balance', total_balance])
    writer.writerow(['Total PnL', total_pnl])
    writer.writerow(['Total My Share', total_my_share])
    writer.writerow(['My Own Share', my_own_total_share])
    writer.writerow(['Friend Share', friend_total_share])
    writer.writerow([])

    # Daily Performance (last 7 days)
    writer.writerow(['Daily Performance (Last 7 Days)'])
    writer.writerow(['Date', 'PnL', 'Transactions Count'])
    for i in range(7):
        day = today - timedelta(days=i)
        day_txns = Transaction.objects.filter(
            client_exchange__client__user=request.user,
            date__date=day
        )
        day_pnl = 0
        for tx in day_txns:
            if tx.type == 'TRADE':
                if tx.exchange_balance_before is not None and tx.exchange_balance_after is not None:
                    day_pnl += (tx.exchange_balance_after - tx.exchange_balance_before)
        if day_txns.exists():
            writer.writerow([day.strftime('%Y-%m-%d'), day_pnl, day_txns.count()])
    writer.writerow([])

    # Client Performance for the selected period
    writer.writerow(['Client Performance (Selected Period)'])
    writer.writerow(['Client Name', 'Client Code', 'PnL', 'Settlements', 'Transactions Count'])
    period_txns = Transaction.objects.filter(
        client_exchange__client__user=request.user,
        date__date__gte=start_date,
        date__date__lte=today
    )
    client_ids = accounts.values_list('client_id', flat=True).distinct()
    for cid in client_ids:
        client = Client.objects.get(id=cid)
        client_txns = period_txns.filter(client_exchange__client_id=cid)
        client_pnl = 0
        client_settlements = 0
        for tx in client_txns:
            if tx.type == 'TRADE':
                if tx.exchange_balance_before is not None and tx.exchange_balance_after is not None:
                    client_pnl += (tx.exchange_balance_after - tx.exchange_balance_before)
            elif tx.type in ['SETTLEMENT_SHARE', 'RECORD_PAYMENT']:
                client_settlements += tx.amount
        if client_txns.exists():
            writer.writerow([client.name, client.code, client_pnl, client_settlements, client_txns.count()])
    writer.writerow([])

    return response

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def api_custom_reports(request):
    """Custom date range reports"""
    from_date_str = request.query_params.get('from_date')
    to_date_str = request.query_params.get('to_date')
    client_id = request.query_params.get('client_id')
    exchange_id = request.query_params.get('exchange_id')

    if not from_date_str or not to_date_str:
        return Response({'error': 'from_date and to_date are required'}, status=400)

    try:
        from_date = timezone.datetime.fromisoformat(from_date_str).date()
        to_date = timezone.datetime.fromisoformat(to_date_str).date()
    except ValueError:
        return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)

    # Base queryset
    accounts = ClientExchangeAccount.objects.filter(client__user=request.user)

    # Apply filters
    if client_id:
        accounts = accounts.filter(client_id=client_id)
    if exchange_id:
        accounts = accounts.filter(exchange_id=exchange_id)

    # Get transactions in date range
    transactions = Transaction.objects.filter(
        client_exchange__in=accounts,
        date__date__gte=from_date,
        date__date__lte=to_date
    ).select_related('client_exchange', 'client_exchange__client', 'client_exchange__exchange').order_by('-date')

    # Calculate summary stats
    total_funding = accounts.aggregate(Sum('funding'))['funding__sum'] or 0
    total_balance = accounts.aggregate(Sum('exchange_balance'))['exchange_balance__sum'] or 0
    total_pnl = sum(acc.compute_client_pnl() for acc in accounts)
    total_my_share = sum(acc.compute_my_share() for acc in accounts)

    # Split calculation (same as other reports)
    my_own_total_share = 0
    friend_total_share = 0

    for acc in accounts:
        acc_my_share = acc.compute_my_share()
        if acc_my_share <= 0:
            continue
        my_total = Decimal(str(acc.my_percentage or 0))
        if my_total <= 0:
            my_own_total_share += acc_my_share
            continue
        my_own_pct = Decimal(str(acc.my_own_percentage or 0))
        friend_pct = Decimal(str(acc.company_percentage or 0))
        my_own_total_share += int((Decimal(acc_my_share) * (my_own_pct / my_total)))
        friend_total_share += int((Decimal(acc_my_share) * (friend_pct / my_total)))

    # Serialize transactions for mobile
    transaction_data = []
    for txn in transactions[:50]:  # Limit to 50 transactions
        transaction_data.append({
            'id': txn.id,
            'type_display': txn.get_type_display(),
            'client_name': txn.client_exchange.client.name,
            'exchange_name': txn.client_exchange.exchange.name,
            'date': txn.date.strftime('%Y-%m-%d %H:%M:%S'),
            'amount': txn.amount,
            'notes': txn.notes or ''
        })

    return Response({
        'overview': {
            'total_funding': total_funding,
            'total_balance': total_balance,
            'total_pnl': total_pnl,
            'total_my_share': total_my_share,
            'my_own_share': my_own_total_share,
            'friend_share': friend_total_share,
        },
        'transactions': transaction_data,
        'from_date': from_date_str,
        'to_date': to_date_str,
        'total_transactions': transactions.count()
    })

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def api_link_exchange(request):
    try:
        # Handle both website format (client, exchange) and API format (client_id, exchange_id)
        client_id = request.data.get('client') or request.data.get('client_id')
        exchange_id = request.data.get('exchange') or request.data.get('exchange_id')

        my_percentage = request.data.get('my_percentage', '').strip()
        friend_percentage = request.data.get('friend_percentage', '').strip()
        my_own_percentage = request.data.get('my_own_percentage', '').strip()

        # Validation - client, exchange, and my_percentage are required
        if not client_id or not exchange_id or not my_percentage:
            return Response({'error': 'Client, Exchange, and My Total % are required.'}, status=400)

        try:
            client = Client.objects.get(pk=client_id, user=request.user)
            exchange = Exchange.objects.get(pk=exchange_id)
            my_pct = Decimal(str(my_percentage))

            # Validate percentage range
            if my_pct < 0 or my_pct > 100:
                return Response({'error': 'My Total % must be between 0 and 100.'}, status=400)

            # Check if link already exists
            if ClientExchangeAccount.objects.filter(client=client, exchange=exchange).exists():
                return Response({'error': f'Client "{client.name}" is already linked to "{exchange.name}".'}, status=400)

            # Create ClientExchangeAccount with MASKED SHARE SETTLEMENT SYSTEM
            # Default to my_percentage for both profit and loss shares (can be changed later)
            account = ClientExchangeAccount.objects.create(
                client=client,
                exchange=exchange,
                funding=0,  # Initial funding is 0 in this version
                exchange_balance=0,
                my_percentage=my_pct,
                company_percentage=Decimal(str(friend_percentage)) if friend_percentage else Decimal("0"),
                my_own_percentage=Decimal(str(my_own_percentage)) if my_own_percentage else Decimal("0"),
                loss_share_percentage=my_pct,  # Default to my_percentage
                profit_share_percentage=my_pct,  # Default to my_percentage (can change anytime)
            )

            return Response({'status': 'success', 'account_id': account.id})

        except (Client.DoesNotExist, Exchange.DoesNotExist):
            return Response({'error': 'Invalid client or exchange selected.'}, status=400)
        except ValueError:
            return Response({'error': 'Invalid percentage value. Please enter numbers only.'}, status=400)

    except Exception as e:
        print(f"DEBUG API LINK ERROR: {str(e)}")
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def api_create_exchange(request):
    """
    API endpoint to create a new exchange.
    Expected fields: name (required), version (optional), code (optional)
    """
    try:
        name = request.data.get('name', '').strip()
        version = request.data.get('version', '').strip() or None
        code = request.data.get('code', '').strip() or None
        
        # Validate name is provided
        if not name:
            return Response({'error': 'Exchange name is required'}, status=400)
        
        # Check for duplicate name (case-insensitive) before creating
        existing = Exchange.objects.filter(name__iexact=name)
        if existing.exists():
            return Response({'error': f"Exchange '{name}' already exists"}, status=400)
        
        # Check for duplicate code if code is provided (code has unique constraint)
        if code:
            existing_code = Exchange.objects.filter(code=code)
            if existing_code.exists():
                return Response({'error': f"Exchange code '{code}' already exists"}, status=400)
        
        # Create exchange with proper field mapping
        # Note: Empty strings are converted to None to avoid unique constraint issues
        exchange = Exchange(
            name=name,
            version_name=version if version else None,
            code=code if code else None
        )
        
        # Call full_clean to trigger model validation
        exchange.full_clean()
        exchange.save()
        
        return Response({
            'status': 'success',
            'id': exchange.id,
            'name': exchange.name,
            'code': exchange.code,
            'version_name': exchange.version_name
        })
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"DEBUG API CREATE EXCHANGE ERROR: {error_msg}")
        print(traceback.format_exc())
        
        # Provide more specific error messages
        if 'unique' in error_msg.lower() or 'duplicate' in error_msg.lower() or 'already exists' in error_msg.lower():
            if 'code' in error_msg.lower():
                return Response({'error': f"Exchange code '{code}' already exists"}, status=400)
            else:
                return Response({'error': f"Exchange '{name}' already exists"}, status=400)
        elif 'validation' in error_msg.lower():
            # Extract validation error message
            if hasattr(e, 'message_dict'):
                errors = []
                for field, msgs in e.message_dict.items():
                    errors.extend(msgs)
                return Response({'error': ' '.join(errors)}, status=400)
            else:
                return Response({'error': f"Validation error: {error_msg}"}, status=400)
        else:
            return Response({'error': f"Error creating exchange: {error_msg}"}, status=400)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def api_edit_transaction(request, pk):
    try:
        transaction = Transaction.objects.get(id=pk, client_exchange__client__user=request.user)
        amount_raw = str(request.data.get('amount', transaction.amount))
        amount = int(Decimal(amount_raw.replace(',', '')))
        notes = request.data.get('notes', transaction.notes)
        
        # We only allow editing amount and notes for simplicity
        transaction.amount = amount
        transaction.notes = notes
        transaction.save()
        
        return Response({'status': 'success'})
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def api_delete_transaction(request, pk):
    try:
        from .views import transaction_delete_logic
        transaction = Transaction.objects.get(id=pk, client_exchange__client__user=request.user)
        account = transaction.client_exchange
        
        # Check if this is the latest transaction for this account
        latest_tx = Transaction.objects.filter(client_exchange=account).order_by('-created_at', '-id').first()
        
        if not latest_tx or transaction.pk != latest_tx.pk:
            return Response({'error': 'Only the last transaction can be deleted to maintain logic consistency.'}, status=400)
            
        transaction_delete_logic(transaction)
        return Response({'status': 'success'})
    except Transaction.DoesNotExist:
        return Response({'error': 'Transaction not found or access denied'}, status=404)
    except Exception as e:
        print(f"DEBUG API DELETE TXN ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def api_update_account_settings(request, account_id):
    try:
        account = ClientExchangeAccount.objects.get(id=account_id, client__user=request.user)
        account.profit_share_percentage = int(Decimal(str(request.data.get('profit_share', account.profit_share_percentage))))
        account.loss_share_percentage = int(Decimal(str(request.data.get('loss_share', account.loss_share_percentage))))
        account.save()
        return Response({'status': 'success'})
    except Exception as e:
        print(f"DEBUG API SETTINGS ERROR: {str(e)}")
        return Response({'error': str(e)}, status=400)

@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def api_delete_client(request, pk):
    try:
        client = Client.objects.get(id=pk, user=request.user)
        client.delete()
        return Response({'status': 'success'})
    except Exception as e:
        print(f"DEBUG API DELETE CLIENT ERROR: {str(e)}")
        return Response({'error': str(e)}, status=400)

@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def api_delete_exchange(request, pk):
    try:
        # Note: Exchanges aren't owned by users in your models, 
        # but for security we'll assume only authenticated users can delete.
        exchange = Exchange.objects.get(id=pk)
        exchange.delete()
        return Response({'status': 'success'})
    except Exception as e:
        print(f"DEBUG API DELETE EXCHANGE ERROR: {str(e)}")
        return Response({'error': str(e)}, status=400)

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Client.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class ExchangeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Exchange.objects.all()
    serializer_class = ExchangeSerializer
    permission_classes = [permissions.IsAuthenticated]

class ClientExchangeAccountViewSet(viewsets.ModelViewSet):
    serializer_class = ClientExchangeAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Filter accounts by authenticated user for proper security
        return ClientExchangeAccount.objects.filter(client__user=self.request.user).select_related('client', 'exchange')

class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Filter transactions by authenticated user for proper security
        return Transaction.objects.filter(
            client_exchange__client__user=self.request.user
        ).order_by('-created_at', '-id')


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def api_submit_mobile_log(request):
    """
    API endpoint for mobile app to submit logs.
    Accepts single log entry or batch of logs.
    """
    try:
        # Handle both single log and batch of logs
        logs_data = request.data
        
        # If it's a single log object, wrap it in a list
        if not isinstance(logs_data, list):
            logs_data = [logs_data]
        
        created_logs = []
        errors = []
        
        for log_data in logs_data:
            try:
                # Extract log fields
                level = log_data.get('level', 'INFO').upper()
                if level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
                    level = 'INFO'
                
                tag = log_data.get('tag', '').strip()[:100]
                message = log_data.get('message', '').strip()
                
                if not message:
                    errors.append('Log message is required')
                    continue
                
                # Create log entry
                mobile_log = MobileLog.objects.create(
                    user=request.user,
                    level=level,
                    tag=tag,
                    message=message,
                    device_info=log_data.get('device_info', '').strip()[:200],
                    app_version=log_data.get('app_version', '').strip()[:50],
                    stack_trace=log_data.get('stack_trace', '').strip(),
                    extra_data=log_data.get('extra_data', {}) or {}
                )
                created_logs.append(mobile_log.id)
                
            except Exception as e:
                errors.append(f'Error creating log entry: {str(e)}')
        
        if created_logs:
            return Response({
                'success': True,
                'created': len(created_logs),
                'log_ids': created_logs,
                'errors': errors if errors else None
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'errors': errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
