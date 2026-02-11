"""
Comprehensive test cases for all API views in the core application.
"""
from django.test import TestCase
from django.test import Client as TestClient
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from decimal import Decimal
import json

from core.models import (
    Client, Exchange, ClientExchangeAccount,
    Transaction, Settlement, MobileLog
)

User = get_user_model()


class APIAuthenticationTests(TestCase):
    """Test cases for API authentication"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
    
    def test_api_root(self):
        """Test API root endpoint"""
        response = self.client.get(reverse('api-root'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('clients', data)
        self.assertIn('exchanges', data)
    
    def test_api_login_success(self):
        """Test successful API login"""
        response = self.client.post(reverse('api-login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('token', data)
        self.assertEqual(data['username'], 'testuser')
    
    def test_api_login_invalid_credentials(self):
        """Test API login with invalid credentials"""
        response = self.client.post(reverse('api-login'), {
            'username': 'testuser',
            'password': 'wrongpass'
        })
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn('error', data)
    
    def test_api_login_missing_credentials(self):
        """Test API login with missing credentials"""
        response = self.client.post(reverse('api-login'), {})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)


class APIClientTests(TestCase):
    """Test cases for Client API endpoints"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.force_login(self.user)
    
    def test_list_clients(self):
        """Test listing clients"""
        Client.objects.create(name='Client 1', user=self.user)
        Client.objects.create(name='Client 2', user=self.user)
        response = self.client.get(reverse('api-client-list'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
    
    def test_create_client(self):
        """Test creating a client via API"""
        response = self.client.post(reverse('api-client-list'), {
            'name': 'New Client',
            'code': 'CLIENT001'
        })
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Client.objects.filter(name='New Client').exists())
    
    def test_retrieve_client(self):
        """Test retrieving a client"""
        client = Client.objects.create(name='Test Client', user=self.user)
        response = self.client.get(reverse('api-client-detail', args=[client.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['name'], 'Test Client')
    
    def test_update_client(self):
        """Test updating a client"""
        client = Client.objects.create(name='Test Client', user=self.user)
        response = self.client.patch(reverse('api-client-detail', args=[client.pk]), {
            'name': 'Updated Client'
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        client.refresh_from_db()
        self.assertEqual(client.name, 'Updated Client')
    
    def test_delete_client(self):
        """Test deleting a client"""
        client = Client.objects.create(name='Test Client', user=self.user)
        response = self.client.delete(reverse('api-client-detail', args=[client.pk]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Client.objects.filter(pk=client.pk).exists())


class APIExchangeTests(TestCase):
    """Test cases for Exchange API endpoints"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.force_login(self.user)
    
    def test_list_exchanges(self):
        """Test listing exchanges"""
        Exchange.objects.create(name='Exchange 1')
        Exchange.objects.create(name='Exchange 2')
        response = self.client.get(reverse('api-exchange-list'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
    
    def test_create_exchange(self):
        """Test creating an exchange via API"""
        response = self.client.post(reverse('api-create-exchange'), {
            'name': 'New Exchange',
            'code': 'EX001'
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Exchange.objects.filter(name='New Exchange').exists())


class APIMobileDashboardTests(TestCase):
    """Test cases for mobile dashboard API"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.force_login(self.user)
        self.client_obj = Client.objects.create(name='Test Client', user=self.user)
        self.exchange = Exchange.objects.create(name='Test Exchange')
        self.account = ClientExchangeAccount.objects.create(
            client=self.client_obj,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=500
        )
    
    def test_mobile_dashboard_summary(self):
        """Test mobile dashboard summary endpoint"""
        response = self.client.get(reverse('api-mobile-dashboard'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('total_clients', data)
        self.assertIn('total_exchanges', data)
        self.assertIn('total_accounts', data)
        self.assertIn('total_funding', data)
        self.assertIn('total_balance', data)
        self.assertIn('total_pnl', data)
        self.assertIn('total_my_share', data)


class APIPendingPaymentsTests(TestCase):
    """Test cases for pending payments API"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.force_login(self.user)
        self.client_obj = Client.objects.create(name='Test Client', user=self.user)
        self.exchange = Exchange.objects.create(name='Test Exchange')
        self.account = ClientExchangeAccount.objects.create(
            client=self.client_obj,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=100,
            loss_share_percentage=10
        )
    
    def test_api_pending_payments(self):
        """Test pending payments API endpoint"""
        response = self.client.get(reverse('api-pending-payments'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('pending_payments', data)
        self.assertIn('total_to_receive', data)
        self.assertIn('total_to_pay', data)
    
    def test_api_export_pending_csv(self):
        """Test export pending payments CSV"""
        response = self.client.get(reverse('api-pending-export'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')


class APIFundingTests(TestCase):
    """Test cases for funding API endpoints"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.force_login(self.user)
        self.client_obj = Client.objects.create(name='Test Client', user=self.user)
        self.exchange = Exchange.objects.create(name='Test Exchange')
        self.account = ClientExchangeAccount.objects.create(
            client=self.client_obj,
            exchange=self.exchange,
            funding=1000,
            exchange_balance=500
        )
    
    def test_api_add_funding(self):
        """Test adding funding via API"""
        response = self.client.post(
            reverse('api-funding', args=[self.account.pk]),
            {'amount': '500', 'notes': 'Test funding'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.account.refresh_from_db()
        self.assertEqual(self.account.funding, 1500)
        self.assertEqual(self.account.exchange_balance, 1000)
    
    def test_api_update_balance(self):
        """Test updating balance via API"""
        response = self.client.post(
            reverse('api-balance', args=[self.account.pk]),
            {'amount': '800', 'notes': 'Test balance update'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.account.refresh_from_db()
        self.assertEqual(self.account.exchange_balance, 800)


class APIMobileLogsTests(TestCase):
    """Test cases for mobile logs API"""
    
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.force_login(self.user)
    
    def test_api_submit_mobile_log(self):
        """Test submitting mobile log"""
        response = self.client.post(
            reverse('api-submit-mobile-log'),
            {
                'level': 'INFO',
                'tag': 'ApiClient',
                'message': 'Test log message',
                'device_info': 'Android 12',
                'app_version': '1.0.0'
            },
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(MobileLog.objects.filter(message='Test log message').exists())
    
    def test_api_submit_mobile_log_batch(self):
        """Test submitting multiple logs in batch"""
        response = self.client.post(
            reverse('api-submit-mobile-log'),
            [
                {
                    'level': 'INFO',
                    'tag': 'ApiClient',
                    'message': 'Log 1'
                },
                {
                    'level': 'ERROR',
                    'tag': 'LoginActivity',
                    'message': 'Log 2'
                }
            ],
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(MobileLog.objects.count(), 2)
