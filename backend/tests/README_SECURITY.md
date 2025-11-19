# Security Tests

Comprehensive security and penetration testing suite for the Provote application.

## Test Files

### `test_security.py`
Main security test suite covering:
- SQL injection protection
- XSS (Cross-Site Scripting) protection
- CSRF (Cross-Site Request Forgery) protection
- Authentication bypass protection
- Rate limit bypass protection
- Idempotency key manipulation protection
- Vote manipulation protection
- Security headers verification
- Data encryption verification
- Audit log capture verification

### `test_security_advanced.py`
Advanced security tests for edge cases:
- Path traversal attacks
- HTTP header injection
- Parameter pollution
- Mass assignment
- Timing attacks
- Session fixation
- Input validation
- API abuse

## Running Security Tests

### Run all security tests (without coverage requirement):
```bash
pytest backend/tests/test_security*.py -v -m security --no-cov
```

Or to allow lower coverage for security tests:
```bash
pytest backend/tests/test_security*.py -v -m security --cov-fail-under=0
```

### Run specific test class:
```bash
pytest backend/tests/test_security.py::TestSQLInjectionProtection -v --no-cov
```

### Run with coverage (for reporting only):
```bash
pytest backend/tests/test_security*.py -v -m security --cov=backend --cov-report=html --cov-fail-under=0
```

**Note:** Security tests focus on verifying security mechanisms, not achieving full code coverage. The 90% coverage requirement in `pytest.ini` applies to the full test suite, not individual test categories. Use `--no-cov` or `--cov-fail-under=0` when running security tests alone.

## Test Categories

### SQL Injection Tests
Tests protection against SQL injection attacks in:
- URL parameters (poll_id, etc.)
- Query parameters (search, filters)
- Request body (vote data)

**Expected behavior:**
- All SQL injection attempts should return 400 (Bad Request) or 404 (Not Found)
- No SQL should be executed
- Database should remain unchanged

### XSS Tests
Tests protection against Cross-Site Scripting attacks:
- Poll title/description with script tags
- Query parameters with XSS payloads
- Response escaping

**Expected behavior:**
- Script tags should be escaped or removed
- Responses should be properly sanitized
- Content-Type should be application/json (not HTML)

### CSRF Tests
Tests CSRF protection:
- POST requests without CSRF token
- Invalid CSRF tokens
- CSRF bypass attempts

**Expected behavior:**
- POST requests without valid CSRF token should return 403 (Forbidden)
- Invalid tokens should be rejected
- Bypass attempts should fail

### Authentication Bypass Tests
Tests authentication security:
- Unauthenticated access to protected endpoints
- Invalid tokens
- Session hijacking
- Privilege escalation

**Expected behavior:**
- Protected endpoints should return 401 (Unauthorized) or 403 (Forbidden)
- Invalid tokens should be rejected
- Regular users cannot access admin endpoints

### Rate Limit Bypass Tests
Tests rate limiting:
- Rate limit enforcement
- Bypass attempt prevention
- Rate limit window reset

**Expected behavior:**
- After exceeding rate limit, should return 429 (Too Many Requests)
- Bypass attempts should fail (unless in test mode)
- Rate limits should reset after time window

### Idempotency Key Tests
Tests idempotency key security:
- Key validation
- Injection attempts
- Replay attack prevention

**Expected behavior:**
- Invalid keys should be rejected or sanitized
- Duplicate keys should return 409 (Conflict)
- Replay attacks should be prevented

### Vote Manipulation Tests
Tests vote manipulation protection:
- Non-existent poll/choice
- Wrong poll-choice combinations
- Invalid vote data

**Expected behavior:**
- Invalid poll/choice IDs should return 400 or 404
- Wrong combinations should be rejected
- Malformed data should be rejected

### Security Headers Tests
Tests presence of security headers:
- X-Frame-Options
- X-Content-Type-Options
- X-XSS-Protection

**Expected behavior:**
- Security headers should be present in responses
- Headers should have correct values

### Data Encryption Tests
Tests data encryption:
- Password hashing
- Sensitive data not in responses

**Expected behavior:**
- Passwords should be hashed (not plain text)
- Sensitive data should not appear in API responses

### Audit Log Tests
Tests audit log capture:
- All requests logged
- Security events logged
- IP address and user agent captured

**Expected behavior:**
- All API requests should be logged
- Security events (SQL injection, XSS, etc.) should be logged
- Logs should include IP address and user agent

## Security Best Practices

1. **Never disable security features in production**
   - CSRF protection should always be enabled
   - Rate limiting should be enabled (except for load tests)
   - Security headers should be present

2. **Monitor audit logs**
   - Review logs regularly for suspicious activity
   - Set up alerts for security events
   - Investigate repeated failed authentication attempts

3. **Keep dependencies updated**
   - Regularly update Django and dependencies
   - Monitor security advisories
   - Apply security patches promptly

4. **Test regularly**
   - Run security tests as part of CI/CD pipeline
   - Perform penetration testing before releases
   - Review and update tests as new threats emerge

## Known Limitations

- Some tests may fail in development mode (e.g., CSRF may be relaxed)
- Rate limiting tests may be affected by `DISABLE_RATE_LIMITING` setting
- Timing attack tests have a margin of error (0.1 seconds)

## Contributing

When adding new security features:
1. Add corresponding security tests
2. Document expected behavior
3. Update this README
4. Ensure tests pass in both development and production modes

