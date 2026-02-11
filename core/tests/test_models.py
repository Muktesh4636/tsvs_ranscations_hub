"""
Comprehensive test cases for all models in the core application.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

from core.models import (
    CustomUser, Client, Exchange, ClientExchangeAccount,
    Settlement, Transaction, EmailOTP, MobileLog,
    ClientExchangeReportConfig
)

User = get_user_model()


class CustomUserModelTests(TestCase):
    """Test cases for CustomUser model"""
    
    def test_create_user_with_valid_username(self):
        """Test creating a user with valid username"""
        user = CustomUser.objects.create_user(
            username='testuser123',
            email='test@example.com',
            password='testpass123'
        )
        self.assertEqual(user.username, 'testuser123')
        self.assertTrue(user.check_password('testpass123'))
    
    def test_username_min_length_validation(self):
        """Test username minimum length validation"""
        user = CustomUser(username='abc', email='test@example.com')
        with self.assertRaises(ValidationError):
            user.full_clean()
    
    def test_username_max_length_validation(self):
        """Test username maximum length validation"""
        user = CustomUser(
            username='a' * 31,
            email='test@example.com'
        )
        with self.assertRaises(ValidationError):
            user.full_clean()
    
    def test_username_allows_special_characters(self):
        """Test that username allows special characters"""
        user = CustomUser.objects.create_user(
            username='user@123!',
            email='test@example.com',
            password='testpass'
        )
        self.assertEqual(user.username, 'user@123!')
    
    def test_username_uniqueness(self):
        """Test username uniqueness constraint"""
        CustomUser.objects.create_user(
            username='uniqueuser',
            email='test1@example.com',
            password='testpass'
        )
        with self.assertRaises(Exception):
            CustomUser.objects.create_user(
                username='uniqueuser',
                email='test2@example.com',
                password='testpass'
            )


class ClientModelTests(TestCase):
    """Test cases for Client model"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
    
    def test_create_client_with_name(self):
        """Test creating a client with just a name"""
        client = Client.objects.create(
            name='Test Client',
            user=self.user
        )
        self.assertEqual(client.name, 'Test Client')
        self.assertIsNone(client.code)
    
    def test_create_client_with_code(self):
        """Test creating a client with code"""
        client = Client.objects.create(
            name='Test Client',
            code='CLIENT001',
            user=self.user
        )
        self.assertEqual(client.code, 'CLIENT001')
    
    def test_client_code_uniqueness(self):
        """Test that client code must be unique"""
        Client.objects.create(
            name='Client 1',
            code='CODE001',
            user=self.user
        )
        with self.assertRaises(Exception):
            Client.objects.create(
                name='Client 2',
                code='CODE001',
                user=self.user
            )
    
    def test_client_code_empty_string_converted_to_none(self):
        """Test that empty string code is converted to None"""
        client = Client.objects.create(
            name='Test Client',
            code='',
            user=self.user
        )
        client.refresh_from_db()
        self.assertIsNone(client.code)
    
    def test_client_code_whitespace_stripped(self):
        """Test that whitespace in code is stripped"""
        client = Client.objects.create(
            name='Test Client',
            code='  CODE001  ',
            user=self.user
        )
        self.assertEqual(client.code, 'CODE001')
    
    def test_multiple_clients_with_null_code(self):
        """Test that multiple clients can have NULL code"""
        client1 = Client.objects.create(name='Client 1', user=self.user)
        client2 = Client.objects.create(name='Client 2', user=self.user)
        self.assertIsNone(client1.code)
        self.assertIsNone(client2.code)
    
    def test_client_str_representation(self):
        """Test client string representation"""
        client = Client.objects.create(name='Test Client', user=self.user)
        self.assertEqual(str(client), 'Test Client')


class ExchangeModelTests(TestCase):
    """Test cases for Exchange model"""
    
    def test_create_exchange_with_name(self):
        """Test creating an exchange with name"""
        exchange = Exchange.objects.create(name='Test Exchange')
        self.assertEqual(exchange.name, 'Test Exchange')
    
    def test_exchange_name_case_insensitive_uniqueness(self):
        """Test that exchange names must be unique case-insensitively"""
        Exchange.objects.create(name='Test Exchange')
        with self.assertRaises(ValidationError):
            exchange = Exchange(name='test exchange')
            exchange.full_clean()
            exchange.save()
    
    def test_exchange_code_uniqueness(self):
        """Test that exchange code must be unique"""
        Exchange.objects.create(name='Exchange 1', code='EX001')
        with self.assertRaises(Exception):
            Exchange.objects.create(name='Exchange 2', code='EX001')
    
    def test_exchange_version_name(self):
        """Test exchange version name field"""
        exchange = Exchange.objects.create(
            name='Test Exchange',
            version_name='v2.0'
        )
        self.assertEqual(exchange.version_name, 'v2.0')
    
    def test_exchange_str_representation(self):
        """Test exchange string representation"""
        exchange = Exchange.objects.create(name='Test Exchange')
        self.assertEqual(str(exchange), 'Test Exchange')


class ClientExchangeAccountModelTests(TestCase):
    """Test cases for ClientExchangeAccount model"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.client = Client.objects.create(name='Test Client', user=self.user)
        self.exchange = Exchange.objects.create(name='Test Exchange')
    
    def test_create_account(self):
        """Test creating a client exchange account"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=500
        )
        self.assertEqual(account.funding, 1000)
        self.assertEqual(account.exchange_balance, 500)
    
    def test_account_multiple_links_allowed(self):
        """Test that a client can be linked to the same exchange multiple times"""
        ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000
        )
        # This should now succeed instead of raising an exception
        account2 = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=2000
        )
        self.assertEqual(ClientExchangeAccount.objects.filter(client=self.client, exchange=self.exchange).count(), 2)
        self.assertEqual(account2.funding, 2000)
    
    def test_compute_client_pnl_loss(self):
        """Test PnL calculation for loss case"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=500
        )
        pnl = account.compute_client_pnl()
        self.assertEqual(pnl, -500)
    
    def test_compute_client_pnl_profit(self):
        """Test PnL calculation for profit case"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=500,
            exchange_balance=1000
        )
        pnl = account.compute_client_pnl()
        self.assertEqual(pnl, 500)
    
    def test_compute_client_pnl_zero(self):
        """Test PnL calculation for zero case"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=1000
        )
        pnl = account.compute_client_pnl()
        self.assertEqual(pnl, 0)
    
    def test_get_share_percentage_loss(self):
        """Test share percentage selection for loss"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=100,
            loss_share_percentage=10,
            profit_share_percentage=20
        )
        share_pct = account.get_share_percentage()
        self.assertEqual(share_pct, 10)
    
    def test_get_share_percentage_profit(self):
        """Test share percentage selection for profit"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=500,
            exchange_balance=1000,
            loss_share_percentage=10,
            profit_share_percentage=20
        )
        share_pct = account.get_share_percentage()
        self.assertEqual(share_pct, 20)
    
    def test_get_share_percentage_fallback_to_my_percentage(self):
        """Test fallback to my_percentage when specific percentage is 0"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=100,
            loss_share_percentage=0,
            profit_share_percentage=0,
            my_percentage=15
        )
        share_pct = account.get_share_percentage()
        self.assertEqual(share_pct, 15)
    
    def test_compute_my_share_loss(self):
        """Test share calculation for loss"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=100,
            loss_share_percentage=10
        )
        share = account.compute_my_share()
        # PnL = -900, Share% = 10%, Share = floor(90) = 90
        self.assertEqual(share, 90)
    
    def test_compute_my_share_profit(self):
        """Test share calculation for profit"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=500,
            exchange_balance=1000,
            profit_share_percentage=20
        )
        share = account.compute_my_share()
        # PnL = +500, Share% = 20%, Share = floor(100) = 100
        self.assertEqual(share, 100)
    
    def test_compute_my_share_zero_pnl(self):
        """Test share calculation for zero PnL"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=1000,
            loss_share_percentage=10
        )
        share = account.compute_my_share()
        self.assertEqual(share, 0)
    
    def test_lock_initial_share_if_needed(self):
        """Test locking initial share"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=100,
            loss_share_percentage=10
        )
        account.lock_initial_share_if_needed()
        account.refresh_from_db()  # Reload from database after save
        self.assertIsNotNone(account.locked_initial_final_share)
        self.assertIsNone(account.cycle_start_date)  # cycle_start_date should remain None
        self.assertEqual(account.locked_initial_final_share, 0)  # Expect 0 based on user requirements
    
    def test_loss_share_percentage_immutability(self):
        """Test that loss share percentage cannot be changed after data exists"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=100,
            loss_share_percentage=10
        )
        # Create a transaction to mark data exists
        Transaction.objects.create(
            client_exchange=account,
            date=timezone.now(),
            type='TRADE',
            amount=100
        )
        # Try to change loss share percentage
        account.loss_share_percentage = 20
        with self.assertRaises(ValidationError):
            account.full_clean()
    
    def test_account_str_representation(self):
        """Test account string representation"""
        account = ClientExchangeAccount.objects.create(
            client=self.client,
            exchange=self.exchange,
            funding=1000
        )
        self.assertEqual(str(account), f"{self.client.name} - {self.exchange.name}")


class SettlementModelTests(TestCase):
    """Test cases for Settlement model"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
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
            exchange_balance=100
        )
    
    def test_create_settlement(self):
        """Test creating a settlement"""
        settlement = Settlement.objects.create(
            client_exchange=self.account,
            amount=100,
            date=timezone.now(),
            notes='Test settlement'
        )
        self.assertEqual(settlement.amount, 100)
        self.assertEqual(settlement.client_exchange, self.account)
    
    def test_settlement_amount_minimum(self):
        """Test that settlement amount must be at least 1"""
        settlement = Settlement(
            client_exchange=self.account,
            amount=0,
            date=timezone.now()
        )
        with self.assertRaises(ValidationError):
            settlement.full_clean()
    
    def test_settlement_str_representation(self):
        """Test settlement string representation"""
        settlement = Settlement.objects.create(
            client_exchange=self.account,
            amount=100,
            date=timezone.now()
        )
        self.assertIn('Settlement:', str(settlement))
        self.assertIn('100', str(settlement))


class TransactionModelTests(TestCase):
    """Test cases for Transaction model"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
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
            exchange_balance=100
        )
    
    def test_create_transaction(self):
        """Test creating a transaction"""
        transaction = Transaction.objects.create(
            client_exchange=self.account,
            date=timezone.now(),
            type='TRADE',
            amount=100,
            notes='Test transaction'
        )
        self.assertEqual(transaction.type, 'TRADE')
        self.assertEqual(transaction.amount, 100)
    
    def test_transaction_sequence_no_auto_increment(self):
        """Test that sequence_no auto-increments per account"""
        txn1 = Transaction.objects.create(
            client_exchange=self.account,
            date=timezone.now(),
            type='TRADE',
            amount=100
        )
        txn2 = Transaction.objects.create(
            client_exchange=self.account,
            date=timezone.now(),
            type='TRADE',
            amount=200
        )
        self.assertEqual(txn2.sequence_no, txn1.sequence_no + 1)
    
    def test_transaction_balance_tracking(self):
        """Test transaction balance tracking fields"""
        transaction = Transaction.objects.create(
            client_exchange=self.account,
            date=timezone.now(),
            type='TRADE',
            amount=100,
            funding_before=1000,
            funding_after=1000,
            exchange_balance_before=100,
            exchange_balance_after=200
        )
        self.assertEqual(transaction.funding_before, 1000)
        self.assertEqual(transaction.exchange_balance_after, 200)
    
    def test_transaction_str_representation(self):
        """Test transaction string representation"""
        transaction = Transaction.objects.create(
            client_exchange=self.account,
            date=timezone.now(),
            type='TRADE',
            amount=100
        )
        self.assertIn('TRADE', str(transaction))


class EmailOTPModelTests(TestCase):
    """Test cases for EmailOTP model"""
    
    def test_create_otp(self):
        """Test creating an OTP"""
        otp = EmailOTP.objects.create(
            email='test@example.com',
            username='testuser',
            otp_code='123456',
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        self.assertEqual(otp.email, 'test@example.com')
        self.assertEqual(otp.otp_code, '123456')
        self.assertFalse(otp.is_verified)
    
    def test_otp_is_expired(self):
        """Test OTP expiration check"""
        otp = EmailOTP.objects.create(
            email='test@example.com',
            username='testuser',
            otp_code='123456',
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        self.assertTrue(otp.is_expired())
    
    def test_otp_not_expired(self):
        """Test that valid OTP is not expired"""
        otp = EmailOTP.objects.create(
            email='test@example.com',
            username='testuser',
            otp_code='123456',
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        self.assertFalse(otp.is_expired())
    
    def test_email_uniqueness(self):
        """Test that email must be unique"""
        EmailOTP.objects.create(
            email='test@example.com',
            username='testuser',
            otp_code='123456',
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        with self.assertRaises(Exception):
            EmailOTP.objects.create(
                email='test@example.com',
                username='testuser2',
                otp_code='654321',
                expires_at=timezone.now() + timedelta(minutes=10)
            )


class MobileLogModelTests(TestCase):
    """Test cases for MobileLog model"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
    
    def test_create_mobile_log(self):
        """Test creating a mobile log"""
        log = MobileLog.objects.create(
            user=self.user,
            level='INFO',
            tag='ApiClient',
            message='Test log message',
            device_info='Android 12',
            app_version='1.0.0'
        )
        self.assertEqual(log.level, 'INFO')
        self.assertEqual(log.tag, 'ApiClient')
        self.assertEqual(log.message, 'Test log message')
    
    def test_mobile_log_without_user(self):
        """Test creating mobile log without user"""
        log = MobileLog.objects.create(
            level='ERROR',
            tag='LoginActivity',
            message='Error occurred',
            stack_trace='Traceback...'
        )
        self.assertIsNone(log.user)
        self.assertEqual(log.level, 'ERROR')
    
    def test_mobile_log_str_representation(self):
        """Test mobile log string representation"""
        log = MobileLog.objects.create(
            level='ERROR',
            tag='ApiClient',
            message='Test error message'
        )
        self.assertIn('ERROR', str(log))
        self.assertIn('ApiClient', str(log))


class ClientExchangeReportConfigModelTests(TestCase):
    """Test cases for ClientExchangeReportConfig model"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
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
            my_percentage=20
        )
    
    def test_create_report_config(self):
        """Test creating report config"""
        config = ClientExchangeReportConfig.objects.create(
            client_exchange=self.account,
            friend_percentage=10,
            my_own_percentage=10
        )
        self.assertEqual(config.friend_percentage, 10)
        self.assertEqual(config.my_own_percentage, 10)
    
    def test_report_config_validation(self):
        """Test report config validation"""
        config = ClientExchangeReportConfig(
            client_exchange=self.account,
            friend_percentage=15,
            my_own_percentage=10
        )
        # friend + own = 25, but my_percentage = 20, should fail
        with self.assertRaises(ValidationError):
            config.full_clean()
    
    def test_compute_friend_share(self):
        """Test friend share calculation"""
        config = ClientExchangeReportConfig.objects.create(
            client_exchange=self.account,
            friend_percentage=10,
            my_own_percentage=10
        )
        # PnL = -900, friend_share = 900 * 10% = 90
        friend_share = config.compute_friend_share()
        self.assertEqual(friend_share, 90)
    
    def test_compute_my_own_share(self):
        """Test my own share calculation"""
        config = ClientExchangeReportConfig.objects.create(
            client_exchange=self.account,
            friend_percentage=10,
            my_own_percentage=10
        )
        # PnL = -900, my_own_share = 900 * 10% = 90
        my_own_share = config.compute_my_own_share()
        self.assertEqual(my_own_share, 90)
