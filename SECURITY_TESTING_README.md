# Security Testing Guide for national77.com

This guide helps you test your website for SQL injection vulnerabilities and check admin account security.

## Overview

Your Django application uses Django ORM, which provides built-in protection against SQL injection attacks. However, it's important to verify that:
1. No raw SQL queries are vulnerable
2. All user inputs are properly sanitized
3. Admin accounts are secure

## Scripts Provided

### 1. SQL Injection Testing (`test_sql_injection.py`)

This script tests your website for SQL injection vulnerabilities by:
- Testing login forms with SQL injection payloads
- Testing search parameters
- Testing URL parameters
- Testing API endpoints
- Checking for SQL error messages in responses

**How to Run:**
```bash
cd /Users/pradyumna/chip_3
python3 test_sql_injection.py
```

**What it does:**
- Sends various SQL injection payloads to your endpoints
- Checks responses for SQL error indicators
- Generates a report (`sql_injection_test_report.json`)

**Expected Results:**
Since your Django app uses ORM, you should see:
- ✓ No SQL injection vulnerabilities detected
- All endpoints should be safe

### 2. Admin Account Checker (`check_admin_accounts.py`)

This script checks your database for admin accounts and their security settings.

**How to Run:**
```bash
cd /Users/pradyumna/chip_3
python3 check_admin_accounts.py
```

**What it shows:**
- List of all admin/superuser accounts
- Account details (username, email, last login)
- Password hashing algorithm used
- Security recommendations

## Manual Testing

You can also manually test your site:

### 1. Test Login Form
Try these in the username field:
- `admin'--`
- `' OR '1'='1`
- `admin'/*`

**Expected:** Should show "Invalid username or password" (not SQL errors)

### 2. Test Search Fields
Try these in search boxes:
- `' UNION SELECT NULL--`
- `'; SELECT pg_sleep(5)--`

**Expected:** Should return empty results or timeout normally (not execute SQL)

### 3. Test URL Parameters
Try accessing:
- `https://national77.com/transactions/?client=1' OR '1'='1`
- `https://national77.com/dashboard/?search=' UNION SELECT NULL--`

**Expected:** Should handle gracefully without SQL errors

## Security Analysis of Your Code

### ✅ Good Security Practices Found:

1. **Django ORM Usage**: Your code uses Django ORM throughout, which automatically escapes SQL queries
   ```python
   # Safe - Django ORM handles escaping
   transactions_qs = Transaction.objects.filter(client_exchange__client__user=request.user)
   ```

2. **Input Validation**: User inputs are validated and sanitized
   ```python
   username = request.POST.get("username", "").strip()
   ```

3. **Rate Limiting**: Login attempts are rate-limited (5 attempts per 5 minutes)

4. **CSRF Protection**: Django CSRF protection is enabled

5. **Password Hashing**: Django uses secure password hashing (PBKDF2/bcrypt/Argon2)

6. **No Raw SQL**: Only one raw SQL query found, and it's safe:
   ```python
   cursor.execute("SELECT 1")  # No user input - safe
   ```

### ⚠️ Areas to Monitor:

1. **Search Queries**: While Django ORM is used, ensure all search filters use `.filter()` with proper escaping
   - Current implementation looks safe: `Q(client_exchange__client__name__icontains=search_query)`

2. **API Endpoints**: Ensure all API endpoints validate and sanitize input
   - Current implementation uses Django REST Framework serializers (safe)

3. **Admin Accounts**: 
   - Regularly review admin account access
   - Use strong passwords (12+ characters)
   - Enable 2FA if available

## Recommendations

### Immediate Actions:
1. ✅ Run the SQL injection test script
2. ✅ Check admin accounts using the admin checker script
3. ✅ Review the generated security report

### Ongoing Security:
1. **Keep Django Updated**: Regularly update Django and dependencies
   ```bash
   pip install --upgrade django
   ```

2. **Enable Security Middleware**: Ensure these are in your `settings.py`:
   ```python
   MIDDLEWARE = [
       'django.middleware.security.SecurityMiddleware',
       'django.middleware.csrf.CsrfViewMiddleware',
       # ... other middleware
   ]
   ```

3. **Use HTTPS**: Always use HTTPS in production
   ```python
   SECURE_SSL_REDIRECT = True
   SESSION_COOKIE_SECURE = True
   CSRF_COOKIE_SECURE = True
   ```

4. **Monitor Logs**: Check Django logs for suspicious activity
   ```python
   # Your code already logs security events
   logger.warning(f'Login rate limit exceeded for IP: {ip_address}')
   ```

5. **Regular Security Audits**: Run these scripts periodically

## Understanding the Results

### If SQL Injection Test Finds Vulnerabilities:
1. Review the vulnerable endpoint
2. Check if raw SQL is being used
3. Ensure all user input goes through Django ORM
4. Fix any issues found

### If No Vulnerabilities Found:
- ✅ Your Django ORM usage is protecting you
- ✅ Continue using Django ORM for all database queries
- ✅ Never use raw SQL with user input

## Additional Security Resources

- [Django Security Documentation](https://docs.djangoproject.com/en/stable/topics/security/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Django Security Best Practices](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/)

## Notes

- **Passwords Cannot Be Retrieved**: Django stores passwords as hashes. You cannot "get" passwords from the database. To reset an admin password, use:
  ```bash
  python manage.py changepassword <username>
  ```

- **Testing Your Own Site**: Since this is your site, you have authorization to test it. Always get permission before testing other sites.

- **Rate Limiting**: The test scripts include delays to avoid triggering your rate limiting. If tests fail due to rate limiting, increase the delays in the scripts.
