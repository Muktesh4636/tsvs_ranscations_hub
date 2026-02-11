# Test Suite Documentation

## Overview

This directory contains comprehensive test cases for all components of the core application. The test suite is organized into separate modules for better maintainability and clarity.

## Test Structure

```
core/tests/
├── __init__.py
├── test_models.py          # Model tests (CustomUser, Client, Exchange, etc.)
├── test_views.py           # View tests (Authentication, CRUD, Reports)
├── test_api_views.py       # API endpoint tests (REST API)
├── test_forms.py           # Form validation tests
├── test_serializers.py     # DRF serializer tests
├── test_middleware.py      # Middleware tests (Rate limiting, Security)
├── test_templatetags.py    # Template tag tests (Filters)
├── test_helpers.py         # Helper function tests
└── README.md               # This file
```

## Running Tests

### Run All Tests

```bash
# From project root
python manage.py test core

# Or run specific test module
python manage.py test core.tests.test_models
python manage.py test core.tests.test_views
python manage.py test core.tests.test_api_views
```

### Run Specific Test Classes

```bash
# Run model tests
python manage.py test core.tests.test_models.CustomUserModelTests

# Run view tests
python manage.py test core.tests.test_views.AuthenticationViewsTests

# Run API tests
python manage.py test core.tests.test_api_views.APIAuthenticationTests
```

### Run Specific Test Methods

```bash
# Run a single test method
python manage.py test core.tests.test_models.CustomUserModelTests.test_create_user_with_valid_username
```

### Run with Verbose Output

```bash
python manage.py test core --verbosity=2
```

### Run with Coverage

```bash
# Install coverage if not already installed
pip install coverage

# Run tests with coverage
coverage run --source='.' manage.py test core
coverage report
coverage html  # Generate HTML report
```

## Test Coverage

### Models (`test_models.py`)
- ✅ CustomUser: Username validation, uniqueness, special characters
- ✅ Client: CRUD operations, code uniqueness, empty string handling
- ✅ Exchange: Name uniqueness (case-insensitive), version support
- ✅ ClientExchangeAccount: PnL calculation, share calculation, locking mechanism
- ✅ Settlement: Amount validation, date tracking
- ✅ Transaction: Sequence numbers, balance tracking
- ✅ EmailOTP: Expiration, verification
- ✅ MobileLog: Log levels, device info
- ✅ ClientExchangeReportConfig: Percentage validation, share calculations

### Views (`test_views.py`)
- ✅ Authentication: Login, logout, signup, OTP verification
- ✅ Client Views: List, create, detail, delete
- ✅ Exchange Views: List, create
- ✅ Dashboard: Access control, data display
- ✅ Transaction Views: List, detail
- ✅ Pending Payments: Summary, CSV export
- ✅ Reports: Overview, daily, weekly, monthly, custom

### API Views (`test_api_views.py`)
- ✅ Authentication: Login, token generation
- ✅ Client API: CRUD operations
- ✅ Exchange API: List, create
- ✅ Mobile Dashboard: Summary endpoint
- ✅ Pending Payments API: List, CSV export
- ✅ Funding API: Add funding, update balance
- ✅ Mobile Logs: Submit logs, batch submission

### Forms (`test_forms.py`)
- ✅ ClientForm: Validation, required fields
- ✅ ExchangeForm: Name validation
- ✅ ClientExchangeLinkForm: Percentage validation, account creation
- ✅ FundingForm: Amount validation
- ✅ ExchangeBalanceUpdateForm: Balance validation
- ✅ RecordPaymentForm: Amount limits, PnL validation
- ✅ SignupForm: Username/password validation, duplicate checks
- ✅ OTPVerificationForm: Code format validation

### Serializers (`test_serializers.py`)
- ✅ ClientSerializer: Serialization, deserialization
- ✅ ExchangeSerializer: Field mapping
- ✅ ClientExchangeAccountSerializer: Computed fields (PnL, share, remaining)
- ✅ TransactionSerializer: Balance tracking fields

### Middleware (`test_middleware.py`)
- ✅ RequestLoggingMiddleware: Request/response logging
- ✅ RateLimitMiddleware: Rate limiting, IP detection, admin bypass
- ✅ SecurityHeadersMiddleware: Security headers (CSP, XSS protection, etc.)

### Template Tags (`test_templatetags.py`)
- ✅ abs filter: Absolute value calculation
- ✅ indian_number_format: Indian number system formatting
- ✅ currency_inr: Currency formatting with ₹ symbol
- ✅ currency_inr_decimal: Decimal currency formatting

### Helper Functions (`test_helpers.py`)
- ✅ calculate_display_remaining: Sign calculation for display
- ✅ get_settlement_info_for_display: Settlement info aggregation

## Test Best Practices

1. **Isolation**: Each test is independent and doesn't rely on other tests
2. **Setup/Teardown**: Use `setUp()` and `tearDown()` methods for test fixtures
3. **Naming**: Test methods should be descriptive: `test_<what>_<condition>`
4. **Assertions**: Use specific assertions (`assertEqual`, `assertTrue`, etc.)
5. **Coverage**: Aim for high coverage but focus on critical paths
6. **Speed**: Keep tests fast - use `TestCase` for database tests, `SimpleTestCase` for non-database tests

## Writing New Tests

When adding new features:

1. **Add model tests** if you create new models or modify existing ones
2. **Add view tests** for new views or view modifications
3. **Add API tests** for new API endpoints
4. **Add form tests** for new forms or form changes
5. **Add serializer tests** for new serializers
6. **Update existing tests** if you break existing functionality

### Example Test Structure

```python
class MyNewFeatureTests(TestCase):
    """Test cases for MyNewFeature"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create test data
    
    def test_feature_works_correctly(self):
        """Test that feature works as expected"""
        # Arrange
        # Act
        # Assert
        self.assertEqual(actual, expected)
```

## Continuous Integration

Tests should be run:
- Before committing code
- In CI/CD pipeline
- Before deploying to production
- When fixing bugs (add regression tests)

## Troubleshooting

### Tests Failing

1. Check database migrations are up to date: `python manage.py migrate`
2. Check test database is clean: `python manage.py flush`
3. Check for test isolation issues (shared state)
4. Check for timezone issues (use `timezone.now()`)

### Import Errors

1. Ensure you're running from project root
2. Check `PYTHONPATH` includes project directory
3. Verify `__init__.py` files exist in test directories

### Database Errors

1. Ensure test database can be created
2. Check database permissions
3. Verify migrations are applied

## Additional Resources

- [Django Testing Documentation](https://docs.djangoproject.com/en/stable/topics/testing/)
- [DRF Testing Documentation](https://www.django-rest-framework.org/api-guide/testing/)
- [Python unittest Documentation](https://docs.python.org/3/library/unittest.html)
