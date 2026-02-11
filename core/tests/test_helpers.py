"""
Comprehensive test cases for helper functions in views.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal

from core.models import Client, Exchange, ClientExchangeAccount
from core.views import (
    calculate_display_remaining,
    get_settlement_info_for_display
)

User = get_user_model()


class HelperFunctionsTests(TestCase):
    """Test cases for helper functions"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.client = Client.objects.create(name='Test Client', user=self.user)
        self.exchange = Exchange.objects.create(name='Test Exchange')
    
    def test_calculate_display_remaining_loss_case(self):
        """Test calculate_display_remaining for loss case"""
        # Loss case: Client_PnL < 0, DisplayRemaining = +RemainingRaw
        client_pnl = -500
        remaining_amount = 100
        result = calculate_display_remaining(client_pnl, remaining_amount)
        self.assertEqual(result, 100)  # Positive for loss
    
    def test_calculate_display_remaining_profit_case(self):
        """Test calculate_display_remaining for profit case"""
        # Profit case: Client_PnL > 0, DisplayRemaining = -RemainingRaw
        client_pnl = 500
        remaining_amount = 100
        result = calculate_display_remaining(client_pnl, remaining_amount)
        self.assertEqual(result, -100)  # Negative for profit
    
    def test_calculate_display_remaining_zero_pnl(self):
        """Test calculate_display_remaining for zero PnL"""
        client_pnl = 0
        remaining_amount = 100
        result = calculate_display_remaining(client_pnl, remaining_amount)
        self.assertEqual(result, 100)  # Default to positive
    
    def test_get_settlement_info_for_display(self):
        """Test get_settlement_info_for_display helper"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=100,
            loss_share_percentage=10
        )
        
        settlement_info = get_settlement_info_for_display(account)
        
        # Check all required keys are present
        self.assertIn('initial_final_share', settlement_info)
        self.assertIn('remaining_amount', settlement_info)
        self.assertIn('overpaid_amount', settlement_info)
        self.assertIn('final_share', settlement_info)
        self.assertIn('show_na', settlement_info)
        self.assertIn('share_pct', settlement_info)
        self.assertIn('client_pnl', settlement_info)
        
        # Verify values
        self.assertIsNotNone(settlement_info['initial_final_share'])
        self.assertIsInstance(settlement_info['remaining_amount'], int)
        self.assertIsInstance(settlement_info['show_na'], bool)
    
    def test_get_settlement_info_for_display_zero_share(self):
        """Test get_settlement_info_for_display with zero share"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=1000,  # PnL = 0, Share = 0
            loss_share_percentage=10
        )
        
        settlement_info = get_settlement_info_for_display(account)
        
        # Should show N.A for zero share
        self.assertTrue(settlement_info['show_na'])
        self.assertEqual(settlement_info['final_share'], 0)
    
    def test_get_settlement_info_for_display_with_settlements(self):
        """Test get_settlement_info_for_display with existing settlements"""
        from core.models import Settlement
        from django.utils import timezone
        
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=100,
            loss_share_percentage=10
        )
        
        # Lock share first
        account.lock_initial_share_if_needed()
        
        # Create a settlement
        Settlement.objects.create(
            client_exchange=account,
            amount=50,
            date=timezone.now()
        )
        
        settlement_info = get_settlement_info_for_display(account)

        # Remaining amount should be 0 (correct behavior)
        self.assertEqual(settlement_info['remaining_amount'], 0)
