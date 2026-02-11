"""
Comprehensive test cases for all middleware in the core application.
"""
from django.test import SimpleTestCase, RequestFactory  # Use SimpleTestCase - no database needed
from django.http import HttpResponse
from django.core.cache import cache
from django.conf import settings

from core.middleware import (
    RequestLoggingMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware
)


class RequestLoggingMiddlewareTests(SimpleTestCase):
    """Test cases for RequestLoggingMiddleware"""
    
    def setUp(self):
        self.middleware = RequestLoggingMiddleware(lambda request: HttpResponse())
        self.factory = RequestFactory()
    
    def test_process_request(self):
        """Test request processing"""
        request = self.factory.get('/test/')
        response = self.middleware.process_request(request)
        # Should return None to continue processing
        self.assertIsNone(response)
    
    def test_process_response(self):
        """Test response processing"""
        request = self.factory.get('/test/')
        response = HttpResponse('Test')
        result = self.middleware.process_response(request, response)
        self.assertEqual(result.status_code, 200)
    
    def test_process_response_500_error(self):
        """Test response processing for 500 error"""
        request = self.factory.get('/test/')
        response = HttpResponse('Error', status=500)
        result = self.middleware.process_response(request, response)
        self.assertEqual(result.status_code, 500)


class RateLimitMiddlewareTests(SimpleTestCase):
    """Test cases for RateLimitMiddleware"""
    
    def setUp(self):
        self.middleware = RateLimitMiddleware(lambda request: HttpResponse())
        self.factory = RequestFactory()
        cache.clear()
    
    def test_process_request_normal(self):
        """Test normal request processing"""
        request = self.factory.get('/test/')
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        response = self.middleware.process_request(request)
        # Should return None to continue processing
        self.assertIsNone(response)
    
    def test_process_request_rate_limit_exceeded(self):
        """Test rate limit exceeded"""
        # Set rate limit to 1 request
        settings.RATE_LIMIT_REQUESTS = 1
        settings.RATE_LIMIT_WINDOW = 60
        
        request = self.factory.get('/test/')
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        
        # First request should pass
        response1 = self.middleware.process_request(request)
        self.assertIsNone(response1)
        
        # Second request should be blocked
        response2 = self.middleware.process_request(request)
        self.assertIsNotNone(response2)
        self.assertEqual(response2.status_code, 429)
    
    def test_process_request_admin_bypass(self):
        """Test that admin paths bypass rate limiting"""
        request = self.factory.get('/admin/')
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        response = self.middleware.process_request(request)
        # Should return None (bypassed)
        self.assertIsNone(response)
    
    def test_get_client_ip_from_x_forwarded_for(self):
        """Test getting client IP from X-Forwarded-For header"""
        request = self.factory.get('/test/')
        request.META['HTTP_X_FORWARDED_FOR'] = '192.168.1.1, 10.0.0.1'
        ip = self.middleware.get_client_ip(request)
        self.assertEqual(ip, '192.168.1.1')
    
    def test_get_client_ip_from_remote_addr(self):
        """Test getting client IP from REMOTE_ADDR"""
        request = self.factory.get('/test/')
        request.META['REMOTE_ADDR'] = '192.168.1.1'
        ip = self.middleware.get_client_ip(request)
        self.assertEqual(ip, '192.168.1.1')
    
    def test_get_client_ip_default(self):
        """Test default IP when no headers present"""
        request = self.factory.get('/test/')
        ip = self.middleware.get_client_ip(request)
        self.assertEqual(ip, '127.0.0.1')


class SecurityHeadersMiddlewareTests(SimpleTestCase):
    """Test cases for SecurityHeadersMiddleware"""
    
    def setUp(self):
        self.middleware = SecurityHeadersMiddleware(lambda request: HttpResponse())
        self.factory = RequestFactory()
    
    def test_process_response_adds_security_headers(self):
        """Test that security headers are added to response"""
        request = self.factory.get('/test/')
        response = HttpResponse('Test')
        result = self.middleware.process_response(request, response)
        
        # Check security headers
        self.assertIn('Content-Security-Policy', result)
        self.assertIn('X-Content-Type-Options', result)
        self.assertEqual(result['X-Content-Type-Options'], 'nosniff')
        self.assertIn('X-XSS-Protection', result)
        self.assertEqual(result['X-XSS-Protection'], '1; mode=block')
        self.assertIn('Referrer-Policy', result)
        self.assertIn('Permissions-Policy', result)
    
    def test_content_security_policy(self):
        """Test Content Security Policy header"""
        request = self.factory.get('/test/')
        response = HttpResponse('Test')
        result = self.middleware.process_response(request, response)
        
        csp = result['Content-Security-Policy']
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertIn("style-src 'self'", csp)
