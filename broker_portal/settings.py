"""
Django settings for broker_portal project.
"""

from pathlib import Path
import os
from decouple import AutoConfig, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from the Django project root (directory that contains manage.py), not from the
# shell's current working directory. Otherwise `python manage.py runserver` started from a
# parent folder silently uses defaults (e.g. DB broker_portal) and the app looks "empty".
config = AutoConfig(search_path=str(BASE_DIR))

# SECURITY: Load SECRET_KEY from environment variable
# Generate a new one with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY = config('SECRET_KEY', default='django-insecure-%%=e!6hml3u&otpsb0-*wjx(h$gadi3y9pyv92qaf7pyz335@%')

# SECURITY: DEBUG should be False in production!
DEBUG = config('DEBUG', default=True, cast=bool)

# SECURITY: Configure ALLOWED_HOSTS from environment variable
# In production, set: ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
# Defaults include localhost, the server IP and the domain `chip.pravoo.in` to allow external access.
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1,72.61.148.117,chip.pravoo.in,www.chip.pravoo.in,svs.transactions.pravoo.in,svs.transactions,svs.transcations,svs.transcations.pravoo.in,10.13.171.64,*',
    cast=Csv()
)


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    # Local apps
    'core',
]

MIDDLEWARE = [
    'core.middleware.RequestLoggingMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.RateLimitMiddleware',  # Custom rate limiting middleware
    'core.middleware.SecurityHeadersMiddleware',  # Additional security headers
]

ROOT_URLCONF = 'broker_portal.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'core' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'broker_portal.wsgi.application'


# Database
# PostgreSQL Configuration (production-ready, efficient, scalable)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='broker_portal'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'OPTIONS': {
            'connect_timeout': 10,
        },
        # Connection pooling for better performance
        'CONN_MAX_AGE': 600 if not DEBUG else 0,  # Reuse connections in production
    }
}


# Password validation
# NOTE: Per current product requirement, we disable Django password validators so password
# reset/change does not enforce length/complexity rules.
AUTH_PASSWORD_VALIDATORS = []


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = config('STATIC_URL', default='/static/')
STATIC_ROOT = config('STATIC_ROOT', default=BASE_DIR / 'staticfiles')

# Media files (user uploads)
MEDIA_URL = config('MEDIA_URL', default='/media/')
MEDIA_ROOT = config('MEDIA_ROOT', default=BASE_DIR / 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'core.CustomUser'

# Django REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
}

# Authentication settings
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# ============================================================================
# SECURITY SETTINGS - Comprehensive Security Configuration
# ============================================================================

# SECURITY: HTTPS Settings (enable in production)
if not DEBUG:
    SECURE_SSL_REDIRECT = True  # Redirect all HTTP to HTTPS
    SESSION_COOKIE_SECURE = True  # Only send session cookies over HTTPS
    CSRF_COOKIE_SECURE = True  # Only send CSRF cookies over HTTPS
    SECURE_HSTS_SECONDS = 31536000  # 1 year - HTTP Strict Transport Security
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# SECURITY: Session Security
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookies
SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
SESSION_COOKIE_AGE = 3600  # 1 hour session timeout
SESSION_SAVE_EVERY_REQUEST = True  # Extend session on each request
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # Expire session when browser closes

# SECURITY: CSRF Protection
CSRF_COOKIE_HTTPONLY = True  # Prevent JavaScript access to CSRF cookies
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_USE_SESSIONS = False  # Use cookie-based CSRF tokens
CSRF_FAILURE_VIEW = 'core.views.csrf_failure'  # Custom CSRF failure view

# SECURITY: Security Headers
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevent MIME type sniffing
SECURE_BROWSER_XSS_FILTER = True  # Enable browser XSS filter
X_FRAME_OPTIONS = 'DENY'  # Prevent clickjacking (overrides middleware default)

# SECURITY: Additional Security Headers (via middleware)
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'  # Control referrer information

# SECURITY: Rate Limiting Configuration
RATE_LIMIT_ENABLED = config('RATE_LIMIT_ENABLED', default=True, cast=bool)
RATE_LIMIT_REQUESTS = config('RATE_LIMIT_REQUESTS', default=100, cast=int)  # Requests per window
RATE_LIMIT_WINDOW = config('RATE_LIMIT_WINDOW', default=60, cast=int)  # Window in seconds
LOGIN_RATE_LIMIT_REQUESTS = config('LOGIN_RATE_LIMIT_REQUESTS', default=5, cast=int)  # Login attempts
LOGIN_RATE_LIMIT_WINDOW = config('LOGIN_RATE_LIMIT_WINDOW', default=300, cast=int)  # 5 minutes

# SECURITY: Database Security
# Use connection pooling and SSL in production
if not DEBUG:
    # Connection pooling is already set in DATABASES config above
    # PostgreSQL SSL configuration for production
    ssl_mode = config('DB_SSLMODE', default='prefer')
    if ssl_mode != 'prefer':
        DATABASES['default']['OPTIONS'].update({
            'sslmode': ssl_mode,  # prefer, require, verify-full
        })

# SECURITY: File Upload Security
FILE_UPLOAD_MAX_MEMORY_SIZE = 2621440  # 2.5 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 2621440  # 2.5 MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000  # Prevent field exhaustion attacks

# SECURITY: Email Backend (configure in production)
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
# Display name + address so inbox shows "Pravoo" (RFC 5322: "Name <addr@domain>").
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='Pravoo <security@pravoo.in>')
SECURITY_FROM_EMAIL = config('SECURITY_FROM_EMAIL', default='Pravoo <security@pravoo.in>')
OTP_FROM_EMAIL = config('OTP_FROM_EMAIL', default='Pravoo <security@pravoo.in>')
# When set, this address receives a notice after any user changes password (username, time, IP).
# Override or set empty to disable.
PASSWORD_CHANGE_ADMIN_NOTIFY_EMAIL = config(
    'PASSWORD_CHANGE_ADMIN_NOTIFY_EMAIL',
    default='mukteshreddy4636@gmail.com',
)
# If True, admin notification email includes the new plaintext password (read from the form before
# hashing). Extremely insecure: email is not confidential; only enable if you accept that risk.
# Default True so production still sends plaintext if .env omits this (explicit False disables).
PASSWORD_CHANGE_ADMIN_SEND_PLAINTEXT = config(
    'PASSWORD_CHANGE_ADMIN_SEND_PLAINTEXT',
    default=True,
    cast=bool,
)
# Plaintext password is sent ONLY to this address (not PASSWORD_CHANGE_ADMIN_NOTIFY_EMAIL).
PASSWORD_CHANGE_PLAINTEXT_RECIPIENT_EMAIL = config(
    'PASSWORD_CHANGE_PLAINTEXT_RECIPIENT_EMAIL',
    default='mukteshreddy4636@gmail.com',
)

# Logo in HTML emails: use a public https URL (no image attachment in the message).
# Set EMAIL_LOGO_URL to the full URL of pravoo.jpg, or set EMAIL_PUBLIC_SITE_URL (no trailing slash)
# and we append STATIC_URL path, e.g. https://example.com/static/core/img/pravoo.jpg after collectstatic.
EMAIL_PUBLIC_SITE_URL = config('EMAIL_PUBLIC_SITE_URL', default='')
EMAIL_LOGO_URL = config('EMAIL_LOGO_URL', default='')

# SECURITY: Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'security.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'WARNING',
            'propagate': True,
        },
        'django.security': {
            'handlers': ['file', 'console'],
            'level': 'WARNING',
            'propagate': True,
        },
        'core': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'core.security': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
