"""
Comprehensive test cases for all serializers in the core application.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory

from core.serializers import (
    ClientSerializer, ExchangeSerializer,
    ClientExchangeAccountSerializer, TransactionSerializer
)
from core.models import Client, Exchange, ClientExchangeAccount, Transaction

User = get_user_model()


class ClientSerializerTests(TestCase):
    """Test cases for ClientSerializer"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.factory = APIRequestFactory()
    
    def test_client_serializer_serialization(self):
        """Test client serializer serialization"""
        client = Client.objects.create(
            name='Test Client',
            code='CLIENT001',
            user=self.user
        )
        serializer = ClientSerializer(client)
        data = serializer.data
        self.assertEqual(data['name'], 'Test Client')
        self.assertEqual(data['code'], 'CLIENT001')
    
    def test_client_serializer_deserialization(self):
        """Test client serializer deserialization"""
        data = {
            'name': 'New Client',
            'code': 'CLIENT002',
            'referred_by': 'Referrer'
        }
        serializer = ClientSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        client = serializer.save(user=self.user)
        self.assertEqual(client.name, 'New Client')
        self.assertEqual(client.code, 'CLIENT002')


class ExchangeSerializerTests(TestCase):
    """Test cases for ExchangeSerializer"""
    
    def test_exchange_serializer_serialization(self):
        """Test exchange serializer serialization"""
        exchange = Exchange.objects.create(
            name='Test Exchange',
            version_name='v2.0',
            code='EX001'
        )
        serializer = ExchangeSerializer(exchange)
        data = serializer.data
        self.assertEqual(data['name'], 'Test Exchange')
        self.assertEqual(data['version_name'], 'v2.0')
        self.assertEqual(data['code'], 'EX001')
    
    def test_exchange_serializer_deserialization(self):
        """Test exchange serializer deserialization"""
        data = {
            'name': 'New Exchange',
            'version_name': 'v1.0',
            'code': 'EX002'
        }
        serializer = ExchangeSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        exchange = serializer.save()
        self.assertEqual(exchange.name, 'New Exchange')


class ClientExchangeAccountSerializerTests(TestCase):
    """Test cases for ClientExchangeAccountSerializer"""
    
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
            exchange_balance=500,
            loss_share_percentage=10,
            profit_share_percentage=20
        )
        self.factory = APIRequestFactory()
        self.request = self.factory.get('/')
    
    def test_account_serializer_serialization(self):
        """Test account serializer serialization"""
        serializer = ClientExchangeAccountSerializer(
            self.account,
            context={'request': self.request}
        )
        data = serializer.data
        self.assertEqual(data['funding'], 1000)
        self.assertEqual(data['exchange_balance'], 500)
        self.assertIn('pnl', data)
        self.assertIn('my_share', data)
        self.assertIn('remaining_amount', data)
    
    def test_account_serializer_computed_fields(self):
        """Test that computed fields are included"""
        serializer = ClientExchangeAccountSerializer(
            self.account,
            context={'request': self.request}
        )
        data = serializer.data
        # PnL = 500 - 1000 = -500
        self.assertEqual(data['pnl'], -500)
        # Share = floor(500 * 10%) = 50
        self.assertEqual(data['my_share'], 50)


class TransactionSerializerTests(TestCase):
    """Test cases for TransactionSerializer"""
    
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
            exchange_balance=500
        )
        self.factory = APIRequestFactory()
        self.request = self.factory.get('/')
    
    def test_transaction_serializer_serialization(self):
        """Test transaction serializer serialization"""
        transaction = Transaction.objects.create(
            client_exchange=self.account,
            date='2024-01-01T00:00:00Z',
            type='TRADE',
            amount=100,
            notes='Test transaction'
        )
        serializer = TransactionSerializer(
            transaction,
            context={'request': self.request}
        )
        data = serializer.data
        self.assertEqual(data['type'], 'TRADE')
        self.assertEqual(data['amount'], 100)
        self.assertIn('type_display', data)
        self.assertIn('client_name', data)
        self.assertIn('exchange_name', data)
    
    def test_transaction_serializer_balance_fields(self):
        """Test transaction balance tracking fields"""
        transaction = Transaction.objects.create(
            client_exchange=self.account,
            date='2024-01-01T00:00:00Z',
            type='TRADE',
            amount=100,
            funding_before=1000,
            funding_after=1000,
            exchange_balance_before=500,
            exchange_balance_after=600
        )
        serializer = TransactionSerializer(
            transaction,
            context={'request': self.request}
        )
        data = serializer.data
        self.assertEqual(data['funding_before'], 1000)
        self.assertEqual(data['funding_after'], 1000)
        self.assertEqual(data['exchange_balance_before'], 500)
        self.assertEqual(data['exchange_balance_after'], 600)
