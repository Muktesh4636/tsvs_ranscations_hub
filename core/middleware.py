"""
Security middleware for rate limiting and request validation.
"""
import time
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
import logging

logger = logging.getLogger('core.security')


class RequestLoggingMiddleware(MiddlewareMixin):
    """Log all requests and responses for debugging."""
    def process_request(self, request):
        logger.info(f"REQUEST: {request.method} {request.path}")
        return None

    def process_response(self, request, response):
        logger.info(f"RESPONSE: {response.status_code} {request.path}")
        if response.status_code == 500:
            logger.error(f"500 ERROR at {request.path}")
        return response


class RateLimitMiddleware(MiddlewareMixin):
    """
    Rate limiting middleware to prevent abuse.
    Limits requests per IP address within a time window.
    """
    
    def process_request(self, request):
        # Skip rate limiting for admin and static files
        if request.path.startswith('/admin/') or request.path.startswith('/static/'):
            return None
        
        # Check if rate limiting is enabled
        if not getattr(settings, 'RATE_LIMIT_ENABLED', True):
            return None
        
        # Get client IP address
        ip_address = self.get_client_ip(request)
        
        # Rate limit key
        rate_limit_key = f'rate_limit:{ip_address}'
        
        # Get current request count
        requests = cache.get(rate_limit_key, 0)
        max_requests = getattr(settings, 'RATE_LIMIT_REQUESTS', 100)
        window = getattr(settings, 'RATE_LIMIT_WINDOW', 60)
        
        if requests >= max_requests:
            logger.warning(f'Rate limit exceeded for IP: {ip_address}')
            return HttpResponse(
                'Too many requests. Please try again later.',
                status=429,
                content_type='text/plain'
            )
        
        # Increment request count
        cache.set(rate_limit_key, requests + 1, window)
        
        return None
    
    def get_client_ip(self, request):
        """Get client IP address from request headers."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        return ip


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add additional security headers to all responses.
    """
    
    def process_response(self, request, response):
        # Content Security Policy
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        
        # X-Content-Type-Options
        response['X-Content-Type-Options'] = 'nosniff'
        
        # X-XSS-Protection
        response['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer Policy
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Permissions Policy
        response['Permissions-Policy'] = (
            'geolocation=(), microphone=(), camera=()'
        )
        
        return response




