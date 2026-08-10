from collections import defaultdict
import time
from config import USERNAME, PASSWORD, JWT_SECRET_KEY
from flask_jwt_extended import create_access_token
import uuid

# Rate limiting
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300
login_attempts = defaultdict(list)  # {ip: [timestamps]}


def check_rate_limit(ip):
    """Check if IP is rate limited. Returns (is_limited, lockout_remaining_seconds)"""
    now = time.time()
    # Clean old attempts outside the lockout window
    attempts = login_attempts[ip]
    login_attempts[ip] = [t for t in attempts if now - t < LOCKOUT_SECONDS]
    attempts = login_attempts[ip]

    if len(attempts) >= MAX_ATTEMPTS:
        oldest = attempts[0]
        remaining = int(LOCKOUT_SECONDS - (now - oldest))
        return True, max(remaining, 0)
    return False, 0


def record_failed_attempt(ip):
    """Record a failed login attempt for this IP"""
    login_attempts[ip].append(time.time())


def clear_attempts(ip):
    """Clear login attempts for this IP (after successful login)"""
    if ip in login_attempts:
        del login_attempts[ip]


def login(username, password, ip):
    """
    Attempt login. Returns token on success.
    Raises PermissionError on rate limit.
    Returns None on wrong credentials with attempts_left count.
    """
    # Check rate limit first
    is_limited, remaining = check_rate_limit(ip)
    if is_limited:
        raise PermissionError(f'登录失败次数过多，请 {remaining} 秒后重试')

    if username != USERNAME or password != PASSWORD:
        record_failed_attempt(ip)
        is_limited, remaining = check_rate_limit(ip)
        if is_limited:
            raise PermissionError(f'登录失败次数过多，请 {remaining} 秒后重试')
        attempts_left = MAX_ATTEMPTS - len(login_attempts[ip])
        return None, attempts_left

    # Successful login - clear attempts
    clear_attempts(ip)
    csrf_token = str(uuid.uuid4())
    additional_claims = {"csrf": csrf_token}
    token = create_access_token(
        identity=username,
        additional_claims=additional_claims
    )
    return token, None
