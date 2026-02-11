"""
Comprehensive test cases for all forms in the core application.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from decimal import Decimal

from core.forms import (
    ClientForm, ExchangeForm, ClientExchangeLinkForm,
    FundingForm, ExchangeBalanceUpdateForm, RecordPaymentForm,
    SignupForm, OTPVerificationForm
)
from core.models import Client, Exchange, ClientExchangeAccount

User = get_user_model()


class ClientFormTests(TestCase):
    """Test cases for ClientForm"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
    
    def test_client_form_valid(self):
        """Test valid client form"""
        form = ClientForm(data={
            'name': 'Test Client',
            'code': 'CLIENT001',
            'referred_by': 'Referrer'
        })
        self.assertTrue(form.is_valid())
    
    def test_client_form_name_required(self):
        """Test that name is required"""
        form = ClientForm(data={'code': 'CLIENT001'})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
    
    def test_client_form_code_optional(self):
        """Test that code is optional"""
        form = ClientForm(data={'name': 'Test Client'})
        self.assertTrue(form.is_valid())


class ExchangeFormTests(TestCase):
    """Test cases for ExchangeForm"""
    
    def test_exchange_form_valid(self):
        """Test valid exchange form"""
        form = ExchangeForm(data={
            'name': 'Test Exchange',
            'version_name': 'v2.0',
            'code': 'EX001'
        })
        self.assertTrue(form.is_valid())
    
    def test_exchange_form_name_required(self):
        """Test that name is required"""
        form = ExchangeForm(data={'code': 'EX001'})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)


class ClientExchangeLinkFormTests(TestCase):
    """Test cases for ClientExchangeLinkForm"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.client = Client.objects.create(name='Test Client', user=self.user)
        self.exchange = Exchange.objects.create(name='Test Exchange')
    
    def test_link_form_valid(self):
        """Test valid link form"""
        form = ClientExchangeLinkForm(data={
            'client': self.client.pk,
            'exchange': self.exchange.pk,
            'my_percentage': 20,
            'friend_percentage': 10,
            'my_own_percentage': 10
        })
        self.assertTrue(form.is_valid())
    
    def test_link_form_percentage_validation(self):
        """Test percentage validation"""
        form = ClientExchangeLinkForm(data={
            'client': self.client.pk,
            'exchange': self.exchange.pk,
            'my_percentage': 20,
            'friend_percentage': 15,
            'my_own_percentage': 10
        })
        # friend + own = 25, but my_percentage = 20, should fail
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)
    
    def test_link_form_save_creates_account(self):
        """Test that form save creates account"""
        form = ClientExchangeLinkForm(data={
            'client': self.client.pk,
            'exchange': self.exchange.pk,
            'my_percentage': 20,
            'friend_percentage': 10,
            'my_own_percentage': 10
        })
        self.assertTrue(form.is_valid())
        account = form.save()
        self.assertIsNotNone(account.pk)
        self.assertEqual(account.client, self.client)
        self.assertEqual(account.exchange, self.exchange)


class FundingFormTests(TestCase):
    """Test cases for FundingForm"""
    
    def test_funding_form_valid(self):
        """Test valid funding form"""
        form = FundingForm(data={
            'amount': 1000,
            'notes': 'Test funding'
        })
        self.assertTrue(form.is_valid())
    
    def test_funding_form_amount_required(self):
        """Test that amount is required"""
        form = FundingForm(data={'notes': 'Test'})
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
    
    def test_funding_form_amount_minimum(self):
        """Test that amount must be at least 1"""
        form = FundingForm(data={'amount': 0})
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
    
    def test_funding_form_notes_optional(self):
        """Test that notes are optional"""
        form = FundingForm(data={'amount': 1000})
        self.assertTrue(form.is_valid())


class ExchangeBalanceUpdateFormTests(TestCase):
    """Test cases for ExchangeBalanceUpdateForm"""
    
    def test_balance_update_form_valid(self):
        """Test valid balance update form"""
        form = ExchangeBalanceUpdateForm(data={
            'new_balance': 1000,
            'transaction_type': 'TRADE',
            'notes': 'Test update'
        })
        self.assertTrue(form.is_valid())
    
    def test_balance_update_form_balance_required(self):
        """Test that new_balance is required"""
        form = ExchangeBalanceUpdateForm(data={
            'transaction_type': 'TRADE'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('new_balance', form.errors)
    
    def test_balance_update_form_balance_minimum(self):
        """Test that balance must be at least 0"""
        form = ExchangeBalanceUpdateForm(data={
            'new_balance': -1,
            'transaction_type': 'TRADE'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('new_balance', form.errors)


class RecordPaymentFormTests(TestCase):
    """Test cases for RecordPaymentForm"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.client = Client.objects.create(name='Test Client', user=self.user)
        self.exchange = Exchange.objects.create(name='Test Exchange')
        self.account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=100,
            loss_share_percentage=10
        )
    
    def test_record_payment_form_valid(self):
        """Test valid payment form"""
        form = RecordPaymentForm(
            data={'paid_amount': 50, 'notes': 'Test payment'},
            account=self.account
        )
        self.assertTrue(form.is_valid())
    
    def test_record_payment_form_amount_required(self):
        """Test that paid_amount is required"""
        form = RecordPaymentForm(
            data={'notes': 'Test'},
            account=self.account
        )
        self.assertFalse(form.is_valid())
        self.assertIn('paid_amount', form.errors)
    
    def test_record_payment_form_amount_exceeds_pnl(self):
        """Test that amount cannot exceed ABS(PnL)"""
        # PnL = -900, so max amount is 900
        form = RecordPaymentForm(
            data={'paid_amount': 1000},
            account=self.account
        )
        self.assertFalse(form.is_valid())
        self.assertIn('paid_amount', form.errors)
    
    def test_record_payment_form_zero_pnl(self):
        """Test that payment cannot be recorded when PnL is zero"""
        # Use get_or_create to avoid duplicate key error if account already exists
        account, created = ClientExchangeAccount.objects.get_or_create(
            client=self.client,
            exchange=self.exchange,
            defaults={
                'funding': 1000,
                'exchange_balance': 1000
            }
        )
        # Update fields if account already existed
        if not created:
            account.funding = 1000
            account.exchange_balance = 1000
            account.save()
        
        form = RecordPaymentForm(
            data={'paid_amount': 100},
            account=account
        )
        self.assertFalse(form.is_valid())
        self.assertIn('paid_amount', form.errors)


class SignupFormTests(TestCase):
    """Test cases for SignupForm"""
    
    def test_signup_form_valid(self):
        """Test valid signup form"""
        form = SignupForm(data={
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'newpass123456'
        })
        self.assertTrue(form.is_valid())
    
    def test_signup_form_username_min_length(self):
        """Test username minimum length"""
        form = SignupForm(data={
            'username': 'abc',
            'email': 'test@example.com',
            'password': 'password123456'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)
    
    def test_signup_form_password_min_length(self):
        """Test password minimum length"""
        form = SignupForm(data={
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'short'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)
    
    def test_signup_form_duplicate_username(self):
        """Test duplicate username validation"""
        User.objects.create_user(
            username='existinguser',
            email='existing@example.com',
            password='testpass'
        )
        form = SignupForm(data={
            'username': 'existinguser',
            'email': 'different@example.com',
            'password': 'password123456'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)
    
    def test_signup_form_duplicate_email(self):
        """Test duplicate email validation"""
        User.objects.create_user(
            username='user1',
            email='test@example.com',
            password='testpass'
        )
        form = SignupForm(data={
            'username': 'user2',
            'email': 'test@example.com',
            'password': 'password123456'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)


class OTPVerificationFormTests(TestCase):
    """Test cases for OTPVerificationForm"""
    
    def test_otp_form_valid(self):
        """Test valid OTP form"""
        form = OTPVerificationForm(
            data={'otp_code': '123456'},
            email='test@example.com'
        )
        self.assertTrue(form.is_valid())
    
    def test_otp_form_code_required(self):
        """Test that OTP code is required"""
        form = OTPVerificationForm(
            data={},
            email='test@example.com'
        )
        self.assertFalse(form.is_valid())
        self.assertIn('otp_code', form.errors)
    
    def test_otp_form_code_length(self):
        """Test OTP code length validation"""
        form = OTPVerificationForm(
            data={'otp_code': '12345'},  # 5 digits
            email='test@example.com'
        )
        self.assertFalse(form.is_valid())
        self.assertIn('otp_code', form.errors)
    
    def test_otp_form_code_digits_only(self):
        """Test that OTP code must contain only digits"""
        form = OTPVerificationForm(
            data={'otp_code': '12345a'},
            email='test@example.com'
        )
        self.assertFalse(form.is_valid())
        self.assertIn('otp_code', form.errors)
