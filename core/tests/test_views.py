"""
Comprehensive test cases for all views in the core application.
"""
from django.test import TestCase
from django.test import Client as TestClient
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

from core.models import (
    Client, Exchange, ClientExchangeAccount,
    Transaction, Settlement, EmailOTP
)

User = get_user_model()


class AuthenticationViewsTests(TestCase):
    """Test cases for authentication views"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_login_view_get(self):
        """Test login view GET request"""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/auth/login.html')
    
    def test_login_view_post_success(self):
        """Test successful login"""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))
    
    def test_login_view_post_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'wrongpass'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid username or password')
    
    def test_login_view_redirects_authenticated_user(self):
        """Test that authenticated users are redirected from login"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('login'))
        self.assertRedirects(response, reverse('dashboard'))
    
    def test_logout_view(self):
        """Test logout view"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('login'))
    
    def test_signup_view_get(self):
        """Test signup view GET request"""
        response = self.client.get(reverse('signup'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/auth/signup.html')
    
    def test_signup_view_post_valid(self):
        """Test signup with valid data"""
        response = self.client.post(reverse('signup'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'newpass123456'
        })
        # Should redirect to OTP verification
        self.assertEqual(response.status_code, 302)
        # Check OTP was created
        self.assertTrue(EmailOTP.objects.filter(email='newuser@example.com').exists())
    
    def test_signup_view_post_duplicate_username(self):
        """Test signup with duplicate username"""
        response = self.client.post(reverse('signup'), {
            'username': 'testuser',
            'email': 'different@example.com',
            'password': 'newpass123456'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')
    
    def test_health_check_view(self):
        """Test health check endpoint"""
        response = self.client.get(reverse('health_check'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('status', data)
        self.assertIn('database', data)


class ClientViewsTests(TestCase):
    """Test cases for client views"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_client_list_view(self):
        """Test client list view"""
        Client.objects.create(name='Client 1', user=self.user)
        Client.objects.create(name='Client 2', user=self.user)
        response = self.client.get(reverse('client_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/clients/list.html')
        self.assertContains(response, 'Client 1')
        self.assertContains(response, 'Client 2')
    
    def test_client_create_view_get(self):
        """Test client create view GET"""
        response = self.client.get(reverse('client_create'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/clients/create.html')
    
    def test_client_create_view_post(self):
        """Test client create view POST"""
        response = self.client.post(reverse('client_create'), {
            'name': 'New Client',
            'code': 'CLIENT001'
        })
        self.assertRedirects(response, reverse('client_list'))
        self.assertTrue(Client.objects.filter(name='New Client').exists())
    
    def test_client_detail_view(self):
        """Test client detail view"""
        client = Client.objects.create(name='Test Client', user=self.user)
        response = self.client.get(reverse('client_detail', args=[client.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/clients/detail.html')
        self.assertContains(response, 'Test Client')
    
    def test_client_delete_view(self):
        """Test client delete view"""
        client = Client.objects.create(name='Test Client', user=self.user)
        response = self.client.post(reverse('client_delete', args=[client.pk]))
        self.assertRedirects(response, reverse('client_list'))
        self.assertFalse(Client.objects.filter(pk=client.pk).exists())


class ExchangeViewsTests(TestCase):
    """Test cases for exchange views"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_exchange_list_view(self):
        """Test exchange list view"""
        Exchange.objects.create(name='Exchange 1')
        Exchange.objects.create(name='Exchange 2')
        response = self.client.get(reverse('exchange_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/exchanges/list.html')
        self.assertContains(response, 'Exchange 1')
    
    def test_exchange_create_view_get(self):
        """Test exchange create view GET"""
        response = self.client.get(reverse('exchange_create'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/exchanges/create.html')
    
    def test_exchange_create_view_post(self):
        """Test exchange create view POST"""
        response = self.client.post(reverse('exchange_create'), {
            'name': 'New Exchange',
            'code': 'EX001'
        })
        self.assertRedirects(response, reverse('exchange_list'))
        self.assertTrue(Exchange.objects.filter(name='New Exchange').exists())


class DashboardViewTests(TestCase):
    """Test cases for dashboard view"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_dashboard_view(self):
        """Test dashboard view"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/dashboard.html')
    
    def test_dashboard_view_requires_login(self):
        """Test that dashboard requires login"""
        self.client.logout()
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")


class TransactionViewsTests(TestCase):
    """Test cases for transaction views"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        self.client_obj = Client.objects.create(name='Test Client', user=self.user)
        self.exchange = Exchange.objects.create(name='Test Exchange')
        self.account = ClientExchangeAccount.objects.create(
            client=self.client_obj,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=500
        )
    
    def test_transaction_list_view(self):
        """Test transaction list view"""
        Transaction.objects.create(
            client_exchange=self.account,
            date=timezone.now(),
            type='TRADE',
            amount=100
        )
        response = self.client.get(reverse('transaction_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/transactions/list.html')
    
    def test_transaction_detail_view(self):
        """Test transaction detail view"""
        transaction = Transaction.objects.create(
            client_exchange=self.account,
            date=timezone.now(),
            type='TRADE',
            amount=100
        )
        response = self.client.get(reverse('transaction_detail', args=[transaction.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/transactions/detail.html')


class PendingPaymentsViewsTests(TestCase):
    """Test cases for pending payments views"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        self.client_obj = Client.objects.create(name='Test Client', user=self.user)
        self.exchange = Exchange.objects.create(name='Test Exchange')
        self.account = ClientExchangeAccount.objects.create(
            client=self.client_obj,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=100,
            loss_share_percentage=10
        )
    
    def test_pending_summary_view(self):
        """Test pending payments summary view"""
        response = self.client.get(reverse('pending_summary'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/pending/summary.html')
    
    def test_export_pending_csv_view(self):
        """Test export pending payments CSV"""
        response = self.client.get(reverse('export_pending_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')


class ReportViewsTests(TestCase):
    """Test cases for report views"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_report_overview_view(self):
        """Test report overview view"""
        response = self.client.get(reverse('report_overview'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/reports/overview.html')
    
    def test_report_daily_view(self):
        """Test daily report view"""
        response = self.client.get(reverse('report_daily'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/reports/daily.html')
    
    def test_report_weekly_view(self):
        """Test weekly report view"""
        response = self.client.get(reverse('report_weekly'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/reports/weekly.html')
    
    def test_report_monthly_view(self):
        """Test monthly report view"""
        response = self.client.get(reverse('report_monthly'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/reports/monthly.html')
    
    def test_report_custom_view(self):
        """Test custom report view"""
        response = self.client.get(reverse('report_custom'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/reports/custom.html')
